"""File operation skills: read, write, edit — with PathGuard workspace restriction.

Red line: all file operations are restricted to WORKSPACE_ROOT.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.engine.schemas import Permission
from app.tools.base import Skill
from app.tools.registry import register

# ---------------------------------------------------------------------------
# PathGuard
# ---------------------------------------------------------------------------

def _workspace_root() -> Path:
    """Return the workspace root, guarding all file operations.

    安全红线：默认指向 backend/data/workspace/，绝不回退到项目根目录。
    否则 LLM 可经 file_read/grep 读到 backend/.env 里的全部密钥
    （FILE_READ 属于默认低危权限，任何节点自动具备）。
    """
    root = os.environ.get("WORKSPACE_ROOT", "")
    if root:
        return Path(root).resolve()
    # 默认：backend/data/workspace/（与 checkpoints 同级，物理隔离 .env 与源码）
    backend_dir = Path(__file__).resolve().parent.parent.parent
    return (backend_dir / "data" / "workspace").resolve()


def _resolve_and_guard(raw_path: str) -> Path:
    """Resolve path and enforce it stays within WORKSPACE_ROOT.

    Raises ValueError if the resolved path escapes the workspace.
    """
    ws = _workspace_root()
    if not ws.exists():
        ws.mkdir(parents=True, exist_ok=True)

    p = (ws / raw_path).resolve()

    # Must be under workspace root
    try:
        p.relative_to(ws)
    except ValueError:
        raise ValueError(
            f"path {raw_path!r} resolves to {p}, which is outside workspace {ws}"
        )
    return p


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class FileReadInput(BaseModel):
    path: str = Field(..., description="文件路径（相对于工作区根目录）")
    offset: int = Field(default=0, ge=0, description="起始行号（0-based）")
    limit: int = Field(default=200, ge=1, le=2000, description="最多读取行数")


class FileWriteInput(BaseModel):
    path: str = Field(..., description="文件路径（相对于工作区根目录）")
    content: str = Field(..., description="文件内容")


class FileEditInput(BaseModel):
    path: str = Field(..., description="文件路径（相对于工作区根目录）")
    old_string: str = Field(..., description="要替换的原始文本片段（需在文件中唯一匹配）")
    new_string: str = Field(default="", description="替换后的文本片段")


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------

@register
class FileReadSkill(Skill):
    """读取工作区内文件内容，支持分段读取。"""

    node_type = "file"
    name = "file_read"
    description = "读取文件：读取工作区内文件内容。输入 path（和可选 offset/limit），返回文件内容"
    input_schema = FileReadInput
    required_permissions = [Permission.FILE_READ]

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        in_ = FileReadInput.model_validate(inputs)
        try:
            target = _resolve_and_guard(in_.path)
        except ValueError as e:
            return {"ok": False, "error": str(e)}

        if not target.exists():
            return {"ok": False, "error": f"file not found: {in_.path}"}
        if not target.is_file():
            return {"ok": False, "error": f"not a file: {in_.path}"}

        try:
            text = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                text = target.read_text(encoding="gbk")
            except Exception as e:
                return {"ok": False, "error": f"cannot read file: {e}"}

        lines = text.splitlines()
        total_lines = len(lines)
        if in_.offset > 0:
            lines = lines[in_.offset:]
        if in_.limit > 0:
            lines = lines[:in_.limit]

        return {
            "ok": True,
            "path": str(target),
            "size": target.stat().st_size,
            "total_lines": total_lines,
            "lines": lines,
            "content": "\n".join(lines),
        }


@register
class FileWriteSkill(Skill):
    """原子写入文件到工作区。"""

    node_type = "file"
    name = "file_write"
    description = "写入文件：将内容写入工作区内文件（原子写入）。输入 path 和 content，返回写入结果"
    input_schema = FileWriteInput
    required_permissions = [Permission.FILE_WRITE]

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        in_ = FileWriteInput.model_validate(inputs)
        try:
            target = _resolve_and_guard(in_.path)
        except ValueError as e:
            return {"ok": False, "error": str(e)}

        target.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write: temp file + rename
        try:
            fd, tmp = tempfile.mkstemp(
                dir=str(target.parent), prefix="." + target.name + ".", suffix=".tmp"
            )
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(in_.content)
            os.replace(tmp, str(target))
        except Exception as e:
            return {"ok": False, "error": f"write failed: {e}"}

        return {
            "ok": True,
            "path": str(target),
            "size": target.stat().st_size,
            "lines": in_.content.count("\n") + 1,
        }


@register
class FileEditSkill(Skill):
    """精确替换文件中唯一匹配的文本片段。"""

    node_type = "file"
    name = "file_edit"
    description = (
        "编辑文件：精确替换文件中的文本片段。"
        "输入 path、old_string、new_string，返回替换结果"
    )
    input_schema = FileEditInput
    required_permissions = [Permission.FILE_WRITE]

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        in_ = FileEditInput.model_validate(inputs)
        try:
            target = _resolve_and_guard(in_.path)
        except ValueError as e:
            return {"ok": False, "error": str(e)}

        if not target.exists():
            return {"ok": False, "error": f"file not found: {in_.path}"}
        if not target.is_file():
            return {"ok": False, "error": f"not a file: {in_.path}"}

        try:
            original = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                original = target.read_text(encoding="gbk")
            except Exception as e:
                return {"ok": False, "error": f"cannot read file: {e}"}

        count = original.count(in_.old_string)
        if count == 0:
            return {
                "ok": False,
                "error": f"old_string not found in {in_.path}",
            }
        if count > 1:
            return {
                "ok": False,
                "error": (
                    f"old_string appears {count} times in {in_.path}. "
                    "must be unique for safe replacement"
                ),
            }

        modified = original.replace(in_.old_string, in_.new_string, 1)
        try:
            fd, tmp = tempfile.mkstemp(
                dir=str(target.parent), prefix="." + target.name + ".", suffix=".tmp"
            )
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(modified)
            os.replace(tmp, str(target))
        except Exception as e:
            return {"ok": False, "error": f"write failed: {e}"}

        return {
            "ok": True,
            "path": str(target),
            "replaced": True,
        }