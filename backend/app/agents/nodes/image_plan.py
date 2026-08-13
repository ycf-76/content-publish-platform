from app.agents.nodes._base import NodeStatus, WorkflowState, emit_node_event, logger


async def image_plan_node(state: WorkflowState) -> dict:
    """图片规划节点：调 LLM 生成 4 张卡片的文案初稿（card_draft），供前端卡片编辑器加载。

    唯一职责：
    - 读取 copywrite 的 title/content/tags/key_points
    - 调 LLM 生成 card_draft（4 张卡：cover/content/quote/list 的文案）
    - 工作流在 image_gen 前 interrupt，前端编辑器加载 card_draft 供用户调整
    - 用户调整后 html2canvas 出图，通过 inject 接口注入 image_gen 输出

    红线：
    - 本节点不生成图片（不调 Playwright，不调通义万相）
    - 只输出文案初稿，图片由前端卡片编辑器生成
    """
    import time
    import json as _json

    workflow_id = state["workflow_id"]
    node_id = "image_plan"
    start_time = time.time()

    await emit_node_event(workflow_id, node_id, "node_started")
    await emit_node_event(workflow_id, node_id, "node_status_changed",
                           {"status": "running"})

    logger.info(f"[{workflow_id}] {node_id} started")

    try:
        copywrite_output = state.get("node_outputs", {}).get("copywrite", {})
    except Exception:
        copywrite_output = {}
    title = (copywrite_output or {}).get("title", "")
    content = (copywrite_output or {}).get("content", "")
    tags = (copywrite_output or {}).get("tags", [])
    key_points = (copywrite_output or {}).get("key_points", [])
    structured_items = (copywrite_output or {}).get("structured_items", []) or []
    topic = state.get("topic", "")

    # 读取 analyze 的 execution_brief（配图风格建议 + 内容类型）
    # 让卡片文案风格和文案内容保持一致
    analyze_output = state.get("node_outputs", {}).get("analyze", {}) or {}
    analyze_insights = analyze_output.get("insights", {}) or {}
    analyze_recommendations = analyze_insights.get("recommendations") or []
    visual_suggestion = ""
    analyze_content_type = ""
    if analyze_recommendations and isinstance(analyze_recommendations[0], dict):
        brief = analyze_recommendations[0].get("execution_brief") or {}
        if isinstance(brief, dict):
            visual_suggestion = str(brief.get("visual_suggestion", "")).strip()
            analyze_content_type = str(brief.get("content_type", "")).strip()

    # 用户配置
    model_settings = state.get("model_settings", {}) or {}
    user_temperature = model_settings.get("temperature")
    user_text_model = model_settings.get("text_model")

    from app.agents.harnesses.factory import get_deepseek_llm

    await emit_node_event(workflow_id, node_id, "progress_update", {
        "progress": 30,
        "step": "card_draft_planning",
        "message": "LLM 正在规划卡片文案...",
    })

    llm = get_deepseek_llm(temperature=user_temperature, model=user_text_model)

    card_draft: dict = {"pages": [], "suggested_template": "minimal_white"}
    model_used = "fallback"

    try:
        if structured_items:
            # 知识清单型：直接构造卡片，每页 4-5 个词条，零 LLM 成本
            # 第 1 张固定封面，后续按每页 4 条切分 structured_items
            items_per_page = 4
            pages_list: list[dict] = [{
                "type": "cover",
                "title": title[:40] if title else topic,
                "subtitle": f"共 {len(structured_items)} 个知识点",
                "footer": "@灵犀工坊",
            }]
            for i in range(0, len(structured_items), items_per_page):
                chunk = structured_items[i:i + items_per_page]
                list_items = [
                    f"{it.get('term', '')}：{it.get('definition', '')}"
                    for it in chunk
                    if it.get("term")
                ]
                if list_items:
                    pages_list.append({
                        "type": "list",
                        "title": f"{topic}（{i + 1}-{i + len(list_items)}）",
                        "listItems": list_items,
                        "footer": f"第 {len(pages_list)}/{((len(structured_items) - 1) // items_per_page) + 2} 页",
                    })
            card_draft = {
                "pages": pages_list,
                "suggested_template": _recommend_template(topic, analyze_content_type),
            }
            model_used = "structured_split (no LLM)"
            logger.info(
                f"[{workflow_id}] {node_id} structured card_draft: "
                f"{len(pages_list)} pages from {len(structured_items)} items"
            )
        else:
            # 非知识清单型：调 LLM 规划 4 张卡（cover/content/quote/list）
            # 构造 prompt：让 LLM 根据 copywrite 生成 4 张卡的文案初稿
            # 输出格式严格匹配前端 CardEditorPanel 的 CardPage 结构
            visual_hint = (
                f"\n**配图风格建议**（来自分析节点，卡片文案风格应与此一致）:\n{visual_suggestion}\n"
                if visual_suggestion else ""
            )
            prompt = (
                "你是小红书卡片文案规划师。根据以下文案内容，规划 4 张小红书卡片（1080×1440 竖图）的文案。\n\n"
                "要求：\n"
                "1. 第 1 张是封面（cover）：吸引眼球的标题 + 副标题 + 署名\n"
                "2. 第 2 张是正文（content）：一个小标题 + 2-3 段正文（正文要完整，不要截断）\n"
                "3. 第 3 张是金句（quote）：一句戳中读者的话 + 出处\n"
                "4. 第 4 张是清单（list）：一个清单标题 + 3-5 个要点\n"
                f"{visual_hint}\n"
                "5. 模板选择：根据主题从以下 3 套中选最合适的一套：\n"
                "   - minimal_white：白底黑字红色点缀，适合知识干货、教育、科普\n"
                "   - warm_card：米黄底深棕字，适合美食、旅行、生活方式、穿搭\n"
                "   - dark_tech：深蓝底白字霓虹绿点缀，适合科技、AI、编程、数码\n"
                "6. 强调色（custom_accent）：根据主题推荐一个十六进制颜色值，用于卡片标题/序号/分割线等强调元素\n"
                "   - 知识干货可用 #FF2442（红）或 #065F46（绿）\n"
                "   - 美食旅行可用 #D97706（橙）或 #B45309（棕）\n"
                "   - 科技编程可用 #10B981（绿）或 #3B82F6（蓝）\n\n"
                "严格输出以下 JSON 格式（不要输出其他内容，不要 markdown 代码块）：\n"
                '{\n'
                '  "pages": [\n'
                '    {"type": "cover", "title": "封面标题", "subtitle": "副标题", "footer": "@灵犀工坊"},\n'
                '    {"type": "content", "title": "正文小标题", "content": "第一段正文\\n\\n第二段正文"},\n'
                '    {"type": "quote", "content": "金句内容", "footer": "— 出处"},\n'
                '    {"type": "list", "title": "清单标题", "listItems": ["要点1", "要点2", "要点3"]}\n'
                '  ],\n'
                '  "suggested_template": "minimal_white",\n'
                '  "custom_accent": "#FF2442"\n'
                '}\n\n'
                f"主题：{topic}\n"
                f"标题：{title}\n"
                f"正文：{content[:800]}\n"
                f"标签：{', '.join(tags) if isinstance(tags, list) else tags}\n"
                f"要点：{', '.join(key_points) if isinstance(key_points, list) and key_points else '无'}\n"
            )

            if llm is not None:
                try:
                    resp = await llm.chat(
                        messages=[{"role": "user", "content": prompt}],
                    )
                    raw = (resp.get("content") or "").strip()
                    # 去掉可能的 markdown 代码块标记
                    if raw.startswith("```"):
                        raw = raw.split("\n", 1)[-1]
                        if raw.endswith("```"):
                            raw = raw.rsplit("```", 1)[0]
                        raw = raw.strip()
                    parsed = _json.loads(raw)
                    if isinstance(parsed, dict) and isinstance(parsed.get("pages"), list):
                        card_draft = parsed
                        model_used = llm.model_name or "deepseek"
                        logger.info(
                            f"[{workflow_id}] {node_id} card_draft generated: "
                            f"{len(card_draft['pages'])} pages"
                        )
                    else:
                        raise ValueError("invalid card_draft structure")
                except Exception as e:
                    logger.warning(f"[{workflow_id}] {node_id} LLM card_draft failed: {e}, using fallback")
                    card_draft = _build_card_draft_fallback(topic, title, content, tags, key_points)
            else:
                logger.warning(f"[{workflow_id}] {node_id} LLM unavailable, using fallback card_draft")
                card_draft = _build_card_draft_fallback(topic, title, content, tags, key_points)
    except Exception as e:
        logger.exception(f"[{workflow_id}] {node_id} card_draft generation failed unexpectedly: {e}")
        card_draft = _build_card_draft_fallback(topic, title, content, tags, key_points)
        model_used = "fallback (exception)"

    # 根据推荐的模板和主题，推荐装饰层配置
    suggested_template_id = card_draft.get("suggested_template", "minimal_white")
    suggested_decoration = _recommend_decoration(
        template=suggested_template_id,
        topic=topic,
        content_type=analyze_content_type,
    )
    card_draft["suggested_decoration"] = suggested_decoration

    output = {
        "image_plan": {"plan": [], "skipped": True, "reason": "card_editor_mode"},
        "card_draft": card_draft,
        "copywrite_passthrough": {
            "title": title,
            "content": content,
            "tags": tags if isinstance(tags, list) else [],
            "key_points": key_points,
        },
        "_model_used": model_used,
        "_duration_ms": int((time.time() - start_time) * 1000),
        "_token_usage": 0,
        "_source": "card_editor_mode",
    }
    await emit_node_event(workflow_id, node_id, "node_completed", output)
    return {
        "current_node": node_id,
        "node_statuses": {node_id: NodeStatus.COMPLETED.value},
        "node_outputs": {node_id: output},
    }


def _recommend_template(topic: str, content_type: str = "") -> str:
    """根据内容类型推荐卡片模板，topic 关键词作兜底。

    优先级：content_type 映射 > topic 关键词 > 默认 minimal_white

    映射表（对齐 analyze 节点 _VALID_CONTENT_TYPES）：
    - 清单型 / 教程型 → minimal_white（白底清晰，重 readability）
    - 观点型 → dark_tech（深色有态度）
    - 对比型 / 叙事型 → warm_card（暖色亲和/温馨）
    """
    # 1. content_type 优先（analyze 节点已校验枚举，可信度高）
    _CONTENT_TYPE_MAP = {
        "清单型": "minimal_white",
        "教程型": "minimal_white",
        "观点型": "dark_tech",
        "对比型": "warm_card",
        "叙事型": "warm_card",
    }
    if content_type in _CONTENT_TYPE_MAP:
        return _CONTENT_TYPE_MAP[content_type]

    # 2. content_type 为空或未知时，用 topic 关键词兜底
    text = (topic or "").lower()
    warm_keywords = [
        "美食", "食谱", "早餐", "晚餐", "午餐", "旅行", "旅游", "生活方式",
        "家居", "穿搭", "美妆", "护肤", "日常", "生活", "咖啡", "烘焙",
        "探店", "节日", "宠物", "花艺",
    ]
    tech_keywords = [
        "科技", "ai", "编程", "代码", "数码", "互联网", "python",
        "javascript", "技术", "开发", "软件", "工具", "效率", "电脑",
        "手机", "算法", "数据", "机器学习", "前端", "后端",
    ]
    for kw in warm_keywords:
        if kw in text:
            return "warm_card"
    for kw in tech_keywords:
        if kw in text:
            return "dark_tech"

    # 3. 默认
    return "minimal_white"


def _recommend_decoration(
    template: str, topic: str = "", content_type: str = ""
) -> dict:
    """根据模板 + 内容类型推荐装饰层配置。

    返回结构化 dict，与前端 DecorationConfig 对齐。
    策略：
    - warm_card → gradient_orbs（暖光斑）/ noise（纸张纹理）
    - dark_tech → grid_lines（网格线）/ geometric（几何色块）
    - minimal_white → dots（波点）/ wave（波浪）/ noise（纸张纹理）
    - content_type 细分覆盖默认
    """
    text = (topic or "").lower()

    # content_type 细分
    if content_type in ("清单型", "教程型"):
        return {
            "type": "noise",
            "color1": "#92400E",
            "color2": "#78716C",
            "opacity": 0.06,
            "param1": 0.5,
            "param2": 1,
        }
    if content_type == "观点型":
        return {
            "type": "geometric",
            "color1": "#818CF8",
            "color2": "#F472B6",
            "opacity": 0.15,
            "param1": 0.6,
            "param2": -15,
        }
    if content_type in ("对比型", "叙事型"):
        return {
            "type": "gradient_orbs",
            "color1": "#FDE68A",
            "color2": "#FCA5A5",
            "opacity": 0.35,
            "param1": 0.25,
            "param2": 0.65,
        }

    # topic 关键词细分
    food_kw = ["美食", "食谱", "早餐", "晚餐", "午餐", "咖啡", "烘焙", "探店"]
    travel_kw = ["旅行", "旅游", "探店", "节日", "花艺"]
    tech_kw = [
        "科技", "ai", "编程", "代码", "数码", "python",
        "javascript", "技术", "开发", "算法", "数据", "机器学习",
    ]
    life_kw = ["生活方式", "家居", "穿搭", "美妆", "护肤", "日常", "生活", "宠物"]

    for kw in food_kw:
        if kw in text:
            return {
                "type": "gradient_orbs",
                "color1": "#FDE68A",
                "color2": "#FCA5A5",
                "opacity": 0.35,
                "param1": 0.25,
                "param2": 0.65,
            }
    for kw in travel_kw:
        if kw in text:
            return {
                "type": "wave",
                "color1": "#7DD3FC",
                "color2": "#BAE6FD",
                "opacity": 0.2,
                "param1": 3,
                "param2": 40,
            }
    for kw in tech_kw:
        if kw in text:
            return {
                "type": "grid_lines",
                "color1": "#94A3B8",
                "color2": "#475569",
                "opacity": 0.12,
                "param1": 80,
                "param2": 1,
            }
    for kw in life_kw:
        if kw in text:
            return {
                "type": "dots",
                "color1": "#F9A8D4",
                "color2": "#FDE68A",
                "opacity": 0.25,
                "param1": 48,
                "param2": 6,
            }

    # 按 template 兜底
    _TEMPLATE_DECO = {
        "warm_card": {
            "type": "gradient_orbs",
            "color1": "#FDE68A",
            "color2": "#FCA5A5",
            "opacity": 0.3,
            "param1": 0.25,
            "param2": 0.65,
        },
        "dark_tech": {
            "type": "grid_lines",
            "color1": "#94A3B8",
            "color2": "#475569",
            "opacity": 0.12,
            "param1": 80,
            "param2": 1,
        },
        "minimal_white": {
            "type": "noise",
            "color1": "#92400E",
            "color2": "#78716C",
            "opacity": 0.06,
            "param1": 0.5,
            "param2": 1,
        },
    }
    return _TEMPLATE_DECO.get(template, {"type": "none", "color1": "#FDE68A", "color2": "#FCA5A5", "opacity": 0.3})


def _build_card_draft_fallback(topic: str, title: str, content: str, tags, key_points) -> dict:
    """LLM 不可用时的 card_draft 兜底：用 copywrite 内容拼 4 张卡。"""
    # 把正文按换行分段，取前 2 段作为 content 卡
    paragraphs = [p.strip() for p in (content or "").split("\n") if p.strip()][:2]
    content_text = "\n\n".join(paragraphs) if paragraphs else "正文内容待补充"

    # key_points 作为 list 卡的来源
    if isinstance(key_points, list) and key_points:
        list_items = [str(k)[:100] for k in key_points[:5]]
    else:
        list_items = ["要点一", "要点二", "要点三"]

    return {
        "pages": [
            {
                "type": "cover",
                "title": title or "点击编辑标题",
                "subtitle": "副标题（可选）",
                "footer": "@灵犀工坊",
            },
            {
                "type": "content",
                "title": "核心观点",
                "content": content_text,
            },
            {
                "type": "quote",
                "content": "一句戳中读者的话，放在这里作为金句。",
                "footer": "— 灵犀工坊",
            },
            {
                "type": "list",
                "title": "要点清单",
                "listItems": list_items,
            },
        ],
        "suggested_template": _recommend_template(topic, ""),
    }
