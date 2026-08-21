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
import re
import shlex
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.tools.base import Skill
from app.engine.schemas import Permission

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Bash
# ----------------------------------------------------------------------


class BashInput(BaseModel):
    command: str = Field(..., description="Shell command line")
    cwd: str = Field(default="", description="Working directory")
    timeout: int = Field(default=15, ge=1, le=120, description="Timeout in seconds")


class BashSkill(Skill):
    """运行 shell 命令。

    红线：
    - 默认拒绝，必须 PERMISSIONS_ALLOW=bash:exec 才放行。
    - 不允许 shell=True（命令注入风险），用 shlex.split 拆参。
    - 命令前缀白名单（默认 git/ls/cat/echo/python/pip/node/npm/rg/find/grep/glob）。
      其他命令直接拒绝，返回结构化错误给 LLM。
    - stdout/stderr 各截断 4KB，避免把 LLM 上下文撑爆。
    """

    name = "bash"
    description = "Run a shell command (read-only-ish whitelist, no shell=True)"
    input_schema = BashInput
    required_permissions = [Permission.BASH_EXEC]

    # 允许的可执行文件前缀（不含路径）
    ALLOWED_BINARIES: frozenset[str] = frozenset(
        {
            "git",
            "ls",
            "cat",
            "echo",
            "pwd",
            "python",
            "python3",
            "pip",
            "node",
            "npm",
            "npx",
            "rg",
            "find",
            "grep",
            "glob",
            "head",
            "tail",
            "wc",
        }
    )

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        in_ = BashInput.model_validate(inputs)
        try:
            argv = shlex.split(in_.command, posix=True)
        except ValueError as e:
            return {"ok": False, "error": f"shlex parse failed: {e}"}
        if not argv:
            return {"ok": False, "error": "empty command"}

        binary = Path(argv[0]).name.lower()
        if binary not in self.ALLOWED_BINARIES:
            return {
                "ok": False,
                "error": f"binary {binary!r} not in whitelist: {sorted(self.ALLOWED_BINARIES)}",
            }

        cwd = Path(in_.cwd).expanduser() if in_.cwd else None
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


class GlobSkill(Skill):
    """按 glob 模式列文件。"""

    name = "glob"
    description = "List files matching a glob pattern"
    input_schema = GlobInput
    required_permissions = [Permission.FILE_READ]

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        in_ = GlobInput.model_validate(inputs)
        root = Path(in_.path).expanduser()
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


class GrepSkill(Skill):
    """纯 Python 实现的正则搜索，避免依赖系统 ripgrep。"""

    name = "grep"
    description = "Search file contents by regex (no shell)"
    input_schema = GrepInput
    required_permissions = [Permission.FILE_READ]

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        in_ = GrepInput.model_validate(inputs)
        root = Path(in_.path).expanduser()
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