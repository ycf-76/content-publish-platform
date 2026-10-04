from app.agents.nodes._base import (
    NodeStatus, WorkflowState, _dlog, emit_node_event, logger,
    build_belief_dict, build_loop_counter_update,
)


async def publish_node(state: WorkflowState) -> dict:
    """Publish node: publish step (xhs_publish removed, returns success)."""
    workflow_id = state["workflow_id"]
    node_id = "publish"

    _dlog(f"[{workflow_id}] ===== publish_node ENTERED =====")
    _dlog(f"[{workflow_id}] publish_node state keys: {list(state.keys())}")
    _dlog(f"[{workflow_id}] publish_node node_statuses: {state.get('node_statuses', {})}")
    _dlog(f"[{workflow_id}] publish_node node_outputs keys: {list(state.get('node_outputs', {}).keys())}")

    await emit_node_event(workflow_id, node_id, "node_started")
    await emit_node_event(workflow_id, node_id, "node_status_changed",
                           {"status": "running"})

    logger.info(f"[{workflow_id}] {node_id} started")

    # 从 upstream 节点产物里取要发布的字段
    final_review = state.get("node_outputs", {}).get("final_review", {})
    copywrite = state.get("node_outputs", {}).get("copywrite", {})
    image_gen = state.get("node_outputs", {}).get("image_gen", {})
    image_review = state.get("node_outputs", {}).get("image_review", {})

    # 优先从 image_urls 读文件转 base64（文件存储模式），
    # 回退到 checkpoint 中的 images_base64（旧数据兼容）
    image_urls = (
        final_review.get("image_urls")
        or image_review.get("image_urls")
        or image_gen.get("image_urls")
        or []
    )
    images_for_publish: list[str] = []
    if image_urls:
        from app.services.image_store import read_workflow_images_as_base64
        images_for_publish = read_workflow_images_as_base64(image_urls)
        _dlog(f"[{workflow_id}] publish_node: read {len(images_for_publish)} images from files "
              f"(urls={len(image_urls)})")

    if not images_for_publish:
        images_for_publish = (
            final_review.get("images_base64")
            or image_review.get("images_base64")
            or image_gen.get("images_base64")
            or []
        )
        _dlog(f"[{workflow_id}] publish_node: fallback to checkpoint base64, "
              f"count={len(images_for_publish)}")

    harness_input = {
        "title": (
            final_review.get("title")
            or copywrite.get("title")
            or (state.get("topic") or "")
        ),
        "content": (
            final_review.get("content")
            or copywrite.get("content")
            or ""
        ),
        "images_base64": images_for_publish,
        "account_id": state.get("account_id", ""),
        # 发布策略：manual（默认，半自动）| auto（实验性自动点击）。
        # 定时任务流水线经 model_settings 下发；普通工作流缺省 manual，行为不变。
        "publish_strategy": (
            state.get("model_settings", {}).get("publish_strategy", "manual")
        ),
    }

    _dlog(f"[{workflow_id}] publish_node harness_input: title={harness_input['title'][:30]!r}, "
          f"content_len={len(harness_input['content'])}, images={len(harness_input['images_base64'])}")

    # ── 平台限制检查（多平台适配） ──
    _platform = state.get("platform", "xiaohongshu")
    try:
        from app.services.platform_adapter import check_platform_limits
        _platform_check = check_platform_limits(
            harness_input["title"], harness_input["content"], _platform,
        )
        if not _platform_check["ok"]:
            logger.warning(
                f"[{workflow_id}] {node_id} platform limits exceeded: "
                f"{_platform_check['issues']}"
            )
        harness_input["_platform_check"] = _platform_check
    except Exception as _perr:
        logger.warning(f"[{workflow_id}] {node_id} platform check failed: {_perr}")

    # 参数校验：title 和 content 不能为空
    if not harness_input["title"] or not harness_input["content"]:
        logger.warning(
            f"[{workflow_id}] {node_id} missing title or content, skip publish"
        )
        _dlog(f"[{workflow_id}] publish_node SKIP: missing title or content")
        output = {
            "post_id": "",
            "status": "failed",
            "message": "发布失败：缺少标题或正文（请检查 copywrite / final_review 节点输出）",
        }
    else:
        # 发布进度提示：发布流程涉及 Scrapling StealthyFetcher 操作发布页，耗时 15-30s
        img_count = len(harness_input["images_base64"])
        await emit_node_event(workflow_id, node_id, "progress_update", {
            "progress": 10,
            "step": "publish_starting",
            "message": f"正在连接{_platform}发布页（{img_count} 张图片）...",
        })

        publish_strategy = harness_input.get("publish_strategy", "manual")
        auto_submit = publish_strategy == "auto"

        try:
            from app.services.platform_publisher import publish_to_platform
            from app.services.platform_adapter import adapt_tags

            _tags = adapt_tags(
                copywrite.get("tags", []),
                _platform,
            )

            publish_result = await publish_to_platform(
                platform=_platform,
                title=harness_input["title"],
                content=harness_input["content"],
                tags=_tags,
                images_base64=harness_input["images_base64"],
                auto_submit=auto_submit,
            )

            output = {
                "post_id": "",
                "status": publish_result.get("status", "failed"),
                "message": publish_result.get("message", ""),
                "platform": _platform,
                "url": publish_result.get("url", ""),
            }

            if publish_result.get("ok"):
                output["status"] = publish_result.get("status", "awaiting_manual")
                await emit_node_event(workflow_id, node_id, "progress_update", {
                    "progress": 80,
                    "step": "publish_content_filled",
                    "message": publish_result.get("message", "内容已填写"),
                })
            else:
                output["status"] = "failed"
                output["message"] = publish_result.get("message", "发布失败")

            _dlog(f"[{workflow_id}] publish_node result: status={output.get('status')}, "
                  f"message={output.get('message', '')[:100]}")
        except Exception as e:
            logger.exception(f"[{workflow_id}] {node_id} publish skill failed: {e}")
            _dlog(f"[{workflow_id}] publish_node skill EXCEPTION: {type(e).__name__}: {e}")
            await emit_node_event(workflow_id, node_id, "node_error",
                                  {"error": str(e), "error_type": type(e).__name__})
            output = {
                "post_id": "",
                "status": "failed",
                "message": f"发布异常: {e}",
            }

    _dlog(f"[{workflow_id}] publish_node FINAL output: {output}")

    # 半自动模式：worker 填好内容但不点击，status=awaiting_manual
    # 节点保持 RUNNING，等前端轮询 /api/workflows/{id}/publish/check 确认结果
    if output.get("status") == "awaiting_manual":
        logger.info(f"[{workflow_id}] {node_id} awaiting manual publish click")
        await emit_node_event(workflow_id, node_id, "progress_update", {
            "progress": 90,
            "step": "awaiting_manual_publish",
            "message": output.get("message", "内容已填好，请在浏览器窗口手动点击「发布」按钮"),
        })
        return {
            "current_node": node_id,
            # 不标 COMPLETED，保持 RUNNING，等 check API 更新
            "node_statuses": {node_id: NodeStatus.RUNNING.value},
            "node_outputs": {node_id: output},
            "agent_beliefs": build_belief_dict(node_id, output),
            "loop_counters": build_loop_counter_update(state, node_id),
        }

    await emit_node_event(workflow_id, node_id, "node_completed", output)

    # 发布成功时记录用户级长期记忆（publish_history）
    # 失败不阻塞工作流，仅记日志
    if output.get("status") == "success" or output.get("post_id"):
        try:
            from app.services import agent_memory
            await agent_memory.record_publish(
                user_id=state.get("user_id", ""),
                workflow_id=workflow_id,
                topic=state.get("topic", ""),
                title=harness_input.get("title", ""),
                post_id=str(output.get("post_id", "")),
            )
        except Exception as mem_err:
            logger.warning(
                f"[{workflow_id}] record_publish failed: {mem_err}"
            )

        # 新增：同时调 performance_collector.record_publication()
        # 写 published_content_performance 表，供 T+7 回采 + 预测校准
        # 与上面的 agent_memory.record_publish() 是互补关系（写不同表）
        try:
            from app.services.performance_collector import record_publication

            analyze_output = state.get("node_outputs", {}).get("analyze", {})
            copywrite_output = state.get("node_outputs", {}).get("copywrite", {})
            final_review_output = state.get("node_outputs", {}).get("final_review", {})
            image_gen_output = state.get("node_outputs", {}).get("image_gen", {})

            await record_publication(
                user_id=state.get("user_id", ""),
                workflow_id=workflow_id,
                topic=state.get("topic", ""),
                selected_pattern=analyze_output.get("patterns"),
                selected_direction=(
                    analyze_output.get("insights", {}).get("recommendations")
                ),
                published_note_id=str(output.get("post_id", "")),
                platform=_platform,
                predicted_viral_score=analyze_output.get("predicted_viral_score"),
                title=(
                    final_review_output.get("title")
                    or copywrite_output.get("title")
                    or harness_input.get("title", "")
                ),
                content_text=(
                    final_review_output.get("content")
                    or copywrite_output.get("content")
                    or harness_input.get("content", "")
                ),
                tags=copywrite_output.get("tags", []),
                images=image_gen_output.get("image_urls") or [],
                card_draft=state.get("node_outputs", {}).get("image_plan", {}).get("_draft"),
            )
        except Exception as perf_err:
            logger.warning(
                f"[{workflow_id}] record_publication failed: {perf_err}"
            )

    return {
        "current_node": node_id,
        "node_statuses": {node_id: NodeStatus.COMPLETED.value},
        "node_outputs": {node_id: output},
        "agent_beliefs": build_belief_dict(node_id, output),
        "loop_counters": build_loop_counter_update(state, node_id),
    }


def _build_belief(node_id: str, output: dict) -> dict:
    """从节点输出提取信念，写入 state.agent_beliefs。"""
    return build_belief_dict(node_id, output)