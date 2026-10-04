"""wechat_push 节点：将卡片/文案推送到微信。

输入：card_gen 的 cards_base64 或 copywrite 的文案
输出：push_status / push_message

使用 WeChatBotEngine.send_image / send_text 发送。
"""
from __future__ import annotations

import base64

from typing import Any

from app.agents.nodes._base import (
    NodeStatus, WorkflowState, _dlog, emit_node_event, logger,
)


async def wechat_push_node(state: WorkflowState) -> dict:
    workflow_id = state["workflow_id"]
    node_id = "wechat_push"

    _dlog(f"[{workflow_id}] ===== wechat_push_node ENTERED =====")
    await emit_node_event(workflow_id, node_id, "node_started")
    await emit_node_event(workflow_id, node_id, "node_status_changed", {"status": "running"})

    node_outputs = state.get("node_outputs", {})
    card_gen = node_outputs.get("card_gen", {})
    copywrite = node_outputs.get("copywrite", {})
    final_review = node_outputs.get("final_review", {})

    cards_base64 = card_gen.get("cards_base64", [])
    title = (
        final_review.get("title")
        or copywrite.get("title")
        or state.get("topic", "")
    )
    content = (
        final_review.get("content")
        or copywrite.get("content")
        or ""
    )

    model_settings = state.get("model_settings", {}) or {}
    wechat_target = model_settings.get("wechat_target_user_id", "")

    if not wechat_target:
        logger.warning(f"[{workflow_id}] {node_id} no wechat_target_user_id configured, skip push")
        await emit_node_event(workflow_id, node_id, "node_status_changed", {"status": "completed"})
        return {
            "node_statuses": {node_id: NodeStatus.COMPLETED.value},
            "node_outputs": {
                node_id: {
                    "push_status": "skipped",
                    "push_message": "未配置微信推送目标，跳过",
                }
            },
        }

    try:
        from app.rpa.wechat_bot_engine import get_wechat_engine

        user_id = state.get("user_id", "")
        engine = get_wechat_engine(user_id)

        if engine is None or not engine.is_logged_in:
            logger.warning(f"[{workflow_id}] {node_id} wechat bot not available or not logged in, skip push")
            await emit_node_event(workflow_id, node_id, "node_status_changed", {"status": "completed"})
            return {
                "node_statuses": {node_id: NodeStatus.COMPLETED.value},
                "node_outputs": {
                    node_id: {
                        "push_status": "skipped",
                        "push_message": "微信机器人未登录或不可用，跳过推送",
                    }
                },
            }

        context_token = None
        if engine._client:
            context_token = await engine._client.ensure_context_token(wechat_target)

        if not context_token:
            logger.warning(f"[{workflow_id}] {node_id} no context_token for target, skip push")
            await emit_node_event(workflow_id, node_id, "node_status_changed", {"status": "completed"})
            return {
                "node_statuses": {node_id: NodeStatus.COMPLETED.value},
                "node_outputs": {
                    node_id: {
                        "push_status": "need_activation",
                        "push_message": (
                            f"无法获取 {wechat_target} 的 context_token。"
                            f"iLink 协议要求对方先给机器人发一条消息才能建立会话。"
                            f"请在微信上给机器人发任意一条消息，然后重试推送。"
                        ),
                    }
                },
            }

        pushed_count = 0

        if cards_base64:
            await emit_node_event(workflow_id, node_id, "progress_update", {
                "progress": 20,
                "step": "pushing_cards",
                "message": f"正在推送 {len(cards_base64)} 张卡片到微信...",
            })
            for i, img_b64 in enumerate(cards_base64):
                try:
                    img_bytes = base64.b64decode(img_b64)
                    success = await engine.send_image(
                        to_user_id=wechat_target,
                        context_token=context_token,
                        image_data=img_bytes,
                        file_ext="png",
                    )
                    if success:
                        pushed_count += 1
                    _dlog(f"[{workflow_id}] wechat_push card {i+1}/{len(cards_base64)}: success={success}")
                except Exception as e:
                    logger.warning(f"[{workflow_id}] wechat_push card {i+1} failed: {e}")

        if title or content:
            await emit_node_event(workflow_id, node_id, "progress_update", {
                "progress": 80,
                "step": "pushing_text",
                "message": "正在推送文案到微信...",
            })
            text_parts = []
            if title:
                text_parts.append(f"📌 {title}")
            if content:
                text_parts.append(content[:2000])
            full_text = "\n\n".join(text_parts)

            try:
                success = await engine.send_text(
                    to_user_id=wechat_target,
                    context_token=context_token,
                    text=full_text,
                )
                if success:
                    pushed_count += 1
                _dlog(f"[{workflow_id}] wechat_push text: success={success}")
            except Exception as e:
                logger.warning(f"[{workflow_id}] wechat_push text failed: {e}")

        await emit_node_event(workflow_id, node_id, "progress_update", {
            "progress": 100,
            "step": "push_done",
            "message": f"已推送 {pushed_count} 项到微信",
        })

        output = {
            "push_status": "completed",
            "pushed_count": pushed_count,
            "push_message": f"已推送 {pushed_count} 项到微信",
        }

    except Exception as e:
        logger.error(f"[{workflow_id}] {node_id} wechat push failed: {e}")
        output = {
            "push_status": "error",
            "push_message": str(e),
        }

    await emit_node_event(workflow_id, node_id, "node_status_changed", {"status": "completed"})
    return {
        "node_statuses": {node_id: NodeStatus.COMPLETED.value},
        "node_outputs": {node_id: output},
    }