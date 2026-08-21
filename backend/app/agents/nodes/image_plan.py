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
    selected_direction = analyze_output.get("selected_direction", 0)
    try:
        selected_direction = int(selected_direction)
    except (TypeError, ValueError):
        selected_direction = 0
    if selected_direction < 0 or selected_direction >= len(analyze_recommendations):
        selected_direction = 0
    if analyze_recommendations and isinstance(analyze_recommendations[selected_direction], dict):
        brief = analyze_recommendations[selected_direction].get("execution_brief") or {}
        if isinstance(brief, dict):
            visual_suggestion = str(brief.get("visual_suggestion", "")).strip()
            analyze_content_type = str(brief.get("content_type", "")).strip()

    # 用户配置
    model_settings = state.get("model_settings", {}) or {}
    user_temperature = model_settings.get("temperature")
    user_text_model = model_settings.get("text_model")

    from app.engine.factory import get_deepseek_llm

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
            suggested = _recommend_template(topic, analyze_content_type)
            is_esther = suggested.startswith("esther_")

            if is_esther:
                pages_list: list[dict] = [{
                    "type": "cover",
                    "title": title[:40] if title else topic,
                    "subtitle": f"共 {len(structured_items)} 个知识点",
                    "footer": "@灵犀工坊",
                    "highlight": "",
                    "tag": "知识清单",
                }]
            else:
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
            if is_esther:
                pages_list.append({
                    "type": "end_page",
                    "title": "",
                    "content": f"掌握 {len(structured_items)} 个知识点，让{topic}不再难。",
                    "footer": "@灵犀工坊",
                    "ctaText": "关注我，获取更多知识",
                    "decoNumber": '"',
                })
            card_draft = {
                "pages": pages_list,
                "suggested_template": suggested,
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
                "你是小红书卡片文案编排师。你的核心任务是把下面的文案全文拆分编排到 4-6 张卡片中，\n"
                "每张卡都要有实质内容，不能留空。读者看完所有卡片等于读完原文。\n\n"
                "编排原则：\n"
                "1. 第 1 张封面（cover）：原文标题 + 吸引眼球的副标题 + 署名\n"
                "2. 中间页把原文正文按逻辑段落拆分，每页放 2-3 句或 1 个完整段落，选择最合适的页面类型：\n"
                "   - content：正文页，一个小标题 + 2-3 段正文（每段 1-2 句，总字数 50-120 字）\n"
                "   - quote：金句页，从原文中挑一句最戳人的话 + 出处\n"
                "   - list：清单页，把原文要点提炼为 3-5 条清单（每条 10-30 字）\n"
                "   - dark_panel：深色面板页，暗底亮字 + emoji + 3-5 条关键洞察（每条 10-30 字）\n"
                "   - compare：对比页，左（问题/痛点）vs 右（解法/优势），各 2-4 条（每条 10-25 字）\n"
                "   - icon_text：图标文字页，4 个 emoji+文字的能力/方法卡片（每条 5-15 字）\n"
                "   - steps：步骤流程页，3-5 个步骤（每步标题 5-10 字 + 描述 15-40 字）\n"
                "   - numbered_cards：编号卡片页，3-5 个编号要点（每项标题 5-10 字 + 描述 15-40 字）\n"
                "   - newspaper：报纸多栏页，报头+2-3 栏新闻式内容（每栏标题 5-15 字 + 正文 30-60 字）\n"
                "   - big_quote：大字金句页，超大字号展示一句话（15-40 字）\n"
                "3. 最后 1 张尾页（end_page）：一句让人记住你的话 + CTA\n"
                f"{visual_hint}\n"
                "4. 模板选择：根据主题从以下 6 套中选最合适的一套：\n"
                "   【基础模板】\n"
                "   - minimal_white：白底黑字红色点缀，适合知识干货、教育、科普\n"
                "   - warm_card：米黄底深棕字，适合美食、旅行、生活方式、穿搭\n"
                "   - dark_tech：深蓝底白字霓虹绿点缀，适合科技、AI、编程、数码\n"
                "   【Esther 设计系统】\n"
                "   - esther_brand：品牌三色+奶白底+衬线标题，适合知识科普、干货分享、职场\n"
                "   - esther_dark：深色墨底+金色强调+衬线标题，适合科技、AI、编程、深度思考\n"
                "   - esther_warm：暖奶底+橙棕强调+圆润字体，适合生活方式、美食、旅行\n"
                "5. 强调色（custom_accent）：根据主题推荐一个十六进制颜色值\n\n"
                "【关键要求】\n"
                "- 你必须把原文内容编排进每张卡的 content/listItems/steps 等字段中，不能只写标题不写正文\n"
                "- 每张 content 页的 content 字段必须有 2-3 段实际文案，总字数 50-120 字\n"
                "- 每张 list/dark_panel 页的 listItems 必须有 3-5 条实际要点，每条 10-30 字\n"
                "- 内容要精炼，不要把整段原文照搬，要提炼要点、保留核心信息\n"
                "- 读者看完所有卡 = 读完原文核心内容，不能遗漏重要内容\n\n"
                "严格输出以下 JSON 格式（不要输出其他内容，不要 markdown 代码块）：\n"
                '{\n'
                '  "pages": [\n'
                '    {"type": "cover", "title": "封面标题", "subtitle": "副标题", "footer": "@灵犀工坊", "highlight": "标题中需高亮的关键词", "tag": "干货分享"},\n'
                '    {"type": "content", "title": "小标题", "content": "2-3段正文，每段1-2句，用\\n换行"},\n'
                '    {"type": "list", "title": "清单标题", "listItems": ["要点1", "要点2", "要点3"]},\n'
                '    {"type": "quote", "content": "一句金句", "footer": "出处"},\n'
                '    {"type": "dark_panel", "emoji": "🚀", "decoNumber": "01", "listItems": ["洞察1", "洞察2", "洞察3"]},\n'
                '    {"type": "steps", "title": "操作步骤", "decoNumber": "01", "steps": [{"title": "第一步", "desc": "描述"}, {"title": "第二步", "desc": "描述"}]},\n'
                '    {"type": "numbered_cards", "title": "核心要点", "decoNumber": "02", "numberedItems": [{"title": "要点1", "desc": "描述"}, {"title": "要点2", "desc": "描述"}]},\n'
                '    {"type": "compare", "compareLeftTitle": "传统做法", "compareRightTitle": "更好方式", "compareLeftItems": ["痛点1", "痛点2"], "compareRightItems": ["优势1", "优势2"]},\n'
                '    {"type": "icon_text", "iconTextPairs": [{"icon": "🎯", "text": "描述1"}, {"icon": "💡", "text": "描述2"}]},\n'
                '    {"type": "newspaper", "masthead": "THE DAILY BRIEF", "newspaperCols": [{"headline": "栏目标题", "body": "栏目正文"}]},\n'
                '    {"type": "big_quote", "content": "一句震撼的话", "footer": "@灵犀工坊", "decoNumber": "\\""},\n'
                '    {"type": "end_page", "content": "一句让人记住你的话", "ctaText": "关注我，获取更多", "footer": "@灵犀工坊", "decoNumber": "\\""}\n'
                '  ],\n'
                '  "suggested_template": "esther_brand",\n'
                '  "custom_accent": "#2B7FD8"\n'
                '}\n\n'
                "注意：pages 数组中只需包含实际需要的页面类型，不必每种都用。封面和尾页各 1 张，中间页根据内容灵活选择。\n"
                "各页面类型特有字段说明：\n"
                "- cover 页可加 highlight（标题高亮关键词）和 tag（分类标签如\"干货分享\"）\n"
                "- dark_panel 页需提供 emoji、decoNumber（装饰数字如\"01\"）、listItems\n"
                "- end_page 页需提供 ctaText（CTA引导语）、decoNumber（装饰引号如\"\\\"\"）\n"
                "- compare 页需提供 compareLeftTitle/compareRightTitle/compareLeftItems/compareRightItems\n"
                "- icon_text 页需提供 iconTextPairs: [{icon: \"🎯\", text: \"描述\"}]\n"
                "- steps 页需提供 steps: [{title: \"步骤名\", desc: \"描述\"}]，可加 decoNumber\n"
                "- numbered_cards 页需提供 numberedItems: [{title: \"要点\", desc: \"描述\"}]，可加 decoNumber\n"
                "- newspaper 页需提供 masthead（报头）、newspaperCols: [{headline: \"栏目标题\", body: \"栏目正文\"}]\n"
                "- big_quote 页用 content 字段放金句，decoNumber 放装饰引号\n\n"
                f"主题：{topic}\n"
                f"标题：{title}\n"
                f"正文（必须全部编排进卡片，不能遗漏）：\n{content}\n"
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

    # 后处理：封面 title 兜底 + 附加 copywrite 原文上下文
    _postprocess_draft(card_draft, title, content, tags)

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

    优先级：content_type 映射 > topic 关键词 > 默认 esther_brand

    映射表（对齐 analyze 节点 _VALID_CONTENT_TYPES）：
    - 清单型 / 教程型 → esther_brand（品牌三色，清晰专业）
    - 观点型 → esther_dark（深色有态度）
    - 对比型 / 叙事型 → esther_warm（暖色亲和/温馨）
    """
    # 1. content_type 优先（analyze 节点已校验枚举，可信度高）
    _CONTENT_TYPE_MAP = {
        "清单型": "esther_brand",
        "教程型": "esther_brand",
        "观点型": "esther_dark",
        "对比型": "esther_warm",
        "叙事型": "esther_warm",
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
    knowledge_keywords = [
        "知识", "干货", "科普", "教育", "学习", "职场", "方法", "技巧",
        "思维", "认知", "提升", "成长", "读书", "笔记",
    ]
    for kw in warm_keywords:
        if kw in text:
            return "esther_warm"
    for kw in tech_keywords:
        if kw in text:
            return "esther_dark"
    for kw in knowledge_keywords:
        if kw in text:
            return "esther_brand"

    # 3. 默认：esther_brand（品牌三色，最通用）
    return "esther_brand"


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
        "esther_brand": {
            "type": "gradient_orbs",
            "color1": "#2B7FD8",
            "color2": "#F4D758",
            "opacity": 0.25,
            "param1": 0.3,
            "param2": 0.7,
        },
        "esther_dark": {
            "type": "geometric",
            "color1": "#F4D758",
            "color2": "#2B7FD8",
            "opacity": 0.12,
            "param1": 0.7,
            "param2": 30,
        },
        "esther_warm": {
            "type": "gradient_orbs",
            "color1": "#F4D758",
            "color2": "#E84A5F",
            "opacity": 0.2,
            "param1": 0.25,
            "param2": 0.6,
        },
    }
    return _TEMPLATE_DECO.get(template, {"type": "none", "color1": "#2B7FD8", "color2": "#F4D758", "opacity": 0.2})


def _build_card_draft_fallback(topic: str, title: str, content: str, tags, key_points) -> dict:
    """LLM 不可用时的 card_draft 兜底：把 copywrite 全文拆分到多张卡。"""
    import re

    # 按段落拆分正文
    paragraphs = [p.strip() for p in (content or "").split("\n") if p.strip()]
    if not paragraphs:
        sentences = re.split(r'(?<=[。！？；])', content or "")
        sentences = [s.strip() for s in sentences if s.strip()]
        paragraphs = []
        chunk = []
        for s in sentences:
            chunk.append(s)
            if len(chunk) >= 2:
                paragraphs.append("".join(chunk))
                chunk = []
        if chunk:
            paragraphs.append("".join(chunk))
    if not paragraphs:
        paragraphs = [content] if content else ["正文内容待补充"]

    # key_points 作为 list 卡的来源
    if isinstance(key_points, list) and key_points:
        list_items = [str(k)[:100] for k in key_points[:5]]
    else:
        list_items = ["要点一", "要点二", "要点三"]

    suggested = _recommend_template(topic, "")
    is_esther = suggested.startswith("esther_")

    # 构建页面列表：封面 + 内容页（每页 2-3 段）+ 尾页
    pages_list = []
    if is_esther:
        pages_list.append({
            "type": "cover",
            "title": title or topic or "点击编辑标题",
            "subtitle": " · ".join(tags[:3]) if isinstance(tags, list) and tags else "",
            "footer": "@灵犀工坊",
            "highlight": "",
            "tag": "干货分享",
        })
    else:
        pages_list.append({
            "type": "cover",
            "title": title or topic or "点击编辑标题",
            "subtitle": " · ".join(tags[:3]) if isinstance(tags, list) and tags else "",
            "footer": "@灵犀工坊",
        })

    # 第 2 张用 dark_panel/list 展示要点（esther），或 list（基础）
    if is_esther:
        pages_list.append({
            "type": "dark_panel",
            "title": "核心要点",
            "emoji": "💡",
            "decoNumber": "01",
            "listItems": list_items,
            "content": "",
        })
    else:
        pages_list.append({
            "type": "list",
            "title": "要点清单",
            "listItems": list_items,
        })

    # 每页放 2-3 段正文
    per_page = 2 if len(paragraphs) <= 4 else 3
    for i in range(0, len(paragraphs), per_page):
        chunk = paragraphs[i:i + per_page]
        pages_list.append({
            "type": "content",
            "title": "",
            "content": "\n".join(chunk),
        })

    if is_esther:
        pages_list.append({
            "type": "end_page",
            "title": "",
            "content": "一句让人记住你的话。",
            "footer": "@灵犀工坊",
            "ctaText": "关注我，获取更多",
            "decoNumber": '"',
        })

    return {
        "pages": pages_list,
        "suggested_template": suggested,
    }


def _postprocess_draft(
    card_draft: dict,
    copywrite_title: str,
    copywrite_content: str,
    copywrite_tags: list,
) -> None:
    """后处理：封面兜底 + 空内容页面校验 + 附加 copywrite 原文上下文。

    LLM 有时返回空 content/listItems 的页面，本函数做兜底：
    1. 封面页 title 为空 → 用 copywrite title 填充
    2. 封面页 subtitle 为空且有 tags → 用 tags 拼副标题
    3. 内容页 content/listItems 都为空 → 用 copywrite 原文段落填充
    4. 附加 copywrite_context 供前端"重新分配"按钮使用
    """
    import re

    pages = card_draft.get("pages", [])
    if not pages:
        return

    # 1. 封面页兜底
    cover = next((p for p in pages if p.get("type") == "cover"), None)
    if cover:
        if not cover.get("title") and copywrite_title:
            cover["title"] = copywrite_title[:40]
        if not cover.get("subtitle") and copywrite_tags:
            tag_str = " · ".join(copywrite_tags[:3]) if isinstance(copywrite_tags, list) else str(copywrite_tags)
            cover["subtitle"] = tag_str

    # 2. 校验内容页：找出所有空内容页面
    content_types = {"content", "list", "dark_panel", "quote", "big_quote", "steps", "numbered_cards", "compare", "icon_text", "newspaper"}
    empty_pages = []
    for p in pages:
        if p.get("type") not in content_types:
            continue
        has_content = bool(p.get("content"))
        has_list = bool(p.get("listItems"))
        has_steps = bool(p.get("steps"))
        has_numbered = bool(p.get("numberedItems"))
        has_compare = bool(p.get("compareLeftItems") or p.get("compareRightItems"))
        has_icon = bool(p.get("iconTextPairs"))
        has_cols = bool(p.get("newspaperCols"))
        if not any([has_content, has_list, has_steps, has_numbered, has_compare, has_icon, has_cols]):
            empty_pages.append(p)

    # 3. 如果有空内容页面，把 copywrite 原文拆段填充
    if empty_pages and copywrite_content:
        paragraphs = [p.strip() for p in copywrite_content.split("\n") if p.strip()]
        if not paragraphs:
            sentences = re.split(r'(?<=[。！？；])', copywrite_content)
            sentences = [s.strip() for s in sentences if s.strip()]
            paragraphs = []
            chunk = []
            for s in sentences:
                chunk.append(s)
                if len(chunk) >= 2:
                    paragraphs.append("".join(chunk))
                    chunk = []
            if chunk:
                paragraphs.append("".join(chunk))
        if not paragraphs:
            paragraphs = [copywrite_content]

        per_page = max(1, (len(paragraphs) + len(empty_pages) - 1) // len(empty_pages))
        para_idx = 0
        for page in empty_pages:
            if para_idx >= len(paragraphs):
                break
            chunk = paragraphs[para_idx:para_idx + per_page]
            para_idx += per_page
            if page.get("type") in ("list", "dark_panel"):
                page["listItems"] = chunk
            else:
                page["content"] = "\n".join(chunk)

    # 4. 附加 copywrite_context
    card_draft["copywrite_context"] = {
        "title": copywrite_title,
        "content": copywrite_content,
        "tags": copywrite_tags if isinstance(copywrite_tags, list) else [],
    }