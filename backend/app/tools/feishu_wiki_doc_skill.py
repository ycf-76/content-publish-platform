"""Feishu Wiki/Doc Skill — 操作飞书 Wiki 知识库与云文档。

包装 FeishuClient 的 wiki v2 / docx v1 能力为 Skill 工具，
让智能体在对话/工作流中能够：
- 列出知识库空间与节点（找资料、找归档位置）
- 在知识库新建文档并写入 Markdown 内容（成果归档）
- 读取文档正文（wiki 链接 token 自动解析为文档 token）
- 向已有文档追加内容

与 feishu_file_ops（云盘文件）互补：本技能专注知识库与文档内容。
"""

from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from app.tools.base import Skill
from app.tools.registry import register

logger = logging.getLogger(__name__)

_WIKI_URL_RE = re.compile(r"https?://[^\s]*?(?:feishu\.cn|larksuite\.com)/(?:wiki|docx|docs)/([A-Za-z0-9]+)")


def _extract_token(raw: str) -> str:
    """从裸 token 或飞书链接中提取 token。"""
    raw = (raw or "").strip()
    m = _WIKI_URL_RE.search(raw)
    if m:
        return m.group(1)
    # 去掉 query 参数以防万一
    return raw.split("?")[0].strip()


class FeishuWikiDocInput(BaseModel):
    operation: str = Field(
        ...,
        description=(
            "操作类型：list_spaces(列出知识库空间)、list_nodes(列出知识库节点)、search_docs(搜索我的文档和知识库)、"
            "create_doc(在知识库新建文档并写入内容)、read_doc(读文档正文)、"
            "append_content(向已有文档追加内容)"
        ),
    )
    space_id: str = Field(default="", description="知识库空间 ID。list_nodes/create_doc 用；list_spaces 可不传")
    parent_node_token: str = Field(
        default="",
        description="父节点 token（可传 wiki 链接）。空=空间顶层。list_nodes/create_doc 用",
    )
    title: str = Field(default="", description="create_doc 时新文档的标题")
    query: str = Field(default="", description="search_docs 时搜索我的文档/知识库的关键词")
    content: str = Field(
        default="",
        description="create_doc/append_content 时的 Markdown 内容。支持 #/## 标题、列表、引用、代码块、--- 分割线",
    )
    doc_token: str = Field(
        default="",
        description="read_doc/append_content 时目标文档 token。可传文档 ID、wiki 节点 token 或飞书链接",
    )


@register
class FeishuWikiDocSkill(Skill):
    node_type = "feishu_wiki_doc"
    name = "feishu_wiki_doc"
    display_name = "飞书知识库/文档"
    description = (
        "操作飞书 Wiki 知识库与云文档：列出知识库空间(list_spaces)、浏览知识库节点树(list_nodes)、搜索我的文档和知识库(search_docs)、"
        "在知识库新建文档并写入 Markdown 内容(create_doc)、读取文档正文(read_doc)、"
        "向已有文档追加内容(append_content)。"
        "常用于查阅知识库资料、把创作成果/报告自动归档进飞书知识库。"
        "与 feishu_file_ops(云盘文件上传下载) 互补，本技能专注知识库与文档内容读写。"
    )
    platform = "feishu"
    trigger_words = ["飞书", "feishu", "lark", "wiki", "知识库", "云文档"]
    prompt_guidance = (
        "【飞书知识库操作 — 最高优先级】\n"
        "当用户消息包含「飞书/feishu/lark/wiki/知识库/云文档」时，必须用飞书工具，禁止使用 local_file_search 或 file_read。\n"
        "- 查看知识库/Wiki → feishu_wiki_doc(operation='list_spaces') 列出知识库空间，再用 list_nodes 浏览节点树\n"
        "- 搜索飞书文档 → feishu_wiki_doc(operation='search_docs', query='关键词')\n"
        "- 打开/读取飞书文档 → feishu_wiki_doc(operation='read_doc', doc_token='文档token或链接')\n"
        "- 在知识库新建文档 → feishu_wiki_doc(operation='create_doc', space_id=..., title=..., content=...)\n"
        "- 向文档追加内容 → feishu_wiki_doc(operation='append_content', doc_token=..., content=...)\n"
        "❌ 禁止：用户说「打开飞书wiki」时调 local_file_search 或 file_read"
    )
    input_schema = FeishuWikiDocInput

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        operation = (inputs.get("operation") or "").strip().lower()

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
        logger.info(f"[FeishuWikiDocSkill] user_id={user_id}, operation={operation}")
        access_token = await self._get_user_access_token(user_id)

        try:
            if operation == "list_spaces":
                return await self._list_spaces(client, access_token)
            if operation == "search_docs":
                return await self._search_docs(client, inputs, access_token)
            if operation == "list_nodes":
                return await self._list_nodes(client, inputs, access_token)
            if operation == "create_doc":
                return await self._create_doc(client, inputs, access_token)
            if operation == "read_doc":
                return await self._read_doc(client, inputs, access_token)
            if operation == "append_content":
                return await self._append_content(client, inputs, access_token)
            return {
                "ok": False,
                "error": f"未知操作: {operation}，可用：list_spaces/list_nodes/search_docs/create_doc/read_doc/append_content",
            }
        except FeishuAPIError as e:
            logger.error(f"[FeishuWikiDocSkill] FeishuAPIError: {e}")
            hint = self._permission_hint(e)
            return {"ok": False, "error": f"飞书API错误: {e.msg} (code={e.code}){hint}"}
        except Exception as e:
            logger.exception(f"[FeishuWikiDocSkill] {operation} failed")
            return {"ok": False, "error": f"操作失败: {e}"}

    # -------------------- 操作实现 --------------------

    async def _get_user_access_token(self, user_id: str) -> str | None:
        """按当前聊天用户取 user_access_token；未绑定时返回 None，回退应用身份。"""
        try:
            from app.tools.context_vars import current_db_session
            from app.services.feishu_oauth import get_valid_user_access_token
            db = current_db_session.get(None)
            if db is not None and user_id and user_id != "default":
                return await get_valid_user_access_token(db, user_id)
        except Exception as exc:
            logger.warning(f"[FeishuWikiDocSkill] user token unavailable, fallback tenant token: {exc}")
        return None

    async def _list_spaces(self, client: Any, access_token: str | None = None) -> dict[str, Any]:
        result = await client.list_wiki_spaces(access_token=access_token)
        items = result.get("items", [])
        return {
            "ok": True,
            "count": len(items),
            "items": items,
            "hint": "用 space_id 调 list_nodes 浏览节点，或调 create_doc 在该空间归档文档" if items else "",
        }

    async def _search_docs(self, client: Any, inputs: dict[str, Any], access_token: str | None = None) -> dict[str, Any]:
        query = (inputs.get("query") or inputs.get("content") or "").strip()
        if not query:
            return {"ok": False, "error": "search_docs 需要提供 query（搜索关键词）"}
        result = await client.search_docs(query, access_token=access_token)
        return {
            "ok": True,
            "query": query,
            "count": len(result.get("items", [])),
            "items": result.get("items", []),
            "has_more": result.get("has_more", False),
            "page_token": result.get("page_token", ""),
            "hint": "搜索结果中的 url/token 可传给 read_doc 读取正文；该接口按用户授权范围返回个人文档和知识库文档",
        }

    async def _list_nodes(self, client: Any, inputs: dict[str, Any], access_token: str | None = None) -> dict[str, Any]:
        space_id = (inputs.get("space_id") or "").strip()
        if not space_id:
            return {"ok": False, "error": "list_nodes 需要提供 space_id（可先用 list_spaces 获取）"}
        parent = _extract_token(inputs.get("parent_node_token", ""))
        result = await client.list_wiki_nodes(space_id, parent_node_token=parent, access_token=access_token)
        items = result.get("items", [])
        return {
            "ok": True,
            "space_id": space_id,
            "parent_node_token": parent,
            "count": len(items),
            "items": items,
            "hint": "has_child=true 的节点可传其 node_token 作为 parent_node_token 继续下钻；obj_type=docx 的节点可传 node_token 给 read_doc 读取正文",
        }

    async def _create_doc(self, client: Any, inputs: dict[str, Any], access_token: str | None = None) -> dict[str, Any]:
        space_id = (inputs.get("space_id") or "").strip()
        title = (inputs.get("title") or "").strip()
        content = inputs.get("content") or ""
        parent = _extract_token(inputs.get("parent_node_token", ""))
        if not space_id:
            return {"ok": False, "error": "create_doc 需要提供 space_id（可先用 list_spaces 获取）"}
        if not title:
            return {"ok": False, "error": "create_doc 需要提供 title（文档标题）"}
        if not content.strip():
            return {"ok": False, "error": "create_doc 需要提供 content（Markdown 内容，可为空标题+正文）"}

        created = await client.create_wiki_doc(space_id, title, parent_node_token=parent, access_token=access_token)
        document_id = created["document_id"]
        appended = await client.append_doc_content(document_id, content, access_token=access_token)
        return {
            "ok": True,
            "space_id": space_id,
            "node_token": created["node_token"],
            "document_id": document_id,
            "title": created["title"],
            "appended_blocks": appended.get("appended_blocks", 0),
            "hint": f"文档已创建并写入 {appended.get('appended_blocks', 0)} 个内容块，节点 token: {created['node_token']}",
        }

    async def _read_doc(self, client: Any, inputs: dict[str, Any], access_token: str | None = None) -> dict[str, Any]:
        token = _extract_token(inputs.get("doc_token", ""))
        if not token:
            return {"ok": False, "error": "read_doc 需要提供 doc_token（文档 ID、wiki 节点 token 或飞书链接均可）"}

        document_id, resolved = await self._resolve_document_id(client, token, access_token)
        content = await client.read_doc_content(document_id, access_token=access_token)
        return {
            "ok": True,
            "document_id": document_id,
            "resolved_from_wiki": resolved,
            "length": len(content),
            "content": content,
        }

    async def _append_content(self, client: Any, inputs: dict[str, Any], access_token: str | None = None) -> dict[str, Any]:
        token = _extract_token(inputs.get("doc_token", ""))
        content = inputs.get("content") or ""
        if not token:
            return {"ok": False, "error": "append_content 需要提供 doc_token（文档 ID、wiki 节点 token 或飞书链接均可）"}
        if not content.strip():
            return {"ok": False, "error": "append_content 需要提供 content（要追加的 Markdown 内容）"}

        document_id, resolved = await self._resolve_document_id(client, token, access_token)
        appended = await client.append_doc_content(document_id, content, access_token=access_token)
        return {
            "ok": True,
            "document_id": document_id,
            "resolved_from_wiki": resolved,
            "appended_blocks": appended.get("appended_blocks", 0),
        }

    # -------------------- 辅助 --------------------

    async def _resolve_document_id(self, client: Any, token: str, access_token: str | None = None) -> tuple[str, bool]:
        """把 wiki 节点 token / 链接解析为 docx 文档 ID。

        规则：wik 开头的 token 视为 wiki 节点，先查节点信息取 obj_token；
        其余（doxcn 等文档 token）直接当文档 ID 用。
        """
        if token.startswith("wik"):
            info = await client.get_wiki_node_info(token, access_token=access_token)
            obj_type = (info.get("obj_type") or "").lower()
            if obj_type and obj_type != "docx":
                raise ValueError(
                    f"该知识库节点是 {obj_type} 类型，不是文档（docx），无法读写正文。node_token={token}"
                )
            return info["obj_token"], True
        return token, False

    @staticmethod
    def _permission_hint(e: Any) -> str:
        """根据错误码给出权限排查提示。"""
        code = getattr(e, "code", 0)
        if code in (99991672, 99991661, 99991679, 230002, 1770002):
            return (
                "。可能缺少权限：请在飞书开放平台为应用开通 知识库(wiki:wiki) 与 文档(docx:document) "
                "相关权限并发布版本；同时确认目标知识库已把该应用添加为成员（知识库设置 > 成员设置 > 添加应用，授予可编辑权限）"
            )
        if code == 99991663:
            return "。无权限访问该 token 对应的资源，请确认文档/知识库已授权给应用"
        return ""