"""飞书机器人核心引擎

职责:
- 机器人生命周期管理（启动/停止）
- 状态维护和查询
- 飞书事件回调处理（消息接收、指令分发）
- 业务桥接（导入文档、导出数据）

设计原则:
- 注册表模式，按平台用户ID隔离，支持多用户并发
- 与 WeChatBotEngine 保持一致架构
- 异步设计，支持并发操作
- 通过 FeishuClient 适配器与飞书 API 交互，不直接调用 SDK
"""

import asyncio
import logging
from datetime import datetime
from enum import Enum
from typing import Any, Awaitable, Callable, Optional

from app.adapters.feishu import FeishuClient, FeishuAPIError

logger = logging.getLogger(__name__)


class FeishuBotStatus(Enum):
    """飞书机器人状态枚举"""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"


class FeishuBotState:
    """飞书机器人当前状态"""

    def __init__(self) -> None:
        self.status: FeishuBotStatus = FeishuBotStatus.STOPPED
        self.app_id: str = ""
        self.start_time: Optional[datetime] = None
        self.error_message: str = ""
        self.last_event_time: Optional[datetime] = None
        self.events_processed: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "app_id": self.app_id,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "uptime": str(datetime.now() - self.start_time) if self.start_time else None,
            "last_event_time": self.last_event_time.isoformat() if self.last_event_time else None,
            "events_processed": self.events_processed,
            "error": self.error_message,
        }


class FeishuBotEngine:
    """飞书机器人引擎（每个平台用户一个实例）

    核心功能:
    - 生命周期管理（启动/停止）
    - 状态查询和维护
    - 飞书事件回调处理
    - 指令分发（/import, /export, /status）
    - 业务桥接（导入文档到平台、导出数据到飞书）

    使用示例:
        engine = get_feishu_engine(user_id)
        await engine.start()
        status = engine.state
        await engine.handle_event(event_data)
        await engine.stop()
    """

    def __init__(
        self,
        user_id: str,
        client: FeishuClient,
        verification_token: str = "",
        encrypt_key: str = "",
        default_bitable_app_token: str = "",
        default_bitable_table_id: str = "",
    ) -> None:
        self._user_id = user_id
        self._client = client
        self._verification_token = verification_token
        self._encrypt_key = encrypt_key
        self._default_bitable_app_token = default_bitable_app_token
        self._default_bitable_table_id = default_bitable_table_id
        self.state = FeishuBotState()
        self.state.app_id = client.app_id
        self._command_handlers: dict[str, Any] = {
            "/import": self._cmd_import,
            "/export": self._cmd_export,
            "/status": self._cmd_status,
            "/help": self._cmd_help,
        }
        self._message_callbacks: list[Callable[[dict[str, Any]], Awaitable[None]]] = []

    @property
    def is_running(self) -> bool:
        return self.state.status == FeishuBotStatus.RUNNING

    async def start(self) -> None:
        """启动飞书机器人引擎。"""
        if self.is_running:
            logger.warning(f"[FeishuBot] Engine already running for user={self._user_id}")
            return

        self.state.status = FeishuBotStatus.STARTING
        try:
            self.state.start_time = datetime.now()
            self.state.status = FeishuBotStatus.RUNNING
            self.state.error_message = ""
            logger.info(f"[FeishuBot] Engine started for user={self._user_id}, app_id={self._client.app_id}")
        except Exception as e:
            self.state.status = FeishuBotStatus.ERROR
            self.state.error_message = str(e)
            logger.error(f"[FeishuBot] Start failed for user={self._user_id}: {e}")
            raise

    async def stop(self) -> None:
        """停止飞书机器人引擎。"""
        self.state.status = FeishuBotStatus.STOPPED
        logger.info(f"[FeishuBot] Engine stopped for user={self._user_id}")

    async def handle_event(self, event_data: dict[str, Any]) -> dict[str, Any]:
        """处理飞书事件回调。

        Args:
            event_data: 飞书事件订阅推送的 JSON 数据

        Returns:
            处理结果
        """
        if not self.is_running:
            logger.warning(f"[FeishuBot] Event received but engine not running, user={self._user_id}")
            return {"handled": False, "reason": "engine_not_running"}

        self.state.last_event_time = datetime.now()
        self.state.events_processed += 1

        header = event_data.get("header", {})
        event_type = header.get("event_type", "") or event_data.get("type", "")
        event = event_data.get("event", {})
        message = event.get("message", {})
        msg_type = message.get("message_type", "") or event.get("msg_type", "")

        if event_type == "im.message.receive_v1" and msg_type == "text":
            return await self._handle_text_message(event)

        logger.info(f"[FeishuBot] Unhandled event: type={event_type}, msg_type={msg_type}")
        return {"handled": True, "event_type": event_type, "action": "ignored"}

    async def _handle_text_message(self, event: dict[str, Any]) -> dict[str, Any]:
        """处理文本消息事件，提取指令并分发。"""
        sender = event.get("sender", {})
        sender_id = sender.get("sender_id", {}).get("open_id", "")
        message = event.get("message", {})
        chat_id = message.get("chat_id", "")

        content_str = message.get("content", "{}")
        try:
            import json
            content = json.loads(content_str) if isinstance(content_str, str) else content_str
            text = content.get("text", "").strip()
        except (json.JSONDecodeError, AttributeError):
            text = content_str if isinstance(content_str, str) else ""

        if not text:
            return {"handled": True, "action": "empty_message"}

        if text.startswith("/"):
            command, _, args = text.partition(" ")
            command = command.lower()
            handler = self._command_handlers.get(command)
            if handler:
                result = await handler(chat_id, sender_id, args.strip())
                return {"handled": True, "action": "command", "command": command, "result": result}
            else:
                await self._client.send_text(chat_id, f"未知指令: {command}\n输入 /help 查看可用指令")
                return {"handled": True, "action": "unknown_command", "command": command}

        msg_dict = {
            "text": text,
            "chat_id": chat_id,
            "sender_id": sender_id,
            "from_user_id": sender_id,
        }
        for cb in self._message_callbacks:
            try:
                await cb(msg_dict)
            except Exception as e:
                logger.error(f"[FeishuBot] Message callback failed: {e}")

        return {"handled": True, "action": "plain_text", "text": text}

    # ==================== 指令处理器 ====================

    async def _cmd_import(self, chat_id: str, sender_id: str, args: str) -> dict[str, Any]:
        """处理 /import 指令：导入飞书文档到平台。

        用法: /import <文档链接或文档ID>
        """
        if not args:
            await self._client.send_text(chat_id, "用法: /import <文档链接或文档ID>")
            return {"success": False, "error": "missing_args"}

        document_id = self._extract_document_id(args)
        if not document_id:
            await self._client.send_text(chat_id, "无法识别文档ID，请提供有效的飞书文档链接或ID")
            return {"success": False, "error": "invalid_document_id"}

        try:
            await self._client.send_text(chat_id, f"正在导入文档 {document_id}...")
            content = await self._client.get_document_content(document_id)

            if not content:
                await self._client.send_text(chat_id, "文档内容为空")
                return {"success": False, "error": "empty_content"}

            await self._client.send_text(
                chat_id,
                f"文档导入成功！内容长度: {len(content)} 字符\n"
                f"（后续将对接平台创作素材库）",
            )
            return {"success": True, "document_id": document_id, "content_length": len(content)}

        except FeishuAPIError as e:
            await self._client.send_text(chat_id, f"导入失败: {e.msg}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"[FeishuBot] Import failed: {e}")
            await self._client.send_text(chat_id, f"导入失败: {str(e)}")
            return {"success": False, "error": str(e)}

    async def _cmd_export(self, chat_id: str, sender_id: str, args: str) -> dict[str, Any]:
        """处理 /export 指令：导出平台数据到飞书多维表格。

        用法: /export <选题/文案ID>
        """
        app_token = self._default_bitable_app_token
        table_id = self._default_bitable_table_id

        if not app_token or not table_id:
            await self._client.send_text(chat_id, "未配置默认多维表格，请联系管理员")
            return {"success": False, "error": "no_bitable_config"}

        if not args:
            await self._client.send_text(chat_id, "用法: /export <选题/文案ID>\n（后续将对接平台数据）")
            return {"success": False, "error": "missing_args"}

        try:
            await self._client.send_text(chat_id, f"正在导出数据到多维表格...")
            result = await self._client.create_bitable_record(
                app_token=app_token,
                table_id=table_id,
                fields={"来源ID": args, "状态": "已导出", "导出时间": datetime.now().isoformat()},
            )
            await self._client.send_text(chat_id, f"导出成功！记录ID: {result.get('record_id', 'N/A')}")
            return {"success": True, "record_id": result.get("record_id")}

        except FeishuAPIError as e:
            await self._client.send_text(chat_id, f"导出失败: {e.msg}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"[FeishuBot] Export failed: {e}")
            await self._client.send_text(chat_id, f"导出失败: {str(e)}")
            return {"success": False, "error": str(e)}

    async def _cmd_status(self, chat_id: str, sender_id: str, args: str) -> dict[str, Any]:
        """处理 /status 指令：查看机器人状态。"""
        state = self.state.to_dict()
        status_text = (
            f"飞书机器人状态:\n"
            f"  状态: {state['status']}\n"
            f"  App ID: {state['app_id']}\n"
            f"  启动时间: {state['start_time'] or '未启动'}\n"
            f"  运行时长: {state['uptime'] or 'N/A'}\n"
            f"  已处理事件: {state['events_processed']}\n"
            f"  最后事件: {state['last_event_time'] or '无'}"
        )
        await self._client.send_text(chat_id, status_text)
        return {"success": True}

    async def _cmd_help(self, chat_id: str, sender_id: str, args: str) -> dict[str, Any]:
        """处理 /help 指令：显示帮助信息。"""
        help_text = (
            "飞书机器人指令:\n"
            "/import <文档链接> - 导入飞书文档作为创作素材\n"
            "/export <ID> - 导出平台数据到飞书多维表格\n"
            "/status - 查看机器人状态\n"
            "/help - 显示此帮助信息"
        )
        await self._client.send_text(chat_id, help_text)
        return {"success": True}

    # ==================== 工具方法 ====================

    @staticmethod
    def _extract_document_id(text: str) -> str:
        """从文本中提取飞书文档 ID。

        支持格式:
        - 纯文档ID: doxcnxxxxxx
        - 完整链接: https://xxx.feishu.cn/docx/doxcnxxxxxx
        - 知识库链接: https://xxx.feishu.cn/wiki/xxxxxx
        """
        text = text.strip()

        if text.startswith("http"):
            parts = text.rstrip("/").split("/")
            last_segment = parts[-1] if parts else ""
            if "?" in last_segment:
                last_segment = last_segment.split("?")[0]
            return last_segment if last_segment else ""

        return text

    async def import_document(self, document_id: str) -> dict[str, Any]:
        """手动导入飞书文档（API 调用，非指令触发）。"""
        return await self._cmd_import("", "", document_id)

    async def export_to_bitable(
        self,
        data: list[dict[str, Any]],
        app_token: str = "",
        table_id: str = "",
    ) -> dict[str, Any]:
        """手动导出数据到飞书多维表格（API 调用，非指令触发）。"""
        target_app_token = app_token or self._default_bitable_app_token
        target_table_id = table_id or self._default_bitable_table_id

        if not target_app_token or not target_table_id:
            return {"success": False, "error": "no_bitable_config"}

        try:
            if len(data) == 1:
                result = await self._client.create_bitable_record(
                    app_token=target_app_token,
                    table_id=target_table_id,
                    fields=data[0],
                )
                return {"success": True, "records": [result]}
            else:
                results = await self._client.batch_create_bitable_records(
                    app_token=target_app_token,
                    table_id=target_table_id,
                    records=data,
                )
                return {"success": True, "records": results}
        except FeishuAPIError as e:
            return {"success": False, "error": str(e)}

    def add_message_callback(self, callback: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        """注册消息回调，收到非指令消息时触发。"""
        self._message_callbacks.append(callback)

    def remove_message_callback(self, callback: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        """移除消息回调。"""
        if callback in self._message_callbacks:
            self._message_callbacks.remove(callback)


# ==================== 注册表：按用户 ID 隔离引擎实例 ====================

_engine_registry: dict[str, FeishuBotEngine] = {}


def get_feishu_engine(user_id: str) -> FeishuBotEngine:
    """获取或创建飞书机器人引擎实例（按用户隔离）。"""
    if user_id not in _engine_registry:
        from app.config import get_settings
        settings = get_settings()

        client = FeishuClient(
            app_id=settings.feishu_app_id,
            app_secret=settings.feishu_app_secret,
        )
        engine = FeishuBotEngine(
            user_id=user_id,
            client=client,
            verification_token=settings.feishu_verification_token,
            encrypt_key=settings.feishu_encrypt_key,
            default_bitable_app_token=settings.feishu_bitable_app_token,
            default_bitable_table_id=settings.feishu_bitable_table_id,
        )
        _engine_registry[user_id] = engine

    return _engine_registry[user_id]


def remove_feishu_engine(user_id: str) -> None:
    """移除飞书机器人引擎实例。"""
    if user_id in _engine_registry:
        del _engine_registry[user_id]