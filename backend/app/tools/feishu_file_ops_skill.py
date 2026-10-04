"""Feishu File Ops Skill — operate files/folders in Feishu Drive.

Wraps FeishuClient drive file operations as a Skill tool so the LLM
can list folders, create folders, upload local files, and download
Feishu files during chat / automation workflows.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

from pydantic import BaseModel, Field

from app.tools.base import Skill
from app.tools.registry import register

logger = logging.getLogger(__name__)


class FeishuFileOpsInput(BaseModel):
    operation: str = Field(
        ...,
        description="操作类型：list(列出目录)、create_folder(创建文件夹)、upload(上传文件)、download(下载文件)",
    )
    folder_token: str = Field(
        default="",
        description="文件夹token。留空或填 root 表示云盘根目录。list/create_folder/upload 用。",
    )
    name: str = Field(default="", description="create_folder 时新建文件夹的名称")
    file_name: str = Field(default="", description="upload 时上传的文件名（含扩展名，如 report.pdf）")
    file_base64: str = Field(default="", description="upload 时上传文件的 base64 内容")
    file_token: str = Field(default="", description="download 时目标文件的 token")


@register
class FeishuFileOpsSkill(Skill):
    node_type = "feishu_file_ops"
    name = "feishu_file_ops"
    display_name = "飞书文件操作"
    description = (
        "操作飞书云盘文件：列出目录内容(list)、创建文件夹(create_folder)、"
        "上传本地文件到飞书(upload)、下载飞书文件(download)。"
        "通常用于整理飞书云盘、归档素材、读取飞书里的文件。"
    )
    platform = "feishu"
    trigger_words = ["飞书云盘", "飞书文件", "feishu drive", "lark drive", "云盘"]
    prompt_guidance = (
        "【飞书云盘操作】\n"
        "当用户消息包含「飞书云盘/云盘/飞书文件」时，必须用飞书工具，禁止使用 local_file_search 或 file_read。\n"
        "- 浏览飞书云盘 → feishu_file_ops(operation='list', folder_token='root')\n"
        "- 在云盘创建文件夹 → feishu_file_ops(operation='create_folder', folder_token=..., name=...)\n"
        "- 上传文件到飞书 → feishu_file_ops(operation='upload', folder_token=..., file_name=..., file_base64=...)\n"
        "- 下载飞书文件 → feishu_file_ops(operation='download', file_token=...)"
    )
    input_schema = FeishuFileOpsInput

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        operation = (inputs.get("operation") or "").strip().lower()
        folder_token = (inputs.get("folder_token") or "").strip()

        try:
            from app.config import get_settings
            from app.adapters.feishu import FeishuClient, FeishuAPIError

            settings = get_settings()
            if not (settings.feishu_app_id and settings.feishu_app_secret):
                return {
                    "ok": False,
                    "error": "飞书尚未配置。请先在 设置 > 飞书 填入 App ID 和 App Secret。",
                }
            client = FeishuClient(
                app_id=settings.feishu_app_id,
                app_secret=settings.feishu_app_secret,
            )
        except ImportError as e:
            return {"ok": False, "error": f"飞书模块不可用: {e}"}

        ctx = inputs.get("_context")
        user_id = ctx.user_id if ctx and hasattr(ctx, "user_id") else "default"
        logger.info(f"[FeishuFileOpsSkill] user_id={user_id}, operation={operation}, folder_token={folder_token}")

        try:
            if operation == "list":
                return await self._list(client, folder_token)
            if operation == "create_folder":
                return await self._create_folder(client, folder_token, inputs.get("name", ""))
            if operation == "upload":
                return await self._upload(client, folder_token, inputs)
            if operation == "download":
                return await self._download(client, inputs.get("file_token", ""))
            return {"ok": False, "error": f"未知操作: {operation}，可用：list/create_folder/upload/download"}
        except FeishuAPIError as e:
            logger.error(f"[FeishuFileOpsSkill] FeishuAPIError: {e}")
            return {"ok": False, "error": f"飞书API错误: {e.msg} (code={e.code})"}
        except Exception as e:
            logger.exception(f"[FeishuFileOpsSkill] {operation} failed")
            return {"ok": False, "error": f"操作失败: {e}"}

    async def _list(self, client: Any, folder_token: str) -> dict[str, Any]:
        result = await client.list_files(folder_token=folder_token)
        items = result.get("items", [])
        return {
            "ok": True,
            "folder_token": folder_token or "root",
            "count": len(items),
            "items": items,
            "has_more": result.get("has_more", False),
        }

    async def _create_folder(self, client: Any, folder_token: str, name: str) -> dict[str, Any]:
        name = (name or "").strip()
        if not name:
            return {"ok": False, "error": "create_folder 需要提供 name（新建文件夹名称）"}
        created = await client.create_folder(name=name, folder_token=folder_token)
        return {"ok": True, "name": name, **created}

    async def _upload(self, client: Any, folder_token: str, inputs: dict[str, Any]) -> dict[str, Any]:
        file_name = (inputs.get("file_name") or "").strip()
        file_base64 = (inputs.get("file_base64") or "").strip()
        if not file_name:
            return {"ok": False, "error": "upload 需要提供 file_name（文件名含扩展名）"}
        if not file_base64:
            return {"ok": False, "error": "upload 需要提供 file_base64（文件base64内容）"}

        raw = file_base64
        if "," in raw:
            raw = raw.split(",", 1)[1]
        try:
            file_data = base64.b64decode(raw)
        except Exception as e:
            return {"ok": False, "error": f"base64解码失败: {e}"}

        uploaded = await client.upload_file(
            file_name=file_name,
            file_data=file_data,
            parent_folder_token=folder_token,
        )
        return {"ok": True, "file_name": file_name, "size": len(file_data), **uploaded}

    async def _download(self, client: Any, file_token: str) -> dict[str, Any]:
        file_token = (file_token or "").strip()
        if not file_token:
            return {"ok": False, "error": "download 需要提供 file_token"}
        downloaded = await client.download_file(file_token=file_token)
        file_data = downloaded.get("file_data")
        file_name = downloaded.get("file_name") or ""
        if file_data is None:
            return {"ok": False, "error": "下载失败：未返回文件内容"}
        # 返回 base64，便于 LLM / 上层消费
        encoded = base64.b64encode(file_data).decode("ascii")
        return {
            "ok": True,
            "file_token": file_token,
            "file_name": file_name,
            "size": len(file_data),
            "file_base64": encoded,
        }