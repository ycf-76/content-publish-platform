"""飞书机器人 ↔ 智能体融合桥。

职责：
  收到飞书消息 → 意图识别 → 路由到对应动作 → 回复结果。

动作映射：
  - 链接采集（抖音/小红书/B站等）→ work_collector + 入库
  - AI 分析 → ChatAgent.process()
  - 搜索/写文/发布 → ChatAgent.process()
  - 普通聊天 → ChatAgent.process()（LLM 兜底）

设计原则：
  - 不修改 FeishuBotEngine 核心代码，通过 message_callback 接入
  - 不修改 ChatAgent 核心代码，直接调用 process()
  - 桥本身无状态，所有状态由 engine / agent / db 管理
  - 与 WeChatAgentBridge 保持一致架构，适配飞书消息格式
  - 支持 BlockKit 卡片消息提升用户体验
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


class BridgeAction:
    COLLECT_LINK = "collect_link"
    AGENT_CHAT = "agent_chat"
    PLAIN_REPLY = "plain_reply"


@dataclass
class BridgeResult:
    action: str
    reply: str
    data: dict[str, Any] | None = None
    card: dict[str, Any] | None = None


class BlockKitBuilder:
    """BlockKit 卡片消息构建器。

    用于生成飞书交互式卡片，提升用户体验。
    支持：采集结果卡、创作结果卡、对话卡、错误卡等。
    """

    @staticmethod
    def collect_result_card(title: str, platform: str, likes: int, collects: int, score: float, url: str = "") -> dict:
        """构建链接采集结果卡片。"""
        platform_emoji = {"xiaohongshu": "📕", "douyin": "🎵", "bilibili": "📺", "instagram": "📸"}.get(platform, "🔗")
        platform_label = {"xiaohongshu": "小红书", "douyin": "抖音", "bilibili": "B站", "instagram": "Instagram"}.get(platform, platform)

        elements = [
            {"tag": "markdown", "content": f"**{platform_emoji} 标题**: {title[:50]}"},
            {"tag": "hr"},
            {
                "tag": "column_set",
                "flex_mode": "none",
                "background_style": "grey",
                "columns": [
                    {
                        "tag": "column",
                        "width": "weighted",
                        "weight": 1,
                        "elements": [
                            {"tag": "markdown", "content": f"**👍 点赞**\n{likes}"}
                        ]
                    },
                    {
                        "tag": "column",
                        "width": "weighted",
                        "weight": 1,
                        "elements": [
                            {"tag": "markdown", "content": f"**⭐ 收藏**\n{collects}"}
                        ]
                    },
                    {
                        "tag": "column",
                        "width": "weighted",
                        "weight": 1,
                        "elements": [
                            {"tag": "markdown", "content": f"**📊 性能分**\n{score:.1f}"}
                        ]
                    }
                ]
            }
        ]

        if url:
            elements.append({
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "🔗 查看原文"},
                        "url": url,
                        "type": "primary"
                    }
                ]
            })

        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"{platform_emoji} 采集成功"},
                "template": "blue"
            },
            "elements": elements
        }

    @staticmethod
    def creation_result_card(title: str, content: str, word_count: int = 0, tags: list[str] | None = None) -> dict:
        """构建文案创作结果卡片。"""
        elements = [
            {"tag": "markdown", "content": f"**📝 标题**\n{title}"}
        ]

        if content:
            preview = content[:200] + ("..." if len(content) > 200 else "")
            elements.append({"tag": "hr"})
            elements.append({"tag": "markdown", "content": f"**✍️ 正文预览**\n{preview}"})

        meta_items = [f"📊 {word_count}字"]
        if tags:
            meta_items.append(f"🏷️ {' '.join(tags[:3])}")

        elements.append({"tag": "hr"})
        elements.append({
            "tag": "column_set",
            "flex_mode": "none",
            "background_style": "grey",
            "columns": [
                {
                    "tag": "column",
                    "width": "weighted",
                    "weight": 1,
                    "elements": [{"tag": "markdown", "content": meta_items[0]}]
                },
                *([{
                    "tag": "column",
                    "width": "weighted",
                    "weight": 1,
                    "elements": [{"tag": "markdown", "content": meta_items[1]}]
                }] if len(meta_items) > 1 else [])
            ]
        })

        elements.append({
            "tag": "action",
            "actions": [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "✅ 确认发布"},
                    "value": json.dumps({"action": "approve", "title": title}),
                    "type": "primary"
                },
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "🔄 重新生成"},
                    "value": json.dumps({"action": "regenerate"}),
                    "type": "default"
                }
            ]
        })

        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": "✨ 文案已生成"},
                "template": "green"
            },
            "elements": elements
        }

    @staticmethod
    def chat_card(reply_text: str, status: str = "chat") -> dict:
        """构建普通对话卡片。"""
        emoji_map = {
            "chat": "💬",
            "workflow_started": "⚙️",
            "awaiting_confirmation": "⏳",
            "error": "❌"
        }
        template_map = {
            "chat": "blue",
            "workflow_started": "orange",
            "awaiting_confirmation": "yellow",
            "error": "red"
        }

        return {
            "config": {"wide_screen_mode": False},
            "header": {
                "title": {"tag": "plain_text", "content": f"{emoji_map.get(status, '💬')} 创作助手"},
                "template": template_map.get(status, "blue")
            },
            "elements": [
                {"tag": "markdown", "content": reply_text[:2000]}
            ]
        }

    @staticmethod
    def error_card(error_msg: str) -> dict:
        """构建错误提示卡片。"""
        return {
            "config": {"wide_screen_mode": False},
            "header": {
                "title": {"tag": "plain_text", "content": "❌ 操作失败"},
                "template": "red"
            },
            "elements": [
                {"tag": "markdown", "content": error_msg[:500]},
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "🔄 重试"},
                            "value": json.dumps({"action": "retry"}),
                            "type": "primary"
                        }
                    ]
                }
            ]
        }


    @staticmethod
    def task_confirm_card(
        plan_title: str,
        day_index: int,
        node: str,
        title: str,
        content_preview: str,
        value: dict[str, Any] | None = None,
    ) -> dict:
        """构建任务清单人工确认卡片（三按钮：确认发布 / 打回重做 / 跳过本条）。

        卡片回调（card.action.trigger）由 api/routers/feishu_bot.py 处理：
        value 需含 biz="task_plan" + workflow_id/task_item_id/plan_id，
        回调侧按按钮 value 里的 action（approve/regenerate/skip）路由。
        """
        base_value = dict(value or {})
        node_label = {
            "image_review": "图片审核",
            "final_review": "终审",
            "publish": "发布确认",
        }.get(node, node)

        elements = [
            {"tag": "markdown", "content": f"**清单**：{plan_title[:50]}（第 {day_index} 天）"},
            {"tag": "markdown", "content": f"**当前环节**：{node_label}"},
            {"tag": "hr"},
            {"tag": "markdown", "content": f"**标题**\n{title}"},
        ]
        if content_preview:
            elements.append({"tag": "markdown", "content": f"**正文预览**\n{content_preview}"})

        elements.append({
            "tag": "action",
            "actions": [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "确认发布"},
                    "value": json.dumps({**base_value, "action": "approve"}, ensure_ascii=False),
                    "type": "primary",
                },
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "打回重做"},
                    "value": json.dumps({**base_value, "action": "regenerate"}, ensure_ascii=False),
                    "type": "default",
                },
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "跳过本条"},
                    "value": json.dumps({**base_value, "action": "skip"}, ensure_ascii=False),
                    "type": "danger",
                },
            ],
        })

        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": "定时任务待确认"},
                "template": "orange",
            },
            "elements": elements,
        }


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
    urls = _extract_urls(text)
    for url in urls:
        platform = _detect_platform(url)
        if platform:
            return True, url, platform
    return False, "", ""


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


def _classify_intent(text: str) -> tuple[str, dict[str, Any]]:
    has_link, url, platform = _has_collectable_link(text)

    is_collect_intent = any(p.search(text) for p in _COLLECT_INTENT_PATTERNS)
    is_chat_intent = any(p.search(text) for p in _CHAT_INTENT_PATTERNS)

    if has_link and (is_collect_intent or not is_chat_intent):
        return BridgeAction.COLLECT_LINK, {"url": url, "platform": platform}

    if is_chat_intent:
        return BridgeAction.AGENT_CHAT, {"message": text}

    if has_link and not is_chat_intent:
        return BridgeAction.COLLECT_LINK, {"url": url, "platform": platform}

    return BridgeAction.AGENT_CHAT, {"message": text}


class FeishuAgentBridge:
    """飞书消息 → 智能体 桥接器。

    使用方式：
        bridge = FeishuAgentBridge(platform_user_id=user_id)
        engine.add_message_callback(bridge.on_message)

    当 FeishuBotEngine 收到飞书消息时，bridge.on_message 被调用，
    自动完成意图识别 → 动作路由 → 回复。
    """

    def __init__(self, platform_user_id: str) -> None:
        self._platform_user_id = platform_user_id
        self._processing = False

    async def on_message(self, msg_dict: dict[str, Any]) -> None:
        if self._processing:
            logger.debug("[FeishuAgentBridge] 上一条消息仍在处理中，跳过")
            return

        text = msg_dict.get("text", "").strip()
        chat_id = msg_dict.get("chat_id", "")
        sender_id = msg_dict.get("sender_id", "") or msg_dict.get("from_user_id", "")

        if not text:
            return

        self._processing = True
        try:
            result = await self._process_message(text, chat_id, sender_id)

            if result.card:
                await self._send_card(chat_id, result.card)
            elif result.reply:
                await self._send_reply(chat_id, result.reply)

        except Exception as e:
            logger.error(f"[FeishuAgentBridge] 处理消息出错: {e}")
            error_card = BlockKitBuilder.error_card(str(e)[:100])
            await self._send_card(chat_id, error_card)
        finally:
            self._processing = False

    async def _process_message(
        self, text: str, chat_id: str, sender_id: str
    ) -> BridgeResult:
        action, params = _classify_intent(text)

        logger.info(
            f"[FeishuAgentBridge] 意图分类: action={action}, "
            f"text={text[:50]}..., params={params}"
        )

        if action == BridgeAction.COLLECT_LINK:
            return await self._handle_collect(params, chat_id)

        if action == BridgeAction.AGENT_CHAT:
            return await self._handle_agent_chat(text, chat_id, sender_id)

        return BridgeResult(action=BridgeAction.PLAIN_REPLY, reply="")

    async def _handle_collect(
        self, params: dict[str, Any], chat_id: str
    ) -> BridgeResult:
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

            card = BlockKitBuilder.collect_result_card(
                title=title,
                platform=platform,
                likes=likes,
                collects=collects,
                score=score,
                url=url
            )

            return BridgeResult(
                action=BridgeAction.COLLECT_LINK,
                reply=reply,
                data={"id": record.id, "title": title, "platform": platform},
                card=card,
            )

        except Exception as e:
            logger.error(f"[FeishuAgentBridge] 采集出错: {e}")
            return BridgeResult(
                action=BridgeAction.COLLECT_LINK,
                reply=f"采集出错: {str(e)[:100]}",
            )

    async def _handle_agent_chat(
        self, text: str, chat_id: str, sender_id: str
    ) -> BridgeResult:
        try:
            from app.agents.chat_agent import ChatAgent
            from app.db.session import AsyncSessionLocal

            agent = ChatAgent()

            async with AsyncSessionLocal() as db:
                result = await agent.process(
                    message=text,
                    session_id=f"feishu_{self._platform_user_id}_{sender_id}",
                    user_id=self._platform_user_id,
                    account_id="",
                    db=db,
                )

            reply = self._extract_reply_from_agent(result)

            if not reply and result.status == "chat":
                reply = await self._llm_simple_reply(text)

            if not reply:
                reply = "收到，我稍后处理。"

            card = BlockKitBuilder.chat_card(reply, result.status)

            return BridgeResult(
                action=BridgeAction.AGENT_CHAT,
                reply=reply,
                data={"status": result.status},
                card=card,
            )

        except Exception as e:
            logger.error(f"[FeishuAgentBridge] 智能体对话出错: {e}")
            return BridgeResult(
                action=BridgeAction.AGENT_CHAT,
                reply=f"智能体处理出错: {str(e)[:100]}",
            )

    def _extract_reply_from_agent(self, result: Any) -> str:
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

                skip_keys = {
                    "_awaiting_confirmation", "_confirmation_prompt",
                    "_workflow_started", "_loop_state_path",
                    "_last_thought", "_thinking_process", "thought",
                }
                parts = [
                    f"{k}: {v}"
                    for k, v in output.items()
                    if v and k not in skip_keys
                ]

                if parts:
                    result_text = "\n".join(parts[:5])

                    thought_patterns = [
                        "用户只是", "简单回应", "这是一个", "我需要",
                        "应该调用", "判断为", "识别到", "分析结果",
                        "根据上下文", "从消息来看", "这看起来",
                    ]

                    is_thought = any(pattern in result_text for pattern in thought_patterns)

                    if is_thought and len(result_text) < 100:
                        return ""

                    return result_text

        if result.status == "chat":
            return ""

        if result.status == "workflow_started":
            return "工作流已启动，正在处理中..."

        if result.status == "awaiting_confirmation":
            return "需要确认操作，请在Web端确认。"

        return ""

    async def _llm_simple_reply(self, text: str) -> str:
        try:
            from app.engine.factory import get_deepseek_llm

            llm = get_deepseek_llm(model="deepseek-v3")
            if llm is None:
                return "收到，我稍后处理。"

            messages = [
                {
                    "role": "system",
                    "content": (
                        "你是小红书创作助手，通过飞书与用户对话。"
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
            logger.warning(f"[FeishuAgentBridge] LLM 简单回复失败: {e}")
            return "收到，我稍后处理。"

    async def _send_reply(self, chat_id: str, text: str) -> None:
        try:
            from app.rpa.feishu_bot import get_feishu_engine

            engine = get_feishu_engine(self._platform_user_id)

            if not engine.is_running:
                logger.warning("[FeishuAgentBridge] 机器人未运行，无法回复")
                return

            if not chat_id:
                logger.warning("[FeishuAgentBridge] 无 chat_id，无法回复")
                return

            if len(text) > 4000:
                text = text[:3997] + "..."

            await engine._client.send_text(chat_id, text)
            logger.info(f"[FeishuAgentBridge] 回复已发送: chat_id={chat_id}")

        except Exception as e:
            logger.error(f"[FeishuAgentBridge] 发送回复出错: {e}")

    async def _send_card(self, chat_id: str, card: dict[str, Any]) -> None:
        """发送 BlockKit 卡片消息。"""
        try:
            from app.rpa.feishu_bot import get_feishu_engine

            engine = get_feishu_engine(self._platform_user_id)

            if not engine.is_running:
                logger.warning("[FeishuAgentBridge] 机器人未运行，无法回复卡片")
                return

            if not chat_id:
                logger.warning("[FeishuAgentBridge] 无 chat_id，无法发送卡片")
                return

            await engine._client.send_card(chat_id, card)
            logger.info(f"[FeishuAgentBridge] 卡片已发送: chat_id={chat_id}")

        except Exception as e:
            logger.error(f"[FeishuAgentBridge] 发送卡片出错: {e}, fallback to text")
            await self._send_reply(chat_id, json.dumps(card, ensure_ascii=False)[:1000])


_bridge_registry: dict[str, FeishuAgentBridge] = {}


def get_or_create_bridge(platform_user_id: str) -> FeishuAgentBridge:
    if platform_user_id not in _bridge_registry:
        bridge = FeishuAgentBridge(platform_user_id=platform_user_id)
        _bridge_registry[platform_user_id] = bridge

        from app.rpa.feishu_bot import get_feishu_engine
        engine = get_feishu_engine(platform_user_id)
        engine.add_message_callback(bridge.on_message)

        logger.info(f"[FeishuAgentBridge] 已为用户 {platform_user_id} 创建桥并注册回调")

    return _bridge_registry[platform_user_id]


def remove_bridge(platform_user_id: str) -> None:
    if platform_user_id in _bridge_registry:
        bridge = _bridge_registry.pop(platform_user_id)
        from app.rpa.feishu_bot import get_feishu_engine
        engine = get_feishu_engine(platform_user_id)
        engine.remove_message_callback(bridge.on_message)
        logger.info(f"[FeishuAgentBridge] 已移除用户 {platform_user_id} 的桥")