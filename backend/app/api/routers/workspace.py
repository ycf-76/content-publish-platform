"""工作区 API — 本地文件夹绑定 + Agent 文件操控。

核心思路（对标 Codex CLI / Claude Code）：
- 用户选本地文件夹 → 传绝对路径给后端 → 后端直接读本地文件系统
- 零上传、零同步，后端 Python 进程就在本机，直接 Path(path).read_text()
- Agent 通过 file_list / file_read / file_write / file_delete 工具操控
- 沙箱隔离：Agent 只能访问绑定的工作区根目录内的文件
"""
from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.api.schemas.common import StandardResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/workspace", tags=["workspace"])

WORKSPACE_META_ROOT = Path(os.getenv("WORKSPACE_META_ROOT", "data/workspaces"))


def _meta_dir(user_id: str) -> Path:
    d = WORKSPACE_META_ROOT / user_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _resolve_root(workspace_id: str, user_id: str) -> Path:
    meta_file = _meta_dir(user_id) / f"{workspace_id}.json"
    if not meta_file.exists():
        raise HTTPException(status_code=404, detail="工作区不存在")
    info = json.loads(meta_file.read_text(encoding="utf-8"))
    root = Path(info["local_path"])
    if not root.exists():
        raise HTTPException(status_code=404, detail=f"本地路径不存在: {info['local_path']}")
    return root


def _safe_path(base: Path, rel: str) -> Path:
    resolved = (base / rel).resolve()
    base_resolved = base.resolve()
    if not str(resolved).startswith(str(base_resolved)):
        raise HTTPException(status_code=403, detail="路径越界，只能访问工作区内的文件")
    return resolved


@router.post("/pick-folder")
async def pick_folder() -> StandardResponse[dict]:
    """弹出原生文件夹选择对话框。桌面端专属，后端在本机。

    Windows: 用 PowerShell FolderBrowserDialog
    Linux/Mac: 回退到 tkinter
    两种都在线程池里跑，不阻塞 asyncio 事件循环。
    """
    import asyncio
    import platform
    import subprocess

    system = platform.system()

    if system == "Windows":
        ps_script = r"""
Add-Type -AssemblyName System.Windows.Forms
$fb = New-Object System.Windows.Forms.FolderBrowserDialog
$fb.Description = '选择要绑定的本地文件夹'
$fb.ShowNewFolderButton = $false
if ($fb.ShowDialog() -eq 'OK') {
    Write-Output $fb.SelectedPath
} else {
    Write-Output ''
}
"""

        def _run_powershell() -> str:
            try:
                proc = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", ps_script],
                    capture_output=True, text=True, timeout=120,
                )
                return proc.stdout.strip()
            except Exception as e:
                logger.warning("pick-folder powershell failed: %s", e)
                return ""

        loop = asyncio.get_event_loop()
        selected = await loop.run_in_executor(None, _run_powershell)
    else:
        def _run_tkinter() -> str:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            sel = filedialog.askdirectory(title="选择要绑定的本地文件夹")
            root.destroy()
            return sel

        loop = asyncio.get_event_loop()
        selected = await loop.run_in_executor(None, _run_tkinter)

    if not selected:
        return StandardResponse(data={"path": "", "name": "", "cancelled": True})

    return StandardResponse(data={"path": selected, "name": Path(selected).name})


class BindWorkspaceRequest(BaseModel):
    local_path: str = Field(description="本地文件夹绝对路径")
    name: str | None = Field(default=None, description="工作区名称，默认取文件夹名")


@router.post("/bind")
async def bind_workspace(
    payload: BindWorkspaceRequest,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict]:
    """绑定本地文件夹为工作区。零上传，后端直接访问本机路径。"""
    local_path = Path(payload.local_path)
    if not local_path.exists():
        raise HTTPException(status_code=400, detail=f"路径不存在: {payload.local_path}")
    if not local_path.is_dir():
        raise HTTPException(status_code=400, detail=f"不是文件夹: {payload.local_path}")

    import uuid
    ws_id = uuid.uuid4().hex[:12]
    name = payload.name or local_path.name
    meta = {
        "id": ws_id,
        "name": name,
        "local_path": str(local_path.resolve()),
        "bound_at": datetime.now(UTC).isoformat(),
    }
    meta_file = _meta_dir(user_id) / f"{ws_id}.json"
    meta_file.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

    file_count = sum(1 for _ in local_path.rglob("*") if _.is_file())

    return StandardResponse(data={
        "id": ws_id,
        "name": name,
        "local_path": str(local_path.resolve()),
        "file_count": file_count,
    })


@router.get("")
async def list_workspaces(
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict]:
    meta_dir = _meta_dir(user_id)
    result = []
    for f in sorted(meta_dir.glob("*.json")):
        try:
            info = json.loads(f.read_text(encoding="utf-8"))
            local_path = Path(info.get("local_path", ""))
            info["accessible"] = local_path.exists()
            result.append(info)
        except Exception:
            pass
    return StandardResponse(data={"workspaces": result})


@router.delete("/{workspace_id}")
async def unbind_workspace(
    workspace_id: str,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict]:
    meta_file = _meta_dir(user_id) / f"{workspace_id}.json"
    if not meta_file.exists():
        raise HTTPException(status_code=404, detail="工作区不存在")
    meta_file.unlink()
    return StandardResponse(data={"deleted": workspace_id})


class RenameWorkspaceRequest(BaseModel):
    name: str = Field(description="新的工作区名称（仅显示名，不改本地目录名）")


@router.patch("/{workspace_id}")
async def rename_workspace(
    workspace_id: str,
    payload: RenameWorkspaceRequest,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict]:
    """重命名工作区（只改显示名，本地目录名不变）。"""
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="名称不能为空")
    meta_file = _meta_dir(user_id) / f"{workspace_id}.json"
    if not meta_file.exists():
        raise HTTPException(status_code=404, detail="工作区不存在")
    info = json.loads(meta_file.read_text(encoding="utf-8"))
    info["name"] = name
    meta_file.write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
    return StandardResponse(data={"id": workspace_id, "name": name, "local_path": info.get("local_path")})


@router.get("/{workspace_id}/list")
async def list_files(
    workspace_id: str,
    path: str = Query(default=""),
    depth: int = Query(default=1, ge=1, le=3),
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict]:
    """列出工作区文件。直接读本地文件系统，零延迟。"""
    root = _resolve_root(workspace_id, user_id)
    target = _safe_path(root, path) if path else root
    if not target.exists():
        return StandardResponse(data={"files": [], "dirs": []})

    files = []
    dirs = []

    def _scan(directory: Path, prefix: str = ""):
        try:
            items = sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            return
        for p in items:
            if p.name.startswith("."):
                continue
            rel = str(p.relative_to(root))
            if p.is_dir():
                dirs.append({"name": p.name, "path": rel})
                if depth > 1:
                    _scan(p, rel)
            else:
                try:
                    size = p.stat().st_size
                except OSError:
                    size = 0
                files.append({"name": p.name, "path": rel, "size": size})

    _scan(target)
    return StandardResponse(data={"files": files, "dirs": dirs, "root": str(root)})


class FileReadRequest(BaseModel):
    path: str = Field(description="相对于工作区根的文件路径")


@router.post("/{workspace_id}/read")
async def read_file(
    workspace_id: str,
    payload: FileReadRequest,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict]:
    """Agent 读文件。直接读本地文件系统。"""
    root = _resolve_root(workspace_id, user_id)
    target = _safe_path(root, payload.path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    try:
        content = target.read_text(encoding="utf-8")
        return StandardResponse(data={"path": payload.path, "content": content, "size": target.stat().st_size})
    except UnicodeDecodeError:
        import base64
        raw = target.read_bytes()
        return StandardResponse(data={"path": payload.path, "content_base64": base64.b64encode(raw).decode(), "size": len(raw), "binary": True})


class FileWriteRequest(BaseModel):
    path: str = Field(description="相对于工作区根的文件路径")
    content: str = Field(description="文件内容（文本）")


@router.post("/{workspace_id}/write")
async def write_file(
    workspace_id: str,
    payload: FileWriteRequest,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict]:
    """Agent 写文件。直接写本地文件系统。"""
    root = _resolve_root(workspace_id, user_id)
    target = _safe_path(root, payload.path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(payload.content, encoding="utf-8")
    return StandardResponse(data={"path": payload.path, "size": target.stat().st_size})


@router.delete("/{workspace_id}/delete")
async def delete_file(
    workspace_id: str,
    path: str = Query(...),
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict]:
    """Agent 删文件。直接操作本地文件系统。"""
    root = _resolve_root(workspace_id, user_id)
    target = _safe_path(root, path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    return StandardResponse(data={"deleted": path})


class FileSearchRequest(BaseModel):
    pattern: str = Field(default="*", description="glob 模式，如 *.py 或 **/*.md")
    max_results: int = Field(default=50, ge=1, le=200)


@router.post("/{workspace_id}/search")
async def search_files(
    workspace_id: str,
    payload: FileSearchRequest,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict]:
    """Agent 搜索文件。glob 模式匹配。"""
    root = _resolve_root(workspace_id, user_id)
    results = []
    for p in root.glob(payload.pattern):
        if len(results) >= payload.max_results:
            break
        try:
            resolved = p.resolve()
            if not str(resolved).startswith(str(root.resolve())):
                continue
            rel = str(p.relative_to(root))
            results.append({
                "name": p.name,
                "path": rel,
                "size": p.stat().st_size if p.is_file() else 0,
                "is_dir": p.is_dir(),
            })
        except (PermissionError, OSError):
            continue
    return StandardResponse(data={"results": results, "count": len(results)})