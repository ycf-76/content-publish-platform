"""沙箱自测（ref: Codex `codex sandbox --log-denials` 的自我验证思路）。

运行：py -m app.sandbox.selftest
全部断言在临时目录内进行，不触碰真实 .env / workspace。

验收断言（对应技术方案 Phase 1 验收标准）：
  1. 子进程运行于 Low 完整性（S-1-16-4096）
  2. 写 workspace 外（Medium）→ 拒绝
  3. 写 workspace 内（Low 标签）→ 成功
  4. 父进程创建的 workspace 文件 → 子进程可改写（标签继承）
  5. 读 NR 标签密钥文件 → 拒绝
  6. os.replace 重写密钥文件后标签丢失 → 重打后仍拒绝（config 集成的依据）
  7. 父进程密钥类环境变量 → 子进程不可见
  8. Job 进程数限额（第 9 个进程被拒）
  9. 超时 → 进程树全灭（孙进程无存活）
 10. 正向用例：常规命令在沙箱内正常完成
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

from app.sandbox.win_native import (
    build_env_block,
    label_dir_low_writable,
    label_file_no_read_up,
    label_tree_low_writable,
    spawn_sandboxed,
)

PY = sys.executable
PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        PASSED.append(name)
        print(f"  [PASS] {name}")
    else:
        FAILED.append(name)
        print(f"  [FAIL] {name} {detail}")


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def run_child(script: str, ws: Path, timeout_s: float = 30.0, env_extra: dict | None = None):
    """在沙箱内执行一段 Python 脚本，返回 (result, 输出文本)。"""
    script_file = ws / "_selftest_child.py"
    _write(script_file, script)
    env = build_env_block(extra=env_extra, temp_dir=ws / "_tmp")
    (ws / "_tmp").mkdir(exist_ok=True)
    r = spawn_sandboxed(
        [PY, str(script_file)], cwd=ws, env=env, timeout_s=timeout_s,
    )
    return r, r.stdout.decode("utf-8", errors="replace")


def test_1_low_integrity(ws: Path) -> None:
    print("[1] 子进程完整性级别")
    _, out = run_child(
        "import win32security, win32api\n"
        "t = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32security.TOKEN_QUERY)\n"
        "s = win32security.GetTokenInformation(t, win32security.TokenIntegrityLevel)\n"
        "print('IL=' + win32security.ConvertSidToStringSid(s[0]))\n",
        ws,
    )
    check("child runs at Low IL", "IL=S-1-16-4096" in out, f"got: {out.strip()[:80]}")


def test_2_write_outside(ws: Path, outside: Path) -> None:
    print("[2] workspace 外写入被拒")
    target = outside / "victim.txt"
    _write(target, "secret")
    _, out = run_child(
        f"try:\n"
        f"    open(r'{target}', 'a').write('X')\n"
        f"    print('W=OK')\n"
        f"except Exception as e:\n"
        f"    print('W=DENIED')\n",
        ws,
    )
    leaked = target.read_text(encoding="utf-8") == "secret"
    check("write outside denied", "W=DENIED" in out and leaked, f"got: {out.strip()[:80]}")


def test_3_write_inside(ws: Path) -> None:
    print("[3] workspace 内写入成功")
    _, out = run_child(
        f"open(r'{ws / 'inside.txt'}', 'w').write('ok')\n"
        f"print('W=DONE')\n",
        ws,
    )
    ok_file = (ws / "inside.txt").read_text(encoding="utf-8") == "ok"
    check("write inside workspace", "W=DONE" in out and ok_file, f"got: {out.strip()[:80]}")


def test_4_label_inheritance(ws: Path) -> None:
    print("[4] 父进程创建的文件可被子进程改写（标签继承）")
    # 父进程（Medium）在 Low 标签目录里新建文件 → 应继承 Low 标签
    pre = ws / "parent_made.txt"
    _write(pre, "from-parent")
    _, out = run_child(
        f"try:\n"
        f"    open(r'{pre}', 'a').write('+child')\n"
        f"    print('M=OK')\n"
        f"except Exception as e:\n"
        f"    print('M=DENIED:' + str(e)[:50])\n",
        ws,
    )
    content = pre.read_text(encoding="utf-8")
    check(
        "parent-created file writable by child",
        "M=OK" in out and content == "from-parent+child",
        f"got: {out.strip()[:80]} content={content!r}",
    )


def test_5_secret_no_read_up(ws: Path, secret: Path) -> None:
    print("[5] NR 标签密钥不可读")
    label_file_no_read_up(secret)
    _, out = run_child(
        f"try:\n"
        f"    print('R=' + open(r'{secret}').read()[:20])\n"
        f"except Exception:\n"
        f"    print('R=DENIED')\n",
        ws,
    )
    check("secret read denied", "R=DENIED" in out and "R=API_KEY" not in out, f"got: {out.strip()[:80]}")


def test_6_relabel_after_replace(ws: Path, secret: Path) -> None:
    print("[6] 重写后重打标签仍生效")
    # 模拟 config 路由的原子写：临时文件 + os.replace → SACL 丢失
    tmp = secret.with_suffix(".tmp")
    _write(tmp, "API_KEY=rotated-secret-123\n")
    os.replace(tmp, secret)
    # 未重打标签前：NR 语义可能已丢失（不作为断言，行为提示）
    # 重打标签（正确集成后 config 路由必须做的事）
    label_file_no_read_up(secret)
    _, out = run_child(
        f"try:\n"
        f"    print('R=' + open(r'{secret}').read()[:10])\n"
        f"except Exception:\n"
        f"    print('R=DENIED')\n",
        ws,
    )
    check(
        "relabel after os.replace keeps protection",
        "R=DENIED" in out and "rotated" not in out,
        f"got: {out.strip()[:80]}",
    )


def test_7_env_isolation(ws: Path) -> None:
    print("[7] 密钥环境变量隔离")
    os.environ["SANDBOX_SELFTEST_SECRET"] = "sk-parent-secret"
    try:
        _, out = run_child(
            "import os\n"
            "print('S=' + os.environ.get('SANDBOX_SELFTEST_SECRET', 'ABSENT'))\n",
            ws,
        )
        check(
            "parent secret env not visible in child",
            "S=ABSENT" in out and "sk-parent-secret" not in out,
            f"got: {out.strip()[:80]}",
        )
    finally:
        os.environ.pop("SANDBOX_SELFTEST_SECRET", None)


def test_8_process_limit(ws: Path) -> None:
    print("[8] Job 进程数限额")
    script = (
        "import subprocess, sys\n"
        "ok = 0\n"
        "procs = []\n"
        f"for i in range(10):\n"
        f"    try:\n"
        f"        p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(8)'])\n"
        f"        procs.append(p)\n"
        f"        ok += 1\n"
        f"    except Exception:\n"
        f"        break\n"
        f"print('SPAWNED=' + str(ok))\n"
    )
    _, out = run_child(script, ws, timeout_s=60)
    # 主子进程自身占 1 个名额 → 最多 7 个孙进程
    spawned = None
    for line in out.splitlines():
        if line.startswith("SPAWNED="):
            spawned = int(line.split("=")[1])
    check(
        "process spawn capped by job limit",
        spawned is not None and spawned <= 7,
        f"spawned={spawned}",
    )


def test_9_timeout_tree_kill(ws: Path) -> None:
    print("[9] 超时全树击杀")
    script = (
        "import subprocess, sys, time\n"
        f"g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30); print(1)'])\n"
        f"print('GPID=' + str(g.pid), flush=True)\n"
        f"time.sleep(30)\n"
    )
    r, out = run_child(script, ws, timeout_s=3.0)
    gpid = None
    for line in out.splitlines():
        if line.startswith("GPID="):
            gpid = int(line.split("=")[1])
    assert gpid is not None, "selftest bug: grandchild pid not captured"
    assert r.timed_out, "selftest bug: expected timeout"

    # 等句柄真正释放
    time.sleep(1.0)
    import win32api
    alive = True
    try:
        h = win32api.OpenProcess(0x1000, 0, gpid)  # PROCESS_QUERY_LIMITED_INFORMATION
        win32api.CloseHandle(h)
    except Exception:
        alive = False
    check("grandchild killed on timeout", not alive, f"grandchild pid {gpid} still alive")


def test_10_positive(ws: Path) -> None:
    print("[10] 正向用例：常规执行")
    r, out = run_child(
        "print('HELLO=' + str(21 * 2))\n"
        "import sys; sys.stderr.write('warn-line\\n')\n",
        ws,
    )
    check(
        "normal execution works",
        r.exit_code == 0 and "HELLO=42" in out and b"warn-line" in r.stderr,
        f"exit={r.exit_code} out={out.strip()[:40]}",
    )


def main() -> int:
    print(f"Python: {sys.version}")
    print(f"Executable: {PY}")
    print("=" * 60)

    with tempfile.TemporaryDirectory(prefix="sandbox_selftest_") as td:
        tmp = Path(td)
        ws = tmp / "workspace"
        ws.mkdir()
        outside = tmp / "outside"
        outside.mkdir()
        secret = outside / "fake.env"
        _write(secret, "API_KEY=fake-secret-abc\n")

        # 初始化沙箱环境（与 init_sandbox 相同的语义，但在临时目录）
        label_tree_low_writable(ws)
        stmp = ws / "_tmp"
        stmp.mkdir()

        test_1_low_integrity(ws)
        test_2_write_outside(ws, outside)
        test_3_write_inside(ws)
        test_4_label_inheritance(ws)
        test_5_secret_no_read_up(ws, secret)
        test_6_relabel_after_replace(ws, secret)
        test_7_env_isolation(ws)
        test_8_process_limit(ws)
        test_9_timeout_tree_kill(ws)
        test_10_positive(ws)

    print("=" * 60)
    print(f"PASS {len(PASSED)} / FAIL {len(FAILED)}")
    if FAILED:
        print("FAILED items:", ", ".join(FAILED))
        return 1
    print("ALL SANDBOX SELFTEST ASSERTIONS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
