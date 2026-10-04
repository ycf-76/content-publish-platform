"""feishu_push 节点：将卡片/文案推送到飞书。

输入：card_gen 的 cards_base64 或 copywrite 的文案
输出：push_status / push_message

使用 FeishuClient.send_text / send_card / send_image 发送。
"""
from __future__ import annotations

import base64
import json

from typing import Any

from app.agents.nodes._base import (
    NodeStatus, WorkflowState, _dlog, emit_node_event, logger,
)


async def feishu_push_node(state: WorkflowState) -> dict:
    workflow_id = state["workflow_id"]
    node_id = "feishu_push"

    _dlog(f"[{workflow_id}] ===== feishu_push_node ENTERED =====")
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
    feishu_chat_id = model_settings.get("feishu_chat_id", "")

    if not feishu_chat_id:
        logger.warning(f"[{workflow_id}] {node_id} no feishu_chat_id configured, skip push")
        await emit_node_event(workflow_id, node_id, "node_status_changed", {"status": "completed"})
        return {
            "node_statuses": {node_id: NodeStatus.COMPLETED.value},
            "node_outputs": {
                node_id: {
                    "push_status": "skipped",
                    "push_message": "未配置飞书推送目标群，跳过",
                }
            },
        }

    try:
        from app.rpa.feishu_bot import get_feishu_engine

        user_id = state.get("user_id", "")
        engine = get_feishu_engine(user_id)

        if not engine.is_running:
            logger.warning(f"[{workflow_id}] {node_id} feishu bot not running, skip push")
            await emit_node_event(workflow_id, node_id, "node_status_changed", {"status": "completed"})
            return {
                "node_statuses": {node_id: NodeStatus.COMPLETED.value},
                "node_outputs": {
                    node_id: {
                        "push_status": "skipped",
                        "push_message": "飞书机器人未启动，跳过推送",
                    }
                },
            }

        client = engine._client
        pushed_count = 0

        if title or content:
            await emit_node_event(workflow_id, node_id, "progress_update", {
                "progress": 20,
                "step": "pushing_text",
                "message": "正在推送文案到飞书...",
            })

            text_parts = []
            if title:
                text_parts.append(f"📌 {title}")
            if content:
                text_parts.append(content[:4000])
            full_text = "\n\n".join(text_parts)

            try:
                await client.send_text(
                    receive_id=feishu_chat_id,
                    text=full_text,
                )
                pushed_count += 1
                _dlog(f"[{workflow_id}] feishu_push text: sent to chat_id={feishu_chat_id}")
            except Exception as e:
                logger.warning(f"[{workflow_id}] feishu_push text failed: {e}")

        if cards_base64:
            await emit_node_event(workflow_id, node_id, "progress_update", {
                "progress": 50,
                "step": "pushing_cards",
                "message": f"正在推送 {len(cards_base64)} 张卡片到飞书...",
            })
            for i, img_b64 in enumerate(cards_base64):
                try:
                    img_bytes = base64.b64decode(img_b64)
                    success = await client.send_image(
                        receive_id=feishu_chat_id,
                        image_data=img_bytes,
                        file_ext="png",
                    )
                    if success:
                        pushed_count += 1
                    _dlog(f"[{workflow_id}] feishu_push card {i+1}/{len(cards_base64)}: success={success}")
                except Exception as e:
                    logger.warning(f"[{workflow_id}] feishu_push card {i+1} failed: {e}")

        await emit_node_event(workflow_id, node_id, "progress_update", {
            "progress": 100,
            "step": "push_done",
            "message": f"已推送 {pushed_count} 项到飞书",
        })

        output = {
            "push_status": "completed",
            "pushed_count": pushed_count,
            "push_message": f"已推送 {pushed_count} 项到飞书",
        }

    except Exception as e:
        logger.error(f"[{workflow_id}] {node_id} feishu push failed: {e}")
        output = {
            "push_status": "error",
            "push_message": str(e),
        }

    await emit_node_event(workflow_id, node_id, "node_status_changed", {"status": "completed"})
    return {
        "node_statuses": {node_id: NodeStatus.COMPLETED.value},
        "node_outputs": {node_id: output},
    }