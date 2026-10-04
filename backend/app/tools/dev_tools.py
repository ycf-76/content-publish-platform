"""通用开发工具 Skill：bash / glob / grep。

设计要点：
- BashSkill 高危（BASH_EXEC），默认拒绝，必须 env PERMISSIONS_ALLOW=bash:exec 才能放行。
- GlobSkill / GrepSkill 只读（FILE_READ），默认放行。
- 所有 Skill 返回 dict（与 Skill 协议一致），不抛业务异常以外的错误。
- 路径解析全部走 pathlib，禁用 shell=True。
- BashSkill 内置命令白名单 + 超时 + stdout 截断，避免 LLM 拿它干坏事。
"""

from __future__ import annotations

import asyncio
import fnmatch
import logging
import os
import re
import shlex
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.tools.registry import register
from app.tools.base import Skill
from app.engine.schemas import Permission

logger = logging.getLogger(__name__)


def _workspace_root() -> Path:
    """工作区根目录。安全红线：默认指向 backend/data/workspace/，绝不回退到项目根，
    否则 LLM 可经 grep 读到 backend/.env 里的密钥（FILE_READ 是默认低危权限）。"""
    root = os.environ.get("WORKSPACE_ROOT", "")
    if root:
        return Path(root).resolve()
    backend_dir = Path(__file__).resolve().parent.parent.parent
    return (backend_dir / "data" / "workspace").resolve()


def _expand_env_placeholders(text: str) -> str:
    """Expand WORKSPACE_ROOT tokens used by tools."""
    ws = str(_workspace_root())
    replacements = {
        "${WORKSPACE_ROOT}": ws,
        "$WORKSPACE_ROOT": ws,
        "WORKSPACE_ROOT": ws,
    }
    out = text
    for token, value in replacements.items():
        out = out.replace(token, value)
    return out


def _split_command(command: str) -> list[str]:
    """Split a command line without mangling Windows drive paths."""
    argv = shlex.split(command, posix=False) if os.name == "nt" else shlex.split(command, posix=True)
    cleaned: list[str] = []
    for token in argv:
        if len(token) >= 2 and token[0] == token[-1] and token[0] in ("'", '"'):
            token = token[1:-1]
        cleaned.append(token)
    return cleaned


# ----------------------------------------------------------------------
# Bash
# ----------------------------------------------------------------------


class BashInput(BaseModel):
    command: str = Field(..., description="Shell command line")
    cwd: str = Field(default="", description="Working directory")
    timeout: int = Field(default=15, ge=1, le=1800, description="Timeout in seconds")


@register
class BashSkill(Skill):
    """运行 shell 命令。

    红线：
    - 默认拒绝，必须 PERMISSIONS_ALLOW=bash:exec 才放行。
    - 不允许 shell=True（命令注入风险），用 shlex.split 拆参。
    - 命令前缀白名单（默认 git/ls/cat/echo/python/pip/node/npm/rg/find/grep/glob）。
      其他命令直接拒绝，返回结构化错误给 LLM。
    - stdout/stderr 各截断 4KB，避免把 LLM 上下文撑爆。
    """

    node_type = "file"
    name = "bash"
    description = "执行命令：运行只读 shell 命令（白名单限制）。输入 command，返回命令输出"
    input_schema = BashInput
    required_permissions = [Permission.BASH_EXEC]

    # 注入系统提示：让 LLM 第一次就用对姿势，避免"管道/重定向不支持、
    # 输出截断、白名单外命令"三类试错（每次试错都消耗一次高危确认）
    prompt_guidance: str = (
        "【bash 工具约束 — 违反必失败，不要试错】\n"
        "- 不经过 shell：管道 |、重定向 > >>、命令替换 $()、链式 && ; 都不支持，"
        "会被当作普通参数传给命令导致失败。一次只跑一条简单命令。\n"
        "- 可执行文件白名单：git/ls/cat/echo/pwd/rg/find/grep/glob/head/tail/wc/"
        "ffmpeg/ffprobe/piper/curl。其他命令（含 python/pip/node/npm）一律被拒。\n"
        "- Windows 平台自动替换：ls→dir, cat→type, pwd→cd, grep→findstr, "
        "find→dir /s /b。你可以照常写 ls -la，系统会透明转成 dir。\n"
        "- stdout/stderr 各截断 4KB。预期输出很长时主动收窄：如 curl 加 "
        "per_page=5、配合 grep 过滤关键行，不要先拉全量再截断。\n"
        "- 工作目录用 cwd 参数传，不要拼进 command。\n"
        "- 该工具为高危操作，每次调用都需要用户确认：把多个命令合并成尽量少的"
        "关键调用，不要频繁试探。"
    )

    # 允许的可执行文件前缀（不含路径）
    ALLOWED_BINARIES: frozenset[str] = frozenset(
        {
            "git",
            "ls",
            "cat",
            "echo",
            "pwd",
            "rg",
            "find",
            "grep",
            "glob",
            "head",
            "tail",
            "wc",
            "ffmpeg",
            "ffprobe",
            "piper",
            "curl",
            "dir",
            "type",
            "where",
        }
    )

    # Windows 上 Unix 命令 → 原生替代映射
    _WIN_CMD_MAP: dict[str, list[str]] = {
        "ls": ["cmd", "/c", "dir"],
        "cat": ["cmd", "/c", "type"],
        "pwd": ["cmd", "/c", "cd"],
        "grep": ["cmd", "/c", "findstr"],
        "find": ["cmd", "/c", "dir", "/s", "/b"],
        "head": ["cmd", "/c", "more"],
    }

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        in_ = BashInput.model_validate(inputs)
        try:
            argv = _split_command(_expand_env_placeholders(in_.command))
        except ValueError as e:
            return {"ok": False, "error": f"shlex parse failed: {e}"}
        if not argv:
            return {"ok": False, "error": "empty command"}

        binary = Path(argv[0]).stem.lower()
        if binary not in self.ALLOWED_BINARIES:
            return {
                "ok": False,
                "error": f"binary {binary!r} not in whitelist: {sorted(self.ALLOWED_BINARIES)}",
            }

        # Windows 平台：将 Unix 命令透明替换为 cmd 原生等价命令
        if os.name == "nt" and binary in self._WIN_CMD_MAP:
            win_prefix = self._WIN_CMD_MAP[binary]
            argv = [*win_prefix, *argv[1:]]

        # 拒绝 find/git 等的 -exec/-execdir/-ok 参数：它们能把任意命令
        # 委托给白名单内的 binary 执行，绕过白名单（如 find . -exec python -c ...）
        _DANGEROUS_FLAGS = {"-exec", "-execdir", "-ok", "-okdir"}
        if any(arg in _DANGEROUS_FLAGS for arg in argv[1:]):
            return {
                "ok": False,
                "error": "denied: -exec/-execdir/-ok flags are blocked to prevent whitelist bypass",
            }

        raw_cwd = _expand_env_placeholders(in_.cwd or "")
        cwd = Path(raw_cwd).expanduser() if raw_cwd else None
        if cwd is not None and not cwd.is_absolute():
            cwd = _workspace_root() / cwd
        if cwd is not None and not cwd.exists():
            return {"ok": False, "error": f"cwd does not exist: {cwd}"}

        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(cwd) if cwd else None,
            )
        except FileNotFoundError as e:
            return {"ok": False, "error": f"binary not found: {e}"}

        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=in_.timeout
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            return {
                "ok": False,
                "error": f"timeout after {in_.timeout}s",
                "exit_code": None,
            }

        return {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": _clip(stdout_b.decode("utf-8", errors="replace"), 4096),
            "stderr": _clip(stderr_b.decode("utf-8", errors="replace"), 4096),
            "command": in_.command,
        }


# ----------------------------------------------------------------------
# Glob
# ----------------------------------------------------------------------


class GlobInput(BaseModel):
    pattern: str = Field(..., description="Glob pattern, e.g. '**/*.py'")
    path: str = Field(default=".", description="Root directory")
    limit: int = Field(default=200, ge=1, le=2000, description="Max matches to return")


@register
class GlobSkill(Skill):
    """按 glob 模式列文件。"""

    node_type = "file"
    name = "glob"
    description = "文件搜索：按模式匹配列出工作区内的文件。输入 pattern（如 **/*.md），返回文件路径列表"
    input_schema = GlobInput
    required_permissions = [Permission.FILE_READ]

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        in_ = GlobInput.model_validate(inputs)
        root = Path(_expand_env_placeholders(in_.path)).expanduser()
        if not root.is_absolute():
            root = _workspace_root() / root
        if not root.exists() or not root.is_dir():
            return {"ok": False, "error": f"root not a dir: {root}", "matches": []}

        # 用 rglob 实现 **/<pattern>
        matches: list[str] = []
        try:
            pattern = in_.pattern.lstrip("/") if in_.pattern.startswith("/") else in_.pattern
            for p in root.rglob(pattern):
                if p.is_dir():
                    continue
                matches.append(str(p))
                if len(matches) >= in_.limit:
                    break
        except (OSError, re.error) as e:
            return {"ok": False, "error": str(e), "matches": []}

        return {
            "ok": True,
            "matches": matches,
            "count": len(matches),
            "truncated": len(matches) >= in_.limit,
        }


# ----------------------------------------------------------------------
# Grep
# ----------------------------------------------------------------------


class GrepInput(BaseModel):
    pattern: str = Field(..., description="Regex pattern")
    path: str = Field(default=".", description="File or directory to search")
    glob: str = Field(default="", description="Optional filename glob filter, e.g. '*.py'")
    ignore_case: bool = Field(default=False)
    max_matches: int = Field(default=50, ge=1, le=500)


@register
class GrepSkill(Skill):
    """纯 Python 实现的正则搜索，避免依赖系统 ripgrep。"""

    node_type = "file"
    name = "grep"
    description = "文件内容搜索：按正则搜索工作区内文件内容。输入 pattern 和 path，返回匹配行"
    input_schema = GrepInput
    required_permissions = [Permission.FILE_READ]

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        in_ = GrepInput.model_validate(inputs)
        root = Path(_expand_env_placeholders(in_.path)).expanduser()
        if not root.is_absolute():
            root = _workspace_root() / root
        if not root.exists():
            return {"ok": False, "error": f"path not found: {root}", "matches": []}

        try:
            regex = re.compile(
                in_.pattern,
                flags=re.IGNORECASE if in_.ignore_case else 0,
            )
        except re.error as e:
            return {"ok": False, "error": f"invalid regex: {e}", "matches": []}

        files: list[Path] = []
        if root.is_file():
            files = [root]
        else:
            for p in root.rglob("*"):
                if not p.is_file():
                    continue
                if in_.glob and not fnmatch.fnmatch(p.name, in_.glob):
                    continue
                files.append(p)

        matches: list[dict[str, Any]] = []
        truncated = False
        try:
            for fp in files:
                try:
                    text = fp.read_text(encoding="utf-8", errors="replace")
                except (OSError, UnicodeDecodeError) as e:
                    logger.debug(f"grep skip {fp}: {e}")
                    continue
                for line_no, line in enumerate(text.splitlines(), start=1):
                    m = regex.search(line)
                    if not m:
                        continue
                    matches.append(
                        {
                            "file": str(fp),
                            "line": line_no,
                            "text": _clip(line, 500),
                            "match": m.group(0)[:200],
                        }
                    )
                    if len(matches) >= in_.max_matches:
                        truncated = True
                        break
                if truncated:
                    break
        except OSError as e:
            return {"ok": False, "error": str(e), "matches": []}

        return {
            "ok": True,
            "matches": matches,
            "count": len(matches),
            "truncated": truncated,
        }


# ----------------------------------------------------------------------
# utils
# ----------------------------------------------------------------------


def _clip(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + f"\n... [truncated {len(text) - max_len} chars]"