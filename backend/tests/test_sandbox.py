"""沙箱模块 pytest 回归（快速子集；完整验收跑 py -m app.sandbox.selftest）。

跳过条件：非 Windows 或缺 pywin32 时自动 skip。
"""

import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("win32security")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.sandbox.win_native import (  # noqa: E402
    build_env_block,
    label_dir_low_writable,
    spawn_sandboxed,
)

PY = sys.executable


@pytest.fixture()
def ws(tmp_path: Path) -> Path:
    """Low 标签的临时工作区。"""
    ws = tmp_path / "workspace"
    ws.mkdir()
    label_dir_low_writable(ws)
    return ws


def _run(script: str, ws: Path, timeout_s: float = 30.0):
    f = ws / "_t.py"
    f.write_text(script, encoding="utf-8")
    env = build_env_block(temp_dir=ws)
    return spawn_sandboxed([PY, str(f)], cwd=ws, env=env, timeout_s=timeout_s)


def test_child_runs_low_and_env_isolated(ws: Path):
    os.environ["SB_TEST_SECRET"] = "sk-leak"
    try:
        r = _run(
            "import os, win32security, win32api\n"
            "t = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32security.TOKEN_QUERY)\n"
            "s = win32security.GetTokenInformation(t, win32security.TokenIntegrityLevel)\n"
            "print(win32security.ConvertSidToStringSid(s[0]))\n"
            "print(os.environ.get('SB_TEST_SECRET', 'ABSENT'))\n",
            ws,
        )
    finally:
        os.environ.pop("SB_TEST_SECRET", None)
    out = r.stdout.decode()
    assert r.exit_code == 0
    assert "S-1-16-4096" in out          # Low 完整性
    assert "sk-leak" not in out          # 密钥未透传
    assert "ABSENT" in out


def test_write_outside_denied_inside_ok(ws: Path, tmp_path: Path):
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    r = _run(
        f"try:\n"
        f"    open(r'{outside}', 'a').write('X'); print('OUT=OK')\n"
        f"except Exception: print('OUT=DENIED')\n"
        f"open(r'{ws / 'in.txt'}', 'w').write('ok'); print('IN=OK')\n",
        ws,
    )
    out = r.stdout.decode()
    assert "OUT=DENIED" in out
    assert outside.read_text(encoding="utf-8") == "secret"
    assert "IN=OK" in out
    assert (ws / "in.txt").read_text(encoding="utf-8") == "ok"


def test_timeout_kills_tree(ws: Path):
    r = _run(
        "import subprocess, sys, time\n"
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
        "print('STARTED', flush=True)\n"
        "time.sleep(30)\n",
        ws,
        timeout_s=3.0,
    )
    assert r.timed_out is True
    assert b"STARTED" in r.stdout
