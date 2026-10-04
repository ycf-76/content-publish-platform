"""Windows 原生沙箱（OS-native sandbox）—— L1 层。

设计对齐 Codex unelevated 模式（ref: codex-rs windows sandbox）：
  - 子进程令牌降为 Low 完整性级别（S-1-16-4096）→ 内核强制 no-write-up，
    全盘默认只读，唯一可写区为 Low 标签的 workspace。
  - 密钥文件打 Medium + No-Read-Up 标签（S:(ML;;NR;;;ME)）→ Low 进程不可读。
  - Job Object 限制进程数/内存，KILL_ON_JOB_CLOSE 保证进程树整体回收。

已实测验证的关键事实（2026-09，Python 3.12 + pywin32 + Win11）：
  1. CreateProcessAsUser 免 SeAssignPrimaryTokenPrivilege 的条件是令牌为本进程
     主令牌的副本；CreateRestrictedToken 会破坏该豁免（1314 错误），
     因此本模块【不使用】CreateRestrictedToken，仅降完整性级别。
  2. 降低 TokenIntegrityLevel 不影响上述豁免，且 Low 子进程写 Medium
     路径会被内核拒绝（行为学验证通过）。
  3. pywin32 环境参数为 dict；Job 限额通过 dict 传入（IoInfo 需含全部 6 字段）。

局限（诚实声明，同 Codex unelevated）：Low IL 不隔离网络。需要内核级断网时
升级 L2（AppContainer），见 docs/技术架构设计文档.md。
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import win32api
import win32con
import win32file
import win32job
import win32pipe
import win32process
import win32security

# TOKEN_GROUPS 中 IntegrityLevel SID 的属性位
SE_GROUP_INTEGRITY = 0x20
# Low 完整性 SID 字符串（仅日志/比对用）
LOW_INTEGRITY_SID = "S-1-16-4096"

# 环境变量白名单：子进程仅能看到这些（密钥类一律不透传）
_ENV_WHITELIST = (
    "SYSTEMROOT", "SYSTEMDRIVE", "COMSPEC", "PATH",
    "PYTHONIOENCODING", "LANG",
)
# 沙箱内固定注入的环境变量
# PYTHONDONTWRITEBYTECODE：site-packages 为 Medium，Low 进程写 __pycache__ 会报错
_FIXED_ENV = {
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONIOENCODING": "utf-8",
}


class SandboxError(RuntimeError):
    """沙箱原语调用失败。"""


# ---------------------------------------------------------------------------
# 令牌构建
# ---------------------------------------------------------------------------

def build_low_integrity_token():
    """从当前进程主令牌派生 Low 完整性令牌。

    红线：不得使用 CreateRestrictedToken —— 它会让 CreateProcessAsUser
    在非提权进程上返回 1314（实测结论，见模块 docstring）。
    """
    tok = win32security.OpenProcessToken(
        win32api.GetCurrentProcess(),
        win32security.TOKEN_DUPLICATE | win32security.TOKEN_QUERY
        | win32security.TOKEN_ASSIGN_PRIMARY,
    )
    primary = win32security.DuplicateTokenEx(
        tok,
        win32security.SecurityImpersonation,
        win32con.MAXIMUM_ALLOWED,
        win32security.TokenPrimary,
    )
    low_sid = win32security.CreateWellKnownSid(win32security.WinLowLabelSid)
    win32security.SetTokenInformation(
        primary, win32security.TokenIntegrityLevel, (low_sid, SE_GROUP_INTEGRITY),
    )
    return primary


# ---------------------------------------------------------------------------
# ML 强制标签（完整性标签）
# ---------------------------------------------------------------------------

def _set_ml_label(path: str | Path, sddl: str) -> None:
    """对文件/目录设置强制完整性标签（SACL）。幂等。"""
    sd = win32security.ConvertStringSecurityDescriptorToSecurityDescriptor(sddl, 1)
    sacl = sd.GetSecurityDescriptorSacl()
    if sacl is None:
        raise SandboxError(f"invalid SDDL produced no SACL: {sddl}")
    win32security.SetNamedSecurityInfo(
        str(path),
        win32security.SE_FILE_OBJECT,
        win32security.LABEL_SECURITY_INFORMATION,
        None, None, None, sacl,
    )


def label_dir_low_writable(path: str | Path) -> None:
    """目录打 Low+NW 标签（含 OI/CI 继承）= Codex 的 workspace-write 语义。

    Low 及以上进程可写；新建子文件继承 Low 标签。
    Medium 的后端进程写 Low 目录不受影响（no-WRITE-up 只限制向上写）。
    """
    _set_ml_label(path, "S:(ML;OICI;NW;;;LW)")


def label_file_no_read_up(path: str | Path) -> None:
    """文件打 Medium+NR 标签：Low 进程不可读（密钥保护核心）。

    注意：os.replace/重写文件会丢失 SACL —— 任何重写密钥文件的代码路径
    必须在写完后重新调用本函数（见 config 路由集成）。
    """
    _set_ml_label(path, "S:(ML;;NR;;;ME)")


def label_tree_low_writable(root: str | Path) -> None:
    """递归把目录树打 Low 标签（含已存在文件，保证存量文件可被沙箱改写）。"""
    root = Path(root)
    label_dir_low_writable(root)
    for p in root.rglob("*"):
        try:
            if p.is_dir():
                label_dir_low_writable(p)
            else:
                _set_ml_label(p, "S:(ML;;NW;;;LW)")
        except OSError:
            # 个别文件被占用/无权限时跳过，不阻断整体初始化
            continue


# ---------------------------------------------------------------------------
# 环境变量净化（凭据隔离，ref: Claude Code envVars mask）
# ---------------------------------------------------------------------------

def build_env_block(
    extra: dict[str, str] | None = None,
    temp_dir: str | Path | None = None,
) -> dict[str, str]:
    """构建沙箱子进程环境变量：白名单 + 固定项，绝不透传密钥。

    temp_dir 必须是 Low 可写目录（系统 TEMP 为 Medium，Low 进程写不了）。
    """
    env: dict[str, str] = {}
    for key in _ENV_WHITELIST:
        val = os.environ.get(key)
        if val:
            env[key] = val
    env.update(_FIXED_ENV)
    if temp_dir is not None:
        env["TEMP"] = str(temp_dir)
        env["TMP"] = str(temp_dir)
    if extra:
        # extra 也走白名单纪律之外显式注入（调用方自担责任，用于 skill 运行参数）
        env.update(extra)
    return env


# ---------------------------------------------------------------------------
# Job Object
# ---------------------------------------------------------------------------

def create_job_object(
    active_process_limit: int = 8,
    process_memory_mb: int = 512,
    job_memory_mb: int = 1024,
):
    """创建限频 Job：进程数上限、单进程/整 Job 内存上限、句柄关闭即全杀。"""
    job = win32job.CreateJobObject(None, "")
    info = {
        "BasicLimitInformation": {
            "PerProcessUserTimeLimit": 0,
            "PerJobUserTimeLimit": 0,
            "LimitFlags": (
                win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                | win32job.JOB_OBJECT_LIMIT_ACTIVE_PROCESS
                | win32job.JOB_OBJECT_LIMIT_PROCESS_MEMORY
                | win32job.JOB_OBJECT_LIMIT_JOB_MEMORY
            ),
            "MinimumWorkingSetSize": 0,
            "MaximumWorkingSetSize": 0,
            "ActiveProcessLimit": active_process_limit,
            "Affinity": 0,
            "PriorityClass": 0,
            "SchedulingClass": 0,
        },
        "IoInfo": {
            "ReadOperationCount": 0,
            "WriteOperationCount": 0,
            "OtherOperationCount": 0,
            "ReadTransferCount": 0,
            "WriteTransferCount": 0,
            "OtherTransferCount": 0,
        },
        "ProcessMemoryLimit": process_memory_mb * 1024 * 1024,
        "JobMemoryLimit": job_memory_mb * 1024 * 1024,
        "PeakProcessMemoryUsed": 0,
        "PeakJobMemoryUsed": 0,
    }
    win32job.SetInformationJobObject(
        job, win32job.JobObjectExtendedLimitInformation, info,
    )
    return job


# ---------------------------------------------------------------------------
# 沙箱执行
# ---------------------------------------------------------------------------

@dataclass
class SandboxResult:
    """沙箱执行结果。timed_out=True 时 exit_code 为 Job 终止码。"""
    exit_code: int | None
    stdout: bytes
    stderr: bytes
    timed_out: bool = False
    pid: int | None = None
    duration_s: float = 0.0
    meta: dict[str, Any] = field(default_factory=dict)


def _read_pipe_thread(handle, out: list[bytearray], lock: threading.Lock) -> None:
    """后台线程：持续读管道直到 EOF（broken pipe）。"""
    buf = bytearray()
    while True:
        try:
            _, data = win32file.ReadFile(handle, 65536)
            if not data:
                break
            buf.extend(data)
        except Exception:
            break  # ERROR_BROKEN_PIPE / handle closed
    with lock:
        out.append(buf)


def spawn_sandboxed(
    argv: list[str],
    cwd: str | Path,
    env: dict[str, str],
    timeout_s: float = 60.0,
    stdin: bytes | None = None,
    active_process_limit: int = 8,
    process_memory_mb: int = 512,
) -> SandboxResult:
    """在 Low IL 沙箱中执行 argv，返回 stdout/stderr/exit_code。

    流程：建 Job → 建管道 → CREATE_SUSPENDED 启动 → 挂 Job → Resume →
    带超时等待 → 超时则 TerminateJobObject 全树击杀。
    （suspended + 先挂 Job 再 resume：关闭进程逃逸 Job 的竞态窗口）
    """
    if not argv:
        raise SandboxError("argv must not be empty")

    started = time.monotonic()
    token = build_low_integrity_token()
    job = create_job_object(
        active_process_limit=active_process_limit,
        process_memory_mb=process_memory_mb,
    )

    sa = win32security.SECURITY_ATTRIBUTES()
    sa.bInheritHandle = 1
    stdin_r, stdin_w = win32pipe.CreatePipe(sa, 0)
    stdout_r, stdout_w = win32pipe.CreatePipe(sa, 0)
    stderr_r, stderr_w = win32pipe.CreatePipe(sa, 0)

    si = win32process.STARTUPINFO()
    si.dwFlags = win32con.STARTF_USESTDHANDLES
    si.hStdInput = stdin_r
    si.hStdOutput = stdout_w
    si.hStdError = stderr_w

    cmdline = subprocess_list2cmdline(argv)
    creation = win32con.CREATE_NO_WINDOW | win32con.CREATE_SUSPENDED

    h_process = h_thread = None
    try:
        h_process, h_thread, pid, _tid = win32process.CreateProcessAsUser(
            token, None, cmdline, None, None, 1, creation, env, str(cwd), si,
        )
        # 子进程已持有管道读/写端，父进程立即关闭自己的冗余端
        win32api.CloseHandle(stdin_r)
        win32api.CloseHandle(stdout_w)
        win32api.CloseHandle(stderr_w)
        stdin_r = stdout_w = stderr_w = None

        win32job.AssignProcessToJobObject(job, h_process)
        win32process.ResumeThread(h_thread)

        # stdin 写入（小数据量同步写；skill runner 协议的 inputs JSON）
        if stdin:
            win32file.WriteFile(stdin_w, stdin)
        if stdin_w is not None:
            win32api.CloseHandle(stdin_w)  # 关闭写端 → 子进程读到 EOF
            stdin_w = None

        # 后台线程收 stdout / stderr
        out_bufs: list[bytearray] = []
        err_bufs: list[bytearray] = []
        lock = threading.Lock()
        t_out = threading.Thread(target=_read_pipe_thread, args=(stdout_r, out_bufs, lock), daemon=True)
        t_err = threading.Thread(target=_read_pipe_thread, args=(stderr_r, err_bufs, lock), daemon=True)
        t_out.start()
        t_err.start()

        timed_out = False
        deadline_ms = int(timeout_s * 1000)
        rc = win32event_wait(h_process, deadline_ms)
        if rc == win32con.WAIT_TIMEOUT:
            timed_out = True
            win32job.TerminateJobObject(job, 1)
            # 等待主进程句柄收敛
            win32event_wait(h_process, 5000)

        exit_code = win32process.GetExitCodeProcess(h_process)
        # 等读线程收完管道尾部数据
        t_out.join(timeout=2.0)
        t_err.join(timeout=2.0)
        # 读端由父进程统一关闭（子进程退出后管道已 EOF，读线程已结束）
        try:
            win32api.CloseHandle(stdout_r)
        except Exception:
            pass
        try:
            win32api.CloseHandle(stderr_r)
        except Exception:
            pass
        stdout_r = stderr_r = None

        stdout_bytes = bytes(out_bufs[0]) if out_bufs else b""
        stderr_bytes = bytes(err_bufs[0]) if err_bufs else b""
        return SandboxResult(
            exit_code=exit_code,
            stdout=stdout_bytes,
            stderr=stderr_bytes,
            timed_out=timed_out,
            pid=pid,
            duration_s=time.monotonic() - started,
        )
    finally:
        for h in (stdin_r, stdin_w, stdout_w, stderr_w, stdout_r, stderr_r):
            if h is not None:
                try:
                    win32api.CloseHandle(h)
                except Exception:
                    pass
        if h_process is not None:
            try:
                win32api.CloseHandle(h_process)
            except Exception:
                pass
        if h_thread is not None:
            try:
                win32api.CloseHandle(h_thread)
            except Exception:
                pass
        # Job 句柄关闭 → KILL_ON_JOB_CLOSE 兜底清场（正常路径子进程已退出）
        try:
            win32api.CloseHandle(job)
        except Exception:
            pass


def win32event_wait(handle, timeout_ms: int) -> int:
    """WaitForSingleObject 封装，返回 WAIT_OBJECT_0 / WAIT_TIMEOUT。"""
    import win32event
    return win32event.WaitForSingleObject(handle, timeout_ms)


def subprocess_list2cmdline(argv: list[str]) -> str:
    """list -> Windows 命令行字符串（等价 subprocess.list2cmdline）。

    沙箱模块不 import subprocess（避免与 asyncio 语义混淆），语义一致。
    """
    import subprocess as _sp
    return _sp.list2cmdline(argv)


# ---------------------------------------------------------------------------
# 初始化（启动时幂等调用）
# ---------------------------------------------------------------------------

def default_workspace_root() -> Path:
    """与 file_tools._workspace_root 相同的约定，避免循环 import。"""
    root = os.environ.get("WORKSPACE_ROOT", "")
    if root:
        return Path(root).resolve()
    backend_dir = Path(__file__).resolve().parent.parent.parent
    return (backend_dir / "data" / "workspace").resolve()


def init_sandbox(
    workspace_root: str | Path | None = None,
    secret_files: list[str | Path] | None = None,
) -> dict[str, Any]:
    """启动时幂等初始化：workspace 打 Low 可写标签 + 密钥文件打 NR 标签。

    secret_files 默认为 backend/.env（存在才处理）。
    返回执行摘要（供日志/自检）。
    """
    ws = Path(workspace_root) if workspace_root else default_workspace_root()
    ws.mkdir(parents=True, exist_ok=True)
    label_tree_low_writable(ws)

    protected: list[str] = []
    backend_dir = Path(__file__).resolve().parent.parent.parent
    secrets = secret_files if secret_files is not None else [backend_dir / ".env"]
    for f in secrets:
        f = Path(f)
        if f.exists():
            label_file_no_read_up(f)
            protected.append(str(f))

    return {
        "workspace": str(ws),
        "protected_secrets": protected,
        "label": "low_integrity",
    }
