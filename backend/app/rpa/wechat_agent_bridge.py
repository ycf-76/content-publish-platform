"""微信机器人 ↔ 智能体融合桥。

职责：
  收到微信消息 → 意图识别 → 路由到对应动作 → 回复结果。

动作映射：
  - 链接采集（抖音/小红书/B站等）→ work_collector + 入库
  - AI 分析 → ChatAgent.process()
  - 搜索/写文/发布 → ChatAgent.process()
  - 普通聊天 → ChatAgent.process()（LLM 兜底）

设计原则：
  - 不修改 WeChatBotEngine 核心代码，通过 message_callback 接入
  - 不修改 ChatAgent 核心代码，直接调用 process()
  - 桥本身无状态，所有状态由 engine / agent / db 管理
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 动作类型
# ──────────────────────────────────────────────

class BridgeAction:
    COLLECT_LINK = "collect_link"
    SEND_LATEST = "send_latest"
    AGENT_CHAT = "agent_chat"
    PLAIN_REPLY = "plain_reply"


@dataclass
class BridgeResult:
    action: str
    reply: str
    data: dict[str, Any] | None = None


# ──────────────────────────────────────────────
# 链接检测
# ──────────────────────────────────────────────

_URL_PATTERN = re.compile(
    r"https?://[^\s<>\"]+|"
    r"(?:www\.)?[a-zA-Z0-9-]+\.(?:com|cn|net|org|io|cc|tv|me|dev|app|xyz|top)"
    r"/[^\s<>\"]*",
    re.IGNORECASE,
)

_PLATFORM_PATTERNS: dict[str, list[re.Pattern]] = {
    "xiaohongshu": [
        re.compile(r"(?:www\.)?xiaohongshu\.com"),
        re.compile(r"xhslink\.(?:com|cn)"),
    ],
    "douyin": [
        re.compile(r"(?:www\.)?douyin\.com"),
        re.compile(r"v\.douyin\.com"),
        re.compile(r"(?:www\.)?iesdouyin\.com"),
    ],
    "bilibili": [
        re.compile(r"(?:www\.)?bilibili\.com"),
        re.compile(r"b23\.tv"),
    ],
    "wechat_mp": [
        re.compile(r"mp\.weixin\.qq\.com"),
    ],
    "instagram": [
        re.compile(r"(?:www\.)?instagram\.com"),
    ],
}


def _extract_urls(text: str) -> list[str]:
    return _URL_PATTERN.findall(text)


def _detect_platform(url: str) -> str | None:
    for platform, patterns in _PLATFORM_PATTERNS.items():
        for pat in patterns:
            if pat.search(url):
                return platform
    return None


def _has_collectable_link(text: str) -> tuple[bool, str, str]:
    """检测文本中是否有可采集的链接。

    Returns:
        (has_link, url, platform)
    """
    urls = _extract_urls(text)
    for url in urls:
        platform = _detect_platform(url)
        if platform:
            return True, url, platform
    return False, "", ""


# ──────────────────────────────────────────────
# 意图分类（轻量规则 + LLM 兜底）
# ──────────────────────────────────────────────

_COLLECT_INTENT_PATTERNS = [
    re.compile(r"添加.*(?:到|进)(?:AI|分析|数据)"),
    re.compile(r"采集"),
    re.compile(r"收藏.*(?:链接|作品)"),
    re.compile(r"抓取"),
    re.compile(r"入库"),
]

_CHAT_INTENT_PATTERNS = [
    re.compile(r"搜(?:索|一下)"),
    re.compile(r"写.*(?:文章|笔记|文案|帖子)"),
    re.compile(r"分析(?:一下)?"),
    re.compile(r"调研"),
    re.compile(r"发布"),
    re.compile(r"帮我"),
    re.compile(r"来一篇"),
]

_SEND_LATEST_RE = re.compile(
    r"^(?:请|麻烦)?(?:把|将)?(?:刚才|刚|最近|上次)?"
    r"(?:写好的|写完的|写的|写出来|刚生成的|生成的|做完的|完成的)?"
    r"(?:那篇|这篇)?"
    r"(?:文案|内容|报告|稿子|文章|作品|笔记)?"
    r"(?:发(?:送)?(?:给)?我(?:微信)?|推送给我|推给我|发到(?:我)?微信)"
    r"[。.！!？?]?$"
)


def _classify_intent(text: str) -> tuple[str, dict[str, Any]]:
    """分类用户意图。

    Returns:
        (action, params)
        action: BridgeAction.COLLECT_LINK | BridgeAction.SEND_LATEST
                | BridgeAction.AGENT_CHAT | BridgeAction.PLAIN_REPLY
    """
    has_link, url, platform = _has_collectable_link(text)

    is_collect_intent = any(p.search(text) for p in _COLLECT_INTENT_PATTERNS)
    is_chat_intent = any(p.search(text) for p in _CHAT_INTENT_PATTERNS)

    if has_link and (is_collect_intent or not is_chat_intent):
        return BridgeAction.COLLECT_LINK, {"url": url, "platform": platform}

    if not has_link and _SEND_LATEST_RE.search(text):
        return BridgeAction.SEND_LATEST, {"message": text}

    if is_chat_intent:
        return BridgeAction.AGENT_CHAT, {"message": text}

    if has_link and not is_chat_intent:
        return BridgeAction.COLLECT_LINK, {"url": url, "platform": platform}

    return BridgeAction.AGENT_CHAT, {"message": text}


# ──────────────────────────────────────────────
# 核心桥
# ──────────────────────────────────────────────

class WeChatAgentBridge:
    """微信消息 → 智能体 桥接器。

    使用方式：
        bridge = WeChatAgentBridge(platform_user_id=user_id)
        engine.add_message_callback(bridge.on_message)

    当 WeChatBotEngine 收到微信消息时，bridge.on_message 被调用，
    自动完成意图识别 → 动作路由 → 回复。
    """

    def __init__(self, platform_user_id: str) -> None:
        self._platform_user_id = platform_user_id
        self._processing = False

    async def on_message(self, msg_dict: dict[str, Any]) -> None:
        """消息回调入口（由 WeChatBotEngine 触发）。"""
        if self._processing:
            logger.debug("[WeChatAgentBridge] 上一条消息仍在处理中，跳过")
            return

        text = msg_dict.get("text", "").strip()
        from_user_id = msg_dict.get("from_user_id", "")
        context_token = msg_dict.get("context_token", "")

        if not text:
            return

        if from_user_id == "bot":
            return

        self._processing = True
        try:
            result = await self._process_message(text, from_user_id, context_token)

            if result.reply:
                await self._send_reply(from_user_id, context_token, result.reply)

        except Exception as e:
            logger.error(f"[WeChatAgentBridge] 处理消息出错: {e}")
            await self._send_reply(
                from_user_id, context_token,
                f"处理时出错: {str(e)[:100]}",
            )
        finally:
            self._processing = False

    async def _process_message(
        self, text: str, from_user_id: str, context_token: str
    ) -> BridgeResult:
        """核心处理流程：意图分类 → 动作执行。"""
        action, params = _classify_intent(text)

        logger.info(
            f"[WeChatAgentBridge] 意图分类: action={action}, "
            f"text={text[:50]}..., params={params}"
        )

        if action == BridgeAction.COLLECT_LINK:
            return await self._handle_collect(params, from_user_id)

        if action == BridgeAction.SEND_LATEST:
            return await self._handle_send_latest(from_user_id)

        if action == BridgeAction.AGENT_CHAT:
            return await self._handle_agent_chat(text, from_user_id)

        return BridgeResult(action=BridgeAction.PLAIN_REPLY, reply="")

    async def _handle_collect(
        self, params: dict[str, Any], from_user_id: str
    ) -> BridgeResult:
        """处理链接采集：调用 work_collector 入库。"""
        url = params.get("url", "")
        platform = params.get("platform", "auto")

        if not url:
            return BridgeResult(
                action=BridgeAction.PLAIN_REPLY,
                reply="未检测到有效链接，请发送包含链接的消息。",
            )

        try:
            from app.services.work_collector import (
                collect_from_url,
                detect_platform,
                get_last_collect_errors,
                _clean_share_text,
            )
            from app.services.performance_collector import compute_performance_score
            from app.db.session import AsyncSessionLocal
            from app.db.models import PublishedContentPerformance
            from datetime import UTC, datetime

            cleaned_url = _clean_share_text(url)
            if platform == "auto" or not platform:
                platform = detect_platform(cleaned_url)

            result = await collect_from_url(url, platform)

            if not result:
                errors = get_last_collect_errors()
                detail = "；".join(errors) if errors else "所有采集方式均失败"
                return BridgeResult(
                    action=BridgeAction.COLLECT_LINK,
                    reply=f"采集失败: {detail[:200]}",
                    data={"url": url, "errors": errors},
                )

            score = compute_performance_score({
                "likes": result.get("likes", 0),
                "collects": result.get("collects", 0),
                "comments": result.get("comments", 0),
                "shares": result.get("shares", 0),
                "author_fans": result.get("author_fans", 1),
            })

            async with AsyncSessionLocal() as db:
                record = PublishedContentPerformance(
                    user_id=self._platform_user_id,
                    workflow_id="",
                    published_note_id=result.get("note_id", ""),
                    title=(result.get("title", "") or "")[:512],
                    content_text=result.get("content_text"),
                    tags=result.get("tags"),
                    cover_img_url=result.get("cover_img_url"),
                    images=result.get("image_urls", []),
                    platform=platform,
                    collected_likes=result.get("likes", 0),
                    collected_collects=result.get("collects", 0),
                    collected_comments=result.get("comments", 0),
                    collected_shares=result.get("shares", 0),
                    performance_score=score,
                    collected_at=datetime.now(UTC),
                    published_at=datetime.now(UTC),
                    content_status="collected",
                )
                db.add(record)
                await db.commit()
                await db.refresh(record)

            title = result.get("title", "无标题")
            likes = result.get("likes", 0)
            collects = result.get("collects", 0)
            platform_label = {"xiaohongshu": "小红书", "douyin": "抖音", "bilibili": "B站", "wechat_mp": "微信公众号", "instagram": "Instagram"}.get(platform, platform)

            reply = (
                f"已采集到AI数据分析中\n"
                f"平台: {platform_label}\n"
                f"标题: {title}\n"
                f"点赞: {likes} | 收藏: {collects}\n"
                f"性能分: {score:.2f}"
            )

            return BridgeResult(
                action=BridgeAction.COLLECT_LINK,
                reply=reply,
                data={"id": record.id, "title": title, "platform": platform},
            )

        except Exception as e:
            logger.error(f"[WeChatAgentBridge] 采集出错: {e}")
            return BridgeResult(
                action=BridgeAction.COLLECT_LINK,
                reply=f"采集出错: {str(e)[:100]}",
            )

    async def _handle_send_latest(self, from_user_id: str) -> BridgeResult:
        """把该用户最近一条完整文案直接发回微信，避免“发给我”被当成闲聊复读。"""
        try:
            from app.services import chat_file as chat_file_svc

            latest = await chat_file_svc.get_latest_copywrite(self._platform_user_id)
            title = str(latest.get("title", "")).strip() if latest else ""
            content = str(latest.get("content", "")).strip() if latest else ""

            if not latest or not (title or content):
                return BridgeResult(
                    action=BridgeAction.SEND_LATEST,
                    reply="还没有找到最近生成的完整文案。请先在 Web 端完成一次创作，再对我说“发给我”。",
                )

            parts: list[str] = []
            if title:
                parts.append(f"📌 {title}")
            if content:
                parts.append(content)
            return BridgeResult(
                action=BridgeAction.SEND_LATEST,
                reply="\n\n".join(parts),
                data={"title": title, "workflow_id": latest.get("workflow_id", "")},
            )
        except Exception as e:
            logger.error(f"[WeChatAgentBridge] 发送最近文案出错: {e}")
            return BridgeResult(
                action=BridgeAction.SEND_LATEST,
                reply=f"读取最近文案失败：{str(e)[:100]}",
            )

    async def _handle_agent_chat(
        self, text: str, from_user_id: str
    ) -> BridgeResult:
        """处理智能体对话：调用 ChatAgent.process()。"""
        try:
            from app.agents.chat_agent import ChatAgent
            from app.db.session import AsyncSessionLocal

            agent = ChatAgent()

            async with AsyncSessionLocal() as db:
                result = await agent.process(
                    message=text,
                    session_id=f"wechat_{self._platform_user_id}_{from_user_id}",
                    user_id=self._platform_user_id,
                    account_id="",
                    db=db,
                )

            reply = self._extract_reply_from_agent(result)

            if not reply and result.status == "chat":
                reply = await self._llm_simple_reply(text)

            if not reply:
                reply = "收到，我稍后处理。"

            return BridgeResult(
                action=BridgeAction.AGENT_CHAT,
                reply=reply,
                data={"status": result.status},
            )

        except Exception as e:
            logger.error(f"[WeChatAgentBridge] 智能体对话出错: {e}")
            return BridgeResult(
                action=BridgeAction.AGENT_CHAT,
                reply=f"智能体处理出错: {str(e)[:100]}",
            )

    def _extract_reply_from_agent(self, result: Any) -> str:
        """从 ChatAgent 的 ChatResult 中提取回复文本。"""
        if result.message:
            return result.message

        if result.output and result.output.output:
            output = result.output.output
            if isinstance(output, dict):
                if output.get("summary"):
                    parts = [output["summary"]]
                    if output.get("key_findings"):
                        findings = output["key_findings"]
                        if isinstance(findings, list) and findings:
                            parts.append("关键发现:")
                            for f in findings[:5]:
                                parts.append(f"  - {f}")
                    if output.get("recommendations"):
                        recs = output["recommendations"]
                        if isinstance(recs, list) and recs:
                            parts.append("建议:")
                            for r in recs[:3]:
                                if isinstance(r, dict):
                                    parts.append(f"  - {r.get('topic_direction', r)}")
                                else:
                                    parts.append(f"  - {r}")
                    return "\n".join(parts)[:800]

                if output.get("content"):
                    return str(output["content"])[:500]

                if output.get("title") and output.get("content_text"):
                    return f"标题: {output['title']}\n{str(output['content_text'])[:300]}"

                if output.get("title"):
                    return f"标题: {output['title']}"

        return ""

        if result.status == "chat":
            return ""

        if result.status == "workflow_started":
            return "工作流已启动，正在处理中..."

        if result.status == "awaiting_confirmation":
            return "需要确认操作，请在Web端确认。"

        return ""

    async def _llm_simple_reply(self, text: str) -> str:
        """当 ChatAgent 返回 chat 状态时，用 LLM 直接生成简短回复。"""
        try:
            from app.engine.factory import get_deepseek_llm

            llm = get_deepseek_llm(model="deepseek-v3")
            if llm is None:
                return "收到，我稍后处理。"

            messages = [
                {
                    "role": "system",
                    "content": (
                        "你是小红书创作助手，通过微信与用户对话。"
                        "请用简短自然的语言回复（100字以内）。"
                        "如果用户提到链接，告诉他可以发送链接来采集到AI数据分析。"
                    ),
                },
                {"role": "user", "content": text},
            ]
            resp = await llm._chat_impl(messages)
            content = resp.get("content", "")
            if content:
                import json
                try:
                    data = json.loads(content)
                    if isinstance(data, dict) and data.get("summary"):
                        return data["summary"][:200]
                except (json.JSONDecodeError, TypeError):
                    pass
                return content[:200]
            return "收到，我稍后处理。"
        except Exception as e:
            logger.warning(f"[WeChatAgentBridge] LLM 简单回复失败: {e}")
            return "收到，我稍后处理。"

    async def _send_reply(
        self, to_user_id: str, context_token: str, text: str
    ) -> None:
        """通过微信机器人发送回复。"""
        try:
            from app.rpa.wechat_bot_engine import get_wechat_engine

            engine = get_wechat_engine(self._platform_user_id)

            if not engine.is_logged_in:
                logger.warning("[WeChatAgentBridge] 机器人未登录，无法回复")
                return

            if not context_token:
                context_token = engine._client.get_context_token(to_user_id) if engine._client else ""

            if not context_token:
                logger.warning(f"[WeChatAgentBridge] 无 {to_user_id} 的 context_token，无法回复")
                return

            if len(text) > 4000:
                text = text[:3997] + "..."

            success = await engine.send_text(to_user_id, context_token, text)
            if success:
                logger.info(f"[WeChatAgentBridge] 回复已发送: to={to_user_id}")
            else:
                logger.warning(f"[WeChatAgentBridge] 回复发送失败: to={to_user_id}")

        except Exception as e:
            logger.error(f"[WeChatAgentBridge] 发送回复出错: {e}")


# ──────────────────────────────────────────────
# 桥注册表（按平台用户隔离）
# ──────────────────────────────────────────────

_bridge_registry: dict[str, WeChatAgentBridge] = {}


def get_or_create_bridge(platform_user_id: str) -> WeChatAgentBridge:
    """获取或创建指定用户的桥实例，并自动注册到对应的微信引擎。"""
    if platform_user_id not in _bridge_registry:
        bridge = WeChatAgentBridge(platform_user_id=platform_user_id)
        _bridge_registry[platform_user_id] = bridge

        from app.rpa.wechat_bot_engine import get_wechat_engine
        engine = get_wechat_engine(platform_user_id)
        engine.add_message_callback(bridge.on_message)

        logger.info(f"[WeChatAgentBridge] 已为用户 {platform_user_id} 创建桥并注册回调")

    return _bridge_registry[platform_user_id]


def remove_bridge(platform_user_id: str) -> None:
    """移除指定用户的桥实例。"""
    if platform_user_id in _bridge_registry:
        bridge = _bridge_registry.pop(platform_user_id)
        from app.rpa.wechat_bot_engine import get_wechat_engine
        engine = get_wechat_engine(platform_user_id)
        engine.remove_message_callback(bridge.on_message)
        logger.info(f"[WeChatAgentBridge] 已移除用户 {platform_user_id} 的桥")
