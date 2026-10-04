"""飞书适配器：封装 lark-oapi SDK 调用。

职责：
- 封装飞书开放平台 API（消息、文档、多维表格）
- 统一错误处理，SDK 返回非 0 时抛出 FeishuAPIError
- 所有方法均为 async，与 FastAPI 异步架构一致
- 适配器不包含业务逻辑，仅做 API 映射

设计原则：
- 适配器模式：与 deepseek.py / qwen_vl.py 保持一致架构
- SDK 升级只改此文件，业务层无感知
- 配置外部化：app_id / app_secret 从 Settings 注入
"""

from __future__ import annotations

import io
import json
import logging

import httpx
from typing import Any

import lark_oapi as lark
from lark_oapi.core.model.request_option import RequestOption
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
    CreateMessageResponse,
    CreateImageRequest,
    CreateImageRequestBody,
    CreateImageResponse,
)
from lark_oapi.api.docx.v1 import (
    GetDocumentRequest,
    GetDocumentResponse,
    RawContentDocumentRequest,
    RawContentDocumentResponse,
    CreateDocumentRequest,
    CreateDocumentRequestBody,
    CreateDocumentResponse,
    CreateDocumentBlockChildrenRequest,
    CreateDocumentBlockChildrenRequestBody,
    CreateDocumentBlockChildrenResponse,
    Block,
    Text,
    TextElement,
    TextRun,
)
from lark_oapi.api.wiki.v2 import (
    ListSpaceRequest,
    ListSpaceResponse,
    ListSpaceNodeRequest,
    ListSpaceNodeResponse,
    CreateSpaceNodeRequest,
    CreateSpaceNodeResponse,
    GetNodeSpaceRequest,
    GetNodeSpaceResponse,
    Node as WikiNode,
)
from lark_oapi.api.bitable.v1 import (
    ListAppTableRecordRequest,
    CreateAppTableRecordRequest,
    BatchCreateAppTableRecordRequest,
    BatchCreateAppTableRecordRequestBody,
    AppTableRecord,
)
from lark_oapi.api.drive.v1 import (
    ListFileRequest,
    ListFileResponse,
    CreateFolderFileRequest,
    CreateFolderFileRequestBody,
    CreateFolderFileResponse,
    UploadAllFileRequest,
    UploadAllFileRequestBody,
    UploadAllFileResponse,
    DownloadFileRequest,
    DownloadFileResponse,
)

logger = logging.getLogger(__name__)


class FeishuAPIError(Exception):
    """飞书 API 调用失败时抛出的异常。"""

    def __init__(self, code: int, msg: str, api_name: str = ""):
        self.code = code
        self.msg = msg
        self.api_name = api_name
        super().__init__(f"FeishuAPIError[{api_name}]: code={code}, msg={msg}")


class FeishuClient:
    """飞书适配器：封装 lark-oapi SDK 调用。

    用法：
        client = FeishuClient(app_id="cli_xxx", app_secret="xxx")
        await client.send_text("oc_xxx", "Hello")
        content = await client.get_document_content("do_xxx")
        records = await client.list_bitable_records("bxxx", "tblxxx")
    """

    def __init__(self, app_id: str, app_secret: str) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.client = lark.Client.builder() \
            .app_id(app_id) \
            .app_secret(app_secret) \
            .log_level(lark.LogLevel.WARNING) \
            .build()

    @staticmethod
    def _request_option(access_token: str | None = None) -> RequestOption | None:
        """为用户身份调用创建 SDK 请求选项；空值时沿用 tenant_access_token。"""
        if not access_token:
            return None
        option = RequestOption()
        option.user_access_token = access_token
        return option

    def _check_response(self, resp: Any, api_name: str) -> None:
        """统一检查飞书 API 响应，非 0 时抛出 FeishuAPIError。"""
        code = getattr(resp, "code", -1)
        msg = getattr(resp, "msg", "unknown")
        if code != 0:
            logger.error(f"[FeishuClient] {api_name} failed: code={code}, msg={msg}")
            raise FeishuAPIError(code=code, msg=msg, api_name=api_name)

    # ==================== 云盘文件 ====================

    @staticmethod
    def _normalize_folder_token(folder_token: str) -> str:
        """飞书云盘根目录用空串表示，普通文件夹传 folder_token。"""
        if not folder_token or folder_token == "root":
            return ""
        return folder_token

    async def list_files(
        self,
        folder_token: str = "",
        page_size: int = 50,
        page_token: str = "",
    ) -> dict[str, Any]:
        """列出云盘文件夹中的文件。

        Args:
            folder_token: 文件夹 token，空串或 "root" 表示根目录
            page_size: 每页数量（默认 50）
            page_token: 分页 token

        Returns:
            {"items": [...], "has_more": bool, "next_page_token": str}
        """
        folder_token = self._normalize_folder_token(folder_token)

        builder = ListFileRequest.builder().folder_token(folder_token).page_size(page_size)
        if page_token:
            builder = builder.page_token(page_token)

        req = builder.build()
        resp: ListFileResponse = await self.client.drive.v1.file.alist(req)
        self._check_response(resp, "drive.v1.file.alist")

        items = resp.data.files if resp.data and resp.data.files else []
        return {
            "items": [
                {
                    "file_token": item.token,
                    "name": item.name,
                    "type": item.type,
                    "url": item.url,
                    "created_time": item.created_time,
                }
                for item in items
            ],
            "has_more": bool(resp.data.has_more) if resp.data else False,
            "next_page_token": resp.data.next_page_token if resp.data else "",
        }

    async def create_folder(
        self,
        name: str,
        folder_token: str = "",
    ) -> dict[str, Any]:
        """在云盘指定位置创建文件夹。

        Args:
            name: 文件夹名称
            folder_token: 父文件夹 token，空串或 "root" 表示根目录

        Returns:
            {"folder_token": str, "url": str}
        """
        folder_token = self._normalize_folder_token(folder_token)

        req = CreateFolderFileRequest.builder() \
            .request_body(
                CreateFolderFileRequestBody.builder()
                .name(name)
                .folder_token(folder_token)
                .build()
            ).build()

        resp: CreateFolderFileResponse = await self.client.drive.v1.file.acreate_folder(req)
        self._check_response(resp, "drive.v1.file.acreate_folder")

        return {"folder_token": resp.data.token, "url": resp.data.url}

    async def upload_file(
        self,
        file_name: str,
        file_data: bytes,
        parent_folder_token: str = "",
    ) -> dict[str, Any]:
        """上传文件到云盘指定文件夹。

        Args:
            file_name: 文件名（含扩展名）
            file_data: 文件二进制内容
            parent_folder_token: 目标文件夹 token，空串或 "root" 表示根目录

        Returns:
            {"file_token": str, "url": str}
        """
        parent_folder_token = self._normalize_folder_token(parent_folder_token)

        content_type = "application/octet-stream"
        req = UploadAllFileRequest.builder() \
            .request_body(
                UploadAllFileRequestBody.builder()
                .file_name(file_name)
                .parent_type("explorer")
                .parent_node(parent_folder_token)
                .size(len(file_data))
                .build()
            ).build()

        req._files = {"file": (file_name, io.BytesIO(file_data), content_type)}

        resp: UploadAllFileResponse = await self.client.drive.v1.file.aupload_all(req)
        self._check_response(resp, "drive.v1.file.aupload_all")

        return {"file_token": resp.data.file_token, "url": resp.data.url}

    async def download_file(self, file_token: str) -> dict[str, Any]:
        """下载云盘文件内容。

        Args:
            file_token: 文件 token

        Returns:
            {"file_data": bytes, "file_name": str}
        """
        req = DownloadFileRequest.builder().file_token(file_token).build()

        resp: DownloadFileResponse = await self.client.drive.v1.file.adownload(req)
        self._check_response(resp, "drive.v1.file.adownload")

        return {"file_data": resp.file, "file_name": resp.file_name}

    # ==================== 消息 ====================

    async def send_text(
        self,
        receive_id: str,
        text: str,
        receive_id_type: str = "chat_id",
    ) -> dict[str, Any]:
        """发送文本消息到飞书群/用户。

        Args:
            receive_id: 接收者 ID（群 chat_id 或用户 open_id）
            text: 文本内容
            receive_id_type: receive_id 的类型，"chat_id" | "open_id"

        Returns:
            API 响应数据
        """
        req = CreateMessageRequest.builder() \
            .receive_id_type(receive_id_type) \
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(receive_id)
                .msg_type("text")
                .content(json.dumps({"text": text}))
                .build()
            ).build()

        resp: CreateMessageResponse = await self.client.im.v1.message.acreate(req)
        self._check_response(resp, "im.v1.message.acreate")
        return {"message_id": resp.data.message_id}

    async def send_card(
        self,
        receive_id: str,
        card: dict[str, Any],
        receive_id_type: str = "chat_id",
    ) -> dict[str, Any]:
        """发送卡片消息到飞书群/用户。

        Args:
            receive_id: 接收者 ID
            card: 卡片 JSON 结构
            receive_id_type: receive_id 的类型

        Returns:
            API 响应数据
        """
        req = CreateMessageRequest.builder() \
            .receive_id_type(receive_id_type) \
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(receive_id)
                .msg_type("interactive")
                .content(json.dumps(card))
                .build()
            ).build()

        resp: CreateMessageResponse = await self.client.im.v1.message.acreate(req)
        self._check_response(resp, "im.v1.message.acreate(card)")
        return {"message_id": resp.data.message_id}

    async def send_image(
        self,
        receive_id: str,
        image_data: bytes,
        file_ext: str = "png",
        receive_id_type: str = "chat_id",
    ) -> bool:
        """发送图片消息到飞书群/用户。

        流程：先上传图片获取 image_key，再发图片消息。

        Args:
            receive_id: 接收者 ID（群 chat_id 或用户 open_id）
            image_data: 图片二进制数据
            file_ext: 图片扩展名（png/jpg）
            receive_id_type: receive_id 的类型

        Returns:
            是否发送成功
        """
        try:
            import io

            image_type = "image/png" if file_ext == "png" else "image/jpeg"
            filename = f"card.{file_ext}"

            req = CreateImageRequest.builder() \
                .request_body(
                    CreateImageRequestBody.builder()
                    .image_type(image_type)
                    .build()
                ).build()

            req._files = {"image": (filename, io.BytesIO(image_data), image_type)}

            resp: CreateImageResponse = await self.client.im.v1.image.acreate(req)
            self._check_response(resp, "im.v1.image.acreate")

            image_key = resp.data.image_key

            msg_req = CreateMessageRequest.builder() \
                .receive_id_type(receive_id_type) \
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(receive_id)
                    .msg_type("image")
                    .content(json.dumps({"image_key": image_key}))
                    .build()
                ).build()

            msg_resp: CreateMessageResponse = await self.client.im.v1.message.acreate(msg_req)
            self._check_response(msg_resp, "im.v1.message.acreate(image)")
            return True
        except FeishuAPIError:
            raise
        except Exception as e:
            logger.error(f"[FeishuClient] send_image failed: {e}")
            return False

    # ==================== Wiki 知识库 ====================

    async def search_docs(
        self,
        query: str,
        access_token: str | None = None,
        page_size: int = 20,
        page_token: str = "",
        space_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """搜索当前访问身份可见的云文档与 Wiki（推荐使用 user_access_token）。"""
        if not query.strip():
            raise FeishuAPIError(1274001, "搜索关键词不能为空", "search.v2.doc_wiki.search")
        if not access_token:
            raise FeishuAPIError(
                1274011,
                "文档搜索需要已绑定飞书用户账号（user_access_token）",
                "search.v2.doc_wiki.search",
            )
        payload: dict[str, Any] = {
            "query": query[:30],
            "doc_filter": {},
            "wiki_filter": {},
            "page_size": min(max(page_size, 1), 20),
        }
        if page_token:
            payload["page_token"] = page_token
        if space_ids:
            payload["wiki_filter"]["space_ids"] = space_ids
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                "https://open.feishu.cn/open-apis/search/v2/doc_wiki/search",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
                json=payload,
            )
        data = response.json()
        if response.status_code >= 400 or data.get("code", 0) != 0:
            raise FeishuAPIError(
                int(data.get("code", response.status_code)),
                str(data.get("msg") or "飞书文档搜索失败"),
                "search.v2.doc_wiki.search",
            )
        result = data.get("data") or {}
        return {
            "items": result.get("items") or result.get("docs") or result.get("wiki_nodes") or [],
            "has_more": bool(result.get("has_more")),
            "page_token": result.get("page_token") or result.get("next_page_token") or "",
        }

    async def list_wiki_spaces(
        self,
        page_size: int = 50,
        page_token: str = "",
        access_token: str | None = None,
    ) -> dict[str, Any]:
        """列出应用可访问的知识库空间。

        Returns:
            {"items": [{"space_id", "name", "description"}], "has_more", "page_token"}
        """
        builder = ListSpaceRequest.builder().page_size(page_size)
        if page_token:
            builder = builder.page_token(page_token)

        req = builder.build()
        resp: ListSpaceResponse = await self.client.wiki.v2.space.alist(req, self._request_option(access_token))
        self._check_response(resp, "wiki.v2.space.alist")

        items = resp.data.items if resp.data and resp.data.items else []
        return {
            "items": [
                {
                    "space_id": s.space_id,
                    "name": s.name,
                    "description": s.description,
                }
                for s in items
            ],
            "has_more": bool(resp.data.has_more) if resp.data else False,
            "page_token": resp.data.page_token if resp.data else "",
        }

    async def list_wiki_nodes(
        self,
        space_id: str,
        parent_node_token: str = "",
        page_size: int = 50,
        page_token: str = "",
        access_token: str | None = None,
    ) -> dict[str, Any]:
        """列出知识库空间下的节点（parent_node_token 为空列顶层）。

        Returns:
            {"items": [{"node_token", "obj_token", "obj_type", "title", "has_child", "url"}], ...}
        """
        builder = ListSpaceNodeRequest.builder() \
            .space_id(space_id) \
            .page_size(page_size)
        if parent_node_token:
            builder = builder.parent_node_token(parent_node_token)
        if page_token:
            builder = builder.page_token(page_token)

        req = builder.build()
        resp: ListSpaceNodeResponse = await self.client.wiki.v2.space_node.alist(req, self._request_option(access_token))
        self._check_response(resp, "wiki.v2.space_node.alist")

        items = resp.data.items if resp.data and resp.data.items else []
        return {
            "items": [
                {
                    "node_token": n.node_token,
                    "obj_token": n.obj_token,
                    "obj_type": n.obj_type,
                    "title": n.title,
                    "has_child": bool(n.has_child) if n.has_child is not None else False,
                    "url": n.url,
                }
                for n in items
            ],
            "has_more": bool(resp.data.has_more) if resp.data else False,
            "page_token": resp.data.page_token if resp.data else "",
        }

    async def get_wiki_node_info(self, token: str, access_token: str | None = None) -> dict[str, Any]:
        """根据节点 token 查询知识库节点信息（用于 wiki 链接 token → 实际文档 token 的解析）。

        Returns:
            {"space_id", "node_token", "obj_token", "obj_type", "title", "has_child"}
        """
        req = GetNodeSpaceRequest.builder().token(token).build()
        resp: GetNodeSpaceResponse = await self.client.wiki.v2.space.aget_node(req, self._request_option(access_token))
        self._check_response(resp, "wiki.v2.space.aget_node")

        node = resp.data.node if resp.data else None
        if not node:
            raise FeishuAPIError(code=-1, msg="节点不存在", api_name="wiki.v2.space.aget_node")
        return {
            "space_id": node.space_id,
            "node_token": node.node_token,
            "obj_token": node.obj_token,
            "obj_type": node.obj_type,
            "title": node.title,
            "has_child": bool(node.has_child) if node.has_child is not None else False,
        }

    async def create_wiki_doc(
        self,
        space_id: str,
        title: str,
        parent_node_token: str = "",
        access_token: str | None = None,
    ) -> dict[str, Any]:
        """在知识库中新建文档（obj_type=docx），返回节点与文档 token。

        Args:
            space_id: 知识库空间 ID
            title: 文档标题
            parent_node_token: 父节点 token，空串表示挂在空间根目录

        Returns:
            {"node_token", "document_id", "title"}
        """
        body_builder = WikiNode.builder() \
            .obj_type("docx") \
            .title(title)
        if parent_node_token:
            body_builder = body_builder.parent_node_token(parent_node_token)

        req = CreateSpaceNodeRequest.builder() \
            .space_id(space_id) \
            .request_body(body_builder.build()) \
            .build()

        resp: CreateSpaceNodeResponse = await self.client.wiki.v2.space_node.acreate(req, self._request_option(access_token))
        self._check_response(resp, "wiki.v2.space_node.acreate")

        node = resp.data.node if resp.data else None
        if not node:
            raise FeishuAPIError(code=-1, msg="创建节点未返回数据", api_name="wiki.v2.space_node.acreate")
        return {
            "node_token": node.node_token,
            "document_id": node.obj_token,
            "title": node.title or title,
        }

    # ==================== 文档 ====================

    async def get_document_content(self, document_id: str, access_token: str | None = None) -> str:
        """获取飞书文档内容（Markdown 格式）。

        Args:
            document_id: 飞书文档 ID（从 URL 中提取）

        Returns:
            文档 Markdown 内容

        Raises:
            FeishuAPIError: API 调用失败
        """
        req = GetDocumentRequest.builder() \
            .document_id(document_id) \
            .build()

        resp: GetDocumentResponse = await self.client.docx.v1.document.aget(req, self._request_option(access_token))
        self._check_response(resp, "docx.v1.document.aget")

        content = resp.data.document.content
        return content if content else ""

    async def create_doc(
        self,
        title: str,
        folder_token: str = "",
        access_token: str | None = None,
    ) -> dict[str, Any]:
        """在云盘（或知识库外）新建空文档。

        Args:
            title: 文档标题
            folder_token: 所属文件夹 token，空串表示云盘根目录

        Returns:
            {"document_id", "title"}
        """
        body = CreateDocumentRequestBody.builder().title(title)
        if folder_token:
            body = body.folder_token(folder_token)

        req = CreateDocumentRequest.builder().request_body(body.build()).build()
        resp: CreateDocumentResponse = await self.client.docx.v1.document.acreate(req, self._request_option(access_token))
        self._check_response(resp, "docx.v1.document.acreate")

        doc = resp.data.document if resp.data else None
        if not doc:
            raise FeishuAPIError(code=-1, msg="创建文档未返回数据", api_name="docx.v1.document.acreate")
        return {"document_id": doc.document_id, "title": doc.title or title}

    async def read_doc_content(self, document_id: str, access_token: str | None = None) -> str:
        """读取文档正文纯文本内容（raw content）。

        Args:
            document_id: 文档 ID（docx 文档的 obj_token）

        Returns:
            文档纯文本正文
        """
        req = RawContentDocumentRequest.builder().document_id(document_id).build()
        resp: RawContentDocumentResponse = await self.client.docx.v1.document.araw_content(req, self._request_option(access_token))
        self._check_response(resp, "docx.v1.document.araw_content")

        content = resp.data.content if resp.data else ""
        return content or ""

    # docx block_type 枚举（飞书开放平台文档 Block 结构）
    _BLOCK_TYPE = {
        "text": 2, "h1": 3, "h2": 4, "h3": 5, "h4": 6,
        "bullet": 12, "ordered": 13, "code": 14, "quote": 15, "divider": 22,
    }
    # 每次追加 block 的数量上限（飞书 API 限制 50）
    _MAX_BLOCKS_PER_CALL = 50

    @staticmethod
    def _text_block(block_type: int, text: str):
        """构造一个纯文本内容块（Text + TextElement + TextRun）。"""
        text_body = Text.builder().elements([
            TextElement.builder()
            .text_run(TextRun.builder().content(text).build())
            .build()
        ]).build()
        return Block.builder().block_type(block_type).text(text_body).build()

    @classmethod
    def _markdown_to_blocks(cls, content: str) -> list:
        """将轻量 Markdown 转换为飞书文档 Block 列表。

        支持：#/##/###/#### 标题、-/*/• 无序列表、1. 有序列表、
        > 引用、``` 代码块、--- 分割线，其余按正文段落处理。
        行内样式（加粗/链接等）暂不转换，按纯文本写入。
        """
        blocks: list = []
        lines = content.splitlines()
        in_code = False
        code_lines: list[str] = []

        for raw_line in lines:
            line = raw_line.rstrip()
            if in_code:
                if line.strip().startswith("```"):
                    blocks.append(cls._text_block(cls._BLOCK_TYPE["code"], "\n".join(code_lines)))
                    code_lines = []
                    in_code = False
                else:
                    code_lines.append(raw_line)
                continue
            if line.strip().startswith("```"):
                in_code = True
                continue

            stripped = line.strip()
            if not stripped:
                continue
            if stripped in ("---", "***", "___"):
                blocks.append(Block.builder().block_type(cls._BLOCK_TYPE["divider"]).build())
            elif stripped.startswith("#### "):
                blocks.append(cls._text_block(cls._BLOCK_TYPE["h4"], stripped[5:]))
            elif stripped.startswith("### "):
                blocks.append(cls._text_block(cls._BLOCK_TYPE["h3"], stripped[4:]))
            elif stripped.startswith("## "):
                blocks.append(cls._text_block(cls._BLOCK_TYPE["h2"], stripped[3:]))
            elif stripped.startswith("# "):
                blocks.append(cls._text_block(cls._BLOCK_TYPE["h1"], stripped[2:]))
            elif stripped.startswith("> "):
                blocks.append(cls._text_block(cls._BLOCK_TYPE["quote"], stripped[2:]))
            elif len(stripped) > 2 and stripped[0] in "-*•" and stripped[1] == " ":
                blocks.append(cls._text_block(cls._BLOCK_TYPE["bullet"], stripped[2:].strip()))
            elif len(stripped) > 2 and stripped[0].isdigit() and stripped[1] in ".、" and (stripped[2] == " " or not stripped[2].isdigit()):
                blocks.append(cls._text_block(cls._BLOCK_TYPE["ordered"], stripped[2:].strip()))
            else:
                blocks.append(cls._text_block(cls._BLOCK_TYPE["text"], stripped))

        if in_code and code_lines:
            blocks.append(cls._text_block(cls._BLOCK_TYPE["code"], "\n".join(code_lines)))
        return blocks

    async def append_doc_content(
        self,
        document_id: str,
        content: str,
        access_token: str | None = None,
    ) -> dict[str, Any]:
        """向文档末尾追加内容（轻量 Markdown，自动转 Block，分批写入）。

        Args:
            document_id: 文档 ID
            content: Markdown 格式内容

        Returns:
            {"document_id", "appended_blocks"}
        """
        blocks = self._markdown_to_blocks(content)
        if not blocks:
            return {"document_id": document_id, "appended_blocks": 0}

        appended = 0
        for i in range(0, len(blocks), self._MAX_BLOCKS_PER_CALL):
            chunk = blocks[i:i + self._MAX_BLOCKS_PER_CALL]
            req = CreateDocumentBlockChildrenRequest.builder() \
                .document_id(document_id) \
                .block_id(document_id) \
                .request_body(
                    CreateDocumentBlockChildrenRequestBody.builder()
                    .children(chunk)
                    .build()
                ).build()

            resp: CreateDocumentBlockChildrenResponse = \
                await self.client.docx.v1.document_block_children.acreate(
                    req, self._request_option(access_token)
                )
            self._check_response(resp, "docx.v1.document_block_children.acreate")
            appended += len(chunk)

        return {"document_id": document_id, "appended_blocks": appended}

    # ==================== 多维表格 ====================

    async def list_bitable_records(
        self,
        app_token: str,
        table_id: str,
        page_size: int = 20,
        page_token: str = "",
        filter_str: str = "",
    ) -> list[dict[str, Any]]:
        """列出多维表格记录。

        Args:
            app_token: 多维表格 App Token
            table_id: 表格 ID
            page_size: 每页记录数
            page_token: 分页 token
            filter_str: 过滤条件

        Returns:
            记录列表
        """
        builder = ListAppTableRecordRequest.builder() \
            .app_token(app_token) \
            .table_id(table_id) \
            .page_size(page_size)

        if page_token:
            builder = builder.page_token(page_token)
        if filter_str:
            builder = builder.filter(filter_str)

        req = builder.build()
        resp = await self.client.bitable.v1.app_table_record.alist(req)
        self._check_response(resp, "bitable.v1.app_table_record.alist")

        items = resp.data.items if resp.data and resp.data.items else []
        return [
            {"record_id": item.record_id, "fields": item.fields}
            for item in items
        ]

    async def create_bitable_record(
        self,
        app_token: str,
        table_id: str,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        """创建单条多维表格记录。

        Args:
            app_token: 多维表格 App Token
            table_id: 表格 ID
            fields: 字段键值对

        Returns:
            创建的记录
        """
        record = AppTableRecord.builder().fields(fields).build()

        req = CreateAppTableRecordRequest.builder() \
            .app_token(app_token) \
            .table_id(table_id) \
            .request_body(record) \
            .build()

        resp = await self.client.bitable.v1.app_table_record.acreate(req)
        self._check_response(resp, "bitable.v1.app_table_record.acreate")

        return {"record_id": resp.data.record_id, "fields": resp.data.fields}

    async def batch_create_bitable_records(
        self,
        app_token: str,
        table_id: str,
        records: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """批量创建多维表格记录。

        Args:
            app_token: 多维表格 App Token
            table_id: 表格 ID
            records: 字段键值对列表

        Returns:
            创建的记录列表
        """
        record_models = [
            AppTableRecord.builder().fields(r).build()
            for r in records
        ]

        req = BatchCreateAppTableRecordRequest.builder() \
            .app_token(app_token) \
            .table_id(table_id) \
            .request_body(
                BatchCreateAppTableRecordRequestBody.builder()
                .records(record_models)
                .build()
            ).build()

        resp = await self.client.bitable.v1.app_table_record.abatch_create(req)
        self._check_response(resp, "bitable.v1.app_table_record.abatch_create")

        items = resp.data.records if resp.data and resp.data.records else []
        return [
            {"record_id": item.record_id, "fields": item.fields}
            for item in items
        ]