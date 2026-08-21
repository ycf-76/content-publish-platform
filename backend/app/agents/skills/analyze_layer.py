"""Layer 2 + Layer 3 LLM 分析层。

职责：
- Layer 2：对 top 5 笔记做模式识别（标题钩子 / 内容结构 / 情绪触发点），1 次 LLM 调用
- Layer 3：对 top 2 + Layer 2 结论做深度归因（趋势信号 + 选题建议），1 次 LLM 调用

红线：
- LLM 不碰 results 字段，只产出 patterns / insights
- evidence_note_ids 必须在 top 20 中校验，不在则丢弃
- LLM 输出 JSON 解析失败时降级为只返回 Layer 1 规则分析结果
- 三级 JSON 解析降级：直接 JSON → 去 markdown fence → 提取首个 JSON 对象 → 原文兜底
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


# ===== Prompt 模板 =====

_LAYER2_PROMPT = """你需要分析以下 {n} 条爆款笔记，找出可复制的模式。

主题：{topic}

笔记数据（已按爆点分排序，含分类标签）：
{top5_json}

请分析以下三个方面，输出严格 JSON：

1. title_patterns：标题钩子模式
   - 识别每条笔记的标题类型（数字型/反差型/痛点型/好奇型/利益型/故事型）
   - 总结最常见的 2-3 种钩子模式
   - 每种模式给出 1 个可复制的标题模板

2. content_structures：内容结构骨架
   - 从 summary 推断内容结构（如 场景引入→痛点→解决方案→证据→行动召唤）
   - 总结最有效的 1-2 种结构

3. emotion_triggers：情绪触发点
   - 识别每条笔记的核心情绪（焦虑/认同/好奇/对比/归属/成就）
   - 总结哪种情绪在该主题下最容易引爆

输出格式：
{{
  "title_patterns": [
    {{"type": "数字型", "template": "X个方法让你...", "examples": ["..."]}}
  ],
  "content_structures": [
    {{"structure": "场景→痛点→方案→证据→召唤", "description": "..."}}
  ],
  "emotion_triggers": [
    {{"emotion": "好奇", "reason": "..."}}
  ]
}}

重要：
- 只输出分析结论，不要复述笔记原文
- 必须输出合法 JSON，不要包含注释或额外文字
"""


_LAYER3_PROMPT = """基于以下分析结果，做深度归因和选题建议。

主题：{topic}
{user_preferences_section}
Layer 1 规则层输出（top 20，含 viral_type 分类）：
{layer1_summary}

Layer 2 LLM 粗分析输出（模式总结）：
{layer2_output}

请完成以下两个任务，输出严格 JSON：

1. trend_signals：跨笔记趋势信号
   - 检查是否有"多个小博主（粉丝型=false）同时用相似标题结构或内容结构爆款"
   - 如果有，说明这是话题型趋势（真趋势信号）
   - 明确标注哪些笔记是"大V日常，不参考"（粉丝型噪音）
   - 给出趋势强度评估（强/中/弱）和依据

2. recommendations：选题方向 + 内容骨架建议 + 执行指令
   - 基于 Layer 2 的模式总结 + Layer 3 的趋势信号
   - 给出 2-3 个可复制的选题方向
   - 若提供了"用户创作要求"，所有推荐方向只能优化表达方式/结构/语气，
     不得改变用户指定的话题对象、立场、重点和必须包含的信息
   - 每个方向附带：推荐标题模板 + 内容结构 + 情绪钩子 + 参考笔记 content_id
   - 必须带证据链：为什么推荐这个方向？哪些笔记是证据？
   - 若提供了用户偏好主题，优先推荐偏好方向；若提供了避免主题，避免推荐这些方向

3. execution_brief：为每个推荐方向生成一份【执行指令】，供下游 copywrite/image_plan 节点直接执行
   - content_type：内容呈现格式（清单型/叙事型/对比型/教程型/观点型）
   - recommended_structure：建议的正文结构（分步骤列出，如 ["痛点引入", "核心清单", "例句释义", "行动召唤"]）
   - tone：建议的语气风格（如"专业但不沉闷，适当口语化"）
   - title_style：建议的标题类型（数字型/反差型/痛点型/好奇型/利益型/故事型）
   - visual_suggestion：建议的配图风格（如"白底大字+绿色强调色，清单分页排版，每页3-4个词条"）

   重要：execution_brief 是下游节点的硬约束指令，不是建议。字段必须具体可执行，
   不要写"建议适当调整"这种模糊话术。content_type 必须从 5 种类型中选一个，
   title_style 必须从 6 种类型中选一个。

输出格式：
{{
  "trend_signals": {{
    "is_topic_trend": true,
    "trend_strength": "强",
    "trend_basis": "依据说明",
    "noise_note_ids": ["content_id1", "content_id2"]
  }},
  "recommendations": [
    {{
      "topic_direction": "...",
      "title_template": "...",
      "content_structure": "...",
      "emotion_hook": "...",
      "evidence_note_ids": ["content_id1", "content_id2"],
      "reason": "为什么推荐这个方向",
      "execution_brief": {{
        "content_type": "清单型",
        "recommended_structure": ["步骤1", "步骤2", "步骤3"],
        "tone": "语气风格描述",
        "title_style": "数字型",
        "visual_suggestion": "配图风格描述"
      }}
    }}
  ]
}}

重要：
- recommendations 必须带证据链（evidence_note_ids + reason）
- evidence_note_ids 必须从上面 Layer 1 输出的笔记列表中选取
- 不要给无依据的建议
- 每个 recommendation 必须包含 execution_brief，字段不可缺失
- 必须输出合法 JSON
"""


# ===== JSON 解析（三级降级） =====

def _build_user_preferences_section(user_preferences: dict) -> str:
    """把用户偏好（preferred_topics / avoided_topics）压缩成 prompt 段落。

    无偏好时返回空串，prompt 中段落消失。
    """
    if not user_preferences:
        return ""

    parts: list[str] = []
    preferred = user_preferences.get("preferred_topics") or []
    avoided = user_preferences.get("avoided_topics") or []
    creative_brief = str(user_preferences.get("creative_brief") or "").strip()
    search_keyword = str(user_preferences.get("search_keyword") or "").strip()
    if creative_brief:
        parts.append(
            "用户创作要求（最高优先级，搜索趋势只能作为表达参考）: "
            f"{creative_brief[:1000]}"
        )
    if search_keyword:
        parts.append(f"搜索关键词（仅用于匹配热点证据）: {search_keyword[:200]}")
    if preferred:
        parts.append(f"用户偏好主题（优先推荐这些方向）: {', '.join(str(t) for t in preferred[:5])}")
    if avoided:
        parts.append(f"用户避免主题（不要推荐这些方向）: {', '.join(str(t) for t in avoided[:5])}")

    if not parts:
        return ""

    return "\n" + "\n".join(f"  {p}" for p in parts) + "\n"


# ===== execution_brief 兜底校验 =====

_VALID_CONTENT_TYPES = {"清单型", "叙事型", "对比型", "教程型", "观点型"}
_VALID_TITLE_STYLES = {"数字型", "反差型", "痛点型", "好奇型", "利益型", "故事型"}


def _sanitize_execution_brief(brief: Any) -> dict:
    """校验 + 兜底 execution_brief，确保下游节点能拿到完整可执行的指令。

    LLM 可能：
    - 漏掉 execution_brief 整个字段
    - 漏掉部分子字段
    - content_type / title_style 写了非法枚举值
    - recommended_structure 写成字符串而非数组

    本函数保证返回的 dict 5 个字段全部存在且类型合法，
    缺失/非法时用合理默认值兜底。
    """
    if not isinstance(brief, dict):
        brief = {}

    # content_type：必须在 5 种合法类型中
    content_type = str(brief.get("content_type", "")).strip()
    if content_type not in _VALID_CONTENT_TYPES:
        # 尝试模糊匹配（LLM 可能写"清单"而非"清单型"）
        for valid in _VALID_CONTENT_TYPES:
            if valid in content_type or content_type in valid:
                content_type = valid
                break
        else:
            content_type = "叙事型"  # 最通用的默认类型

    # recommended_structure：必须是 list[str]，非空
    structure = brief.get("recommended_structure")
    if isinstance(structure, str):
        # LLM 可能写成 "步骤1→步骤2→步骤3" 字符串，按 → / , / ， 分割
        import re as _re
        parts = _re.split(r"[→,，\n]", structure)
        structure = [p.strip() for p in parts if p.strip()]
    elif not isinstance(structure, list):
        structure = []
    structure = [str(s).strip() for s in structure if str(s).strip()]
    if not structure:
        structure = ["引入", "主体内容", "总结"]

    # tone：字符串，非空
    tone = str(brief.get("tone", "")).strip()
    if not tone:
        tone = "自然口语化"

    # title_style：必须在 6 种合法类型中
    title_style = str(brief.get("title_style", "")).strip()
    if title_style not in _VALID_TITLE_STYLES:
        for valid in _VALID_TITLE_STYLES:
            if valid in title_style or title_style in valid:
                title_style = valid
                break
        else:
            title_style = "利益型"  # 最通用的默认类型

    # visual_suggestion：字符串，非空
    visual = str(brief.get("visual_suggestion", "")).strip()
    if not visual:
        visual = "简洁排版，突出重点信息"

    return {
        "content_type": content_type,
        "recommended_structure": structure,
        "tone": tone,
        "title_style": title_style,
        "visual_suggestion": visual,
    }


def _parse_llm_json(raw: str) -> dict | None:
    """三级降级解析 LLM 输出的 JSON。

    1. 直接 json.loads
    2. 去 markdown fence（```json ... ```）后解析
    3. 提取首个 { ... } 对象后解析
    4. 失败返回 None
    """
    if not raw:
        return None

    # Level 1: 直接解析
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Level 2: 去 markdown fence
    fenced = re.sub(r"^```(?:json)?\s*\n?", "", raw.strip(), flags=re.MULTILINE)
    fenced = re.sub(r"\n?```\s*$", "", fenced).strip()
    try:
        return json.loads(fenced)
    except json.JSONDecodeError:
        pass

    # Level 3: 提取首个 JSON 对象
    match = re.search(r"\{[\s\S]*\}", fenced)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    logger.warning(f"[analyze_layer] JSON parse failed, raw[:200]={raw[:200]}")
    return None


# ===== Layer 2 =====

async def run_layer2(
    llm: Any,
    top_notes: list[dict],
    topic: str,
) -> dict:
    """Layer 2：LLM 粗分析（top 5，1 次调用）。

    分析标题钩子模式 / 内容结构骨架 / 情绪触发点。

    Args:
        llm: DeepSeekAdapter 实例（必须有 chat 方法）
        top_notes: Layer 1 排序后的 top N 笔记（含 viral_type / viral_score）
        topic: 工作流主题

    Returns:
        patterns: dict（title_patterns / content_structures / emotion_triggers）
        失败时返回空 dict
    """
    if not llm:
        logger.warning("[analyze_layer] Layer2 skipped: no LLM")
        return {"_skipped": "no_llm"}

    if not top_notes:
        return {"_skipped": "empty_input"}

    # 准备 LLM 输入：只保留必要字段，降低 token 消耗
    slim_notes = []
    for n in top_notes[:5]:
        slim_notes.append({
            "content_id": n.get("content_id", ""),
            "title": n.get("title", ""),
            "summary": (n.get("summary") or "")[:200],  # 截断防止 token 爆炸
            "viral_type": n.get("viral_type", "普通"),
            "viral_score": n.get("viral_score", 0),
            "likes": n.get("likes", 0),
            "author": n.get("author", ""),
        })

    prompt = _LAYER2_PROMPT.format(
        n=len(slim_notes),
        topic=topic,
        top5_json=json.dumps(slim_notes, ensure_ascii=False, indent=2),
    )

    try:
        resp = await llm.chat(
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        raw = resp.get("content", "")
        parsed = _parse_llm_json(raw)
        if parsed is None:
            logger.warning("[analyze_layer] Layer2 JSON parse failed, returning raw")
            return {"_parse_failed": True, "_raw": raw[:500]}
        logger.info(
            f"[analyze_layer] Layer2 done: "
            f"patterns={len(parsed.get('title_patterns', []))}, "
            f"structures={len(parsed.get('content_structures', []))}, "
            f"triggers={len(parsed.get('emotion_triggers', []))}"
        )
        return parsed
    except Exception as e:
        logger.exception(f"[analyze_layer] Layer2 LLM call failed: {e}")
        return {"_error": str(e)}


async def run_layer2_streaming(
    llm: Any,
    top_notes: list[dict],
    topic: str,
    workflow_id: str = "",
    node_id: str = "analyze",
) -> dict:
    """Layer 2 流式版本：LLM streaming + 可读进度推送。

    保持JSON模式收集原始数据用于最终解析，
    但SSE推送时转换为人类可读的进度描述。
    """
    from app.services.sse_bus import sse_bus

    if not llm:
        logger.warning("[analyze_layer] Layer2 streaming skipped: no LLM")
        return {"_skipped": "no_llm"}

    if not top_notes:
        return {"_skipped": "empty_input"}

    slim_notes = []
    for n in top_notes[:5]:
        slim_notes.append({
            "content_id": n.get("content_id", ""),
            "title": n.get("title", ""),
            "summary": (n.get("summary") or "")[:200],
            "viral_type": n.get("viral_type", "普通"),
            "viral_score": n.get("viral_score", 0),
            "likes": n.get("likes", 0),
            "author": n.get("author", ""),
        })

    prompt = _LAYER2_PROMPT.format(
        n=len(slim_notes),
        topic=topic,
        top5_json=json.dumps(slim_notes, ensure_ascii=False, indent=2),
    )

    try:
        raw_parts: list[str] = []
        # 追加式流式推送：只发新增文本行（_append），前端逐字打印。
        # 过滤"正在..."占位行，保证已推送的行不会回改（append-only）。
        emitted_lines: list[str] = []
        if workflow_id:
            await sse_bus.publish(workflow_id, "stream_chunk", {
                "node_id": node_id,
                "chunk": {"content": ""},
                "_append": "\n—— Layer 2 · 模式识别 ——",
            })
        async for chunk in llm.stream_chat(
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        ):
            content = chunk.get("content")
            if content:
                raw_parts.append(content)
                if workflow_id:
                    full_display = _make_layer2_display_text(content, raw_parts)
                    lines = [
                        l for l in full_display.split("\n")
                        if l.strip() and "正在" not in l
                    ]
                    new_lines = lines[len(emitted_lines):]
                    if new_lines:
                        emitted_lines.extend(new_lines)
                        await sse_bus.publish(workflow_id, "stream_chunk", {
                            "node_id": node_id,
                            "chunk": {"content": content},
                            "_append": "\n" + "\n".join(new_lines),
                        })

        raw = "".join(raw_parts)
        parsed = _parse_llm_json(raw)
        if parsed is None:
            logger.warning("[analyze_layer] Layer2 streaming JSON parse failed")
            return {"_parse_failed": True, "_raw": raw[:500]}
        logger.info(
            f"[analyze_layer] Layer2 streaming done: "
            f"patterns={len(parsed.get('title_patterns', []))}, "
            f"structures={len(parsed.get('content_structures', []))}, "
            f"triggers={len(parsed.get('emotion_triggers', []))}"
        )
        return parsed
    except Exception as e:
        logger.exception(f"[analyze_layer] Layer2 streaming failed: {e}")
        return {"_error": str(e)}


def _make_layer2_display_text(latest_chunk: str, all_parts: list[str]) -> str:
    """将Layer2的JSON chunk转换为可读进度文本（累积式，每次返回完整文本）。"""
    import re as _re
    combined = "".join(all_parts) if all_parts else latest_chunk

    lines: list[str] = []

    # 阶段1：标题钩子
    if '"title_patterns"' in combined:
        title_match = _re.search(r'"title"\s*:\s*"([^"]+)"', combined)
        hook_match = _re.search(r'"hook"\s*:\s*"([^"]+)"', combined)
        pattern_match = _re.search(r'"pattern"\s*:\s*"([^"]+)"', combined)
        if title_match:
            lines.append(f"🔍 标题: {title_match.group(1)}")
        if hook_match:
            lines.append(f"🪝 钩子: {hook_match.group(1)}")
        if pattern_match:
            lines.append(f"📐 模式: {pattern_match.group(1)}")
        if not lines:
            lines.append("🔍 正在识别标题钩子模式...")

    # 阶段2：内容结构
    if '"content_structures"' in combined:
        struct_match = _re.search(r'"structure"\s*:\s*"([^"]+)"', combined)
        type_match = _re.search(r'"type"\s*:\s*"([^"]+)"', combined)
        if struct_match:
            lines.append(f"📋 结构: {struct_match.group(1)}")
        if type_match:
            lines.append(f"📝 类型: {type_match.group(1)}")
        if not any("结构" in l or "类型" in l for l in lines):
            lines.append("📋 正在分析内容结构骨架...")

    # 阶段3：情绪触发
    if '"emotion_triggers"' in combined:
        trigger_match = _re.search(r'"trigger"\s*:\s*"([^"]+)"', combined)
        emotion_match = _re.search(r'"emotion"\s*:\s*"([^"]+)"', combined)
        if trigger_match:
            lines.append(f"💡 触发: {trigger_match.group(1)}")
        if emotion_match:
            lines.append(f"❤️ 情绪: {emotion_match.group(1)}")
        if not any("触发" in l or "情绪" in l for l in lines):
            lines.append("💡 正在识别情绪触发点...")

    if not lines:
        if len(combined) < 50:
            lines.append("🔎 正在分析爆款笔记模式...")
        else:
            lines.append("⚙️ 正在生成分析结果...")

    return "\n".join(lines)


# ===== Layer 3 =====

async def run_layer3(
    llm: Any,
    top2: list[dict],
    all_notes: list[dict],
    layer2_output: dict,
    topic: str,
    user_preferences: dict | None = None,
) -> dict:
    """Layer 3：LLM 深度归因（top 2 + Layer 2 结论，1 次调用）。

    跨笔记趋势信号发现 + 选题方向建议（带证据链）。

    Args:
        llm: DeepSeekAdapter 实例
        top2: Layer 1 top 2 笔记
        all_notes: Layer 1 完整 top 20（用于 evidence_note_ids 校验）
        layer2_output: Layer 2 输出
        topic: 工作流主题
        user_preferences: 用户级长期记忆中的偏好（preferred_topics / avoided_topics），
            用于让 LLM 在推荐选题方向时优先/避免某些主题。

    Returns:
        insights: dict（trend_signals / recommendations）
        失败时返回空 dict
    """
    if not llm:
        logger.warning("[analyze_layer] Layer3 skipped: no LLM")
        return {"_skipped": "no_llm"}

    if not top2:
        return {"_skipped": "empty_input"}

    # 校验集合：所有合法的 content_id
    valid_ids = {n.get("content_id") for n in all_notes if n.get("content_id")}

    # 准备 Layer 1 摘要（top 20 精简版，含 content_id 供 LLM 引用）
    layer1_summary = json.dumps([
        {
            "content_id": n.get("content_id", ""),
            "title": n.get("title", ""),
            "viral_type": n.get("viral_type", "普通"),
            "viral_score": n.get("viral_score", 0),
            "likes": n.get("likes", 0),
            "author": n.get("author", ""),
        }
        for n in all_notes[:20]
    ], ensure_ascii=False, indent=2)

    # Layer 2 输出原样传入
    layer2_str = json.dumps(layer2_output, ensure_ascii=False, indent=2) if layer2_output else "{}"

    # 用户偏好段落（无偏好则空串，prompt 中段落消失）
    user_preferences_section = _build_user_preferences_section(user_preferences or {})

    prompt = _LAYER3_PROMPT.format(
        topic=topic,
        user_preferences_section=user_preferences_section,
        layer1_summary=layer1_summary,
        layer2_output=layer2_str,
    )

    try:
        resp = await llm.chat(
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        raw = resp.get("content", "")
        parsed = _parse_llm_json(raw)
        if parsed is None:
            logger.warning("[analyze_layer] Layer3 JSON parse failed, returning raw")
            return {"_parse_failed": True, "_raw": raw[:500]}

        # 校验 evidence_note_ids：不在 valid_ids 中的丢弃
        recs = parsed.get("recommendations", [])
        for rec in recs:
            ev_ids = rec.get("evidence_note_ids", [])
            rec["evidence_note_ids"] = [
                eid for eid in ev_ids if eid in valid_ids
            ]

        # 校验 noise_note_ids
        ts = parsed.get("trend_signals", {})
        if isinstance(ts, dict):
            noise = ts.get("noise_note_ids", [])
            ts["noise_note_ids"] = [nid for nid in noise if nid in valid_ids]

        # 校验 + 兜底 execution_brief（LLM 可能漏字段或写非法枚举值）
        for rec in recs:
            rec["execution_brief"] = _sanitize_execution_brief(
                rec.get("execution_brief")
            )

        logger.info(
            f"[analyze_layer] Layer3 done: "
            f"is_topic_trend={ts.get('is_topic_trend') if isinstance(ts, dict) else 'N/A'}, "
            f"strength={ts.get('trend_strength') if isinstance(ts, dict) else 'N/A'}, "
            f"recommendations={len(recs)}"
        )
        return parsed
    except Exception as e:
        logger.exception(f"[analyze_layer] Layer3 LLM call failed: {e}")
        return {"_error": str(e)}


async def run_layer3_streaming(
    llm: Any,
    top2: list[dict],
    all_notes: list[dict],
    layer2_output: dict,
    topic: str,
    user_preferences: dict | None = None,
    workflow_id: str = "",
    node_id: str = "analyze",
) -> dict:
    """Layer 3 流式版本：LLM streaming + 可读进度推送。"""
    from app.services.sse_bus import sse_bus

    if not llm:
        logger.warning("[analyze_layer] Layer3 streaming skipped: no LLM")
        return {"_skipped": "no_llm"}

    if not top2:
        return {"_skipped": "empty_input"}

    valid_ids = {n.get("content_id") for n in all_notes if n.get("content_id")}

    layer1_summary = json.dumps([
        {
            "content_id": n.get("content_id", ""),
            "title": n.get("title", ""),
            "viral_type": n.get("viral_type", "普通"),
            "viral_score": n.get("viral_score", 0),
            "likes": n.get("likes", 0),
            "author": n.get("author", ""),
        }
        for n in all_notes[:20]
    ], ensure_ascii=False, indent=2)

    layer2_str = json.dumps(layer2_output, ensure_ascii=False, indent=2) if layer2_output else "{}"
    user_preferences_section = _build_user_preferences_section(user_preferences or {})

    prompt = _LAYER3_PROMPT.format(
        topic=topic,
        user_preferences_section=user_preferences_section,
        layer1_summary=layer1_summary,
        layer2_output=layer2_str,
    )

    try:
        raw_parts: list[str] = []
        # 追加式流式推送（同 Layer2）：只发新增行，append-only
        emitted_lines: list[str] = []
        if workflow_id:
            await sse_bus.publish(workflow_id, "stream_chunk", {
                "node_id": node_id,
                "chunk": {"content": ""},
                "_append": "\n\n—— Layer 3 · 深度归因 ——",
            })
        async for chunk in llm.stream_chat(
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        ):
            content = chunk.get("content")
            if content:
                raw_parts.append(content)
                if workflow_id:
                    full_display = _make_layer3_display_text(content, raw_parts)
                    lines = [
                        l for l in full_display.split("\n")
                        if l.strip() and "正在" not in l
                    ]
                    new_lines = lines[len(emitted_lines):]
                    if new_lines:
                        emitted_lines.extend(new_lines)
                        await sse_bus.publish(workflow_id, "stream_chunk", {
                            "node_id": node_id,
                            "chunk": {"content": content},
                            "_append": "\n" + "\n".join(new_lines),
                        })

        raw = "".join(raw_parts)
        parsed = _parse_llm_json(raw)
        if parsed is None:
            logger.warning("[analyze_layer] Layer3 streaming JSON parse failed")
            return {"_parse_failed": True, "_raw": raw[:500]}

        recs = parsed.get("recommendations", [])
        for rec in recs:
            ev_ids = rec.get("evidence_note_ids", [])
            rec["evidence_note_ids"] = [eid for eid in ev_ids if eid in valid_ids]

        ts = parsed.get("trend_signals", {})
        if isinstance(ts, dict):
            noise = ts.get("noise_note_ids", [])
            ts["noise_note_ids"] = [nid for nid in noise if nid in valid_ids]

        for rec in recs:
            rec["execution_brief"] = _sanitize_execution_brief(rec.get("execution_brief"))

        logger.info(
            f"[analyze_layer] Layer3 streaming done: "
            f"is_topic_trend={ts.get('is_topic_trend') if isinstance(ts, dict) else 'N/A'}, "
            f"strength={ts.get('trend_strength') if isinstance(ts, dict) else 'N/A'}, "
            f"recommendations={len(recs)}"
        )
        return parsed
    except Exception as e:
        logger.exception(f"[analyze_layer] Layer3 streaming failed: {e}")
        return {"_error": str(e)}


def _make_layer3_display_text(latest_chunk: str, all_parts: list[str]) -> str:
    """将Layer3的JSON chunk转换为可读进度文本（累积式，每次返回完整文本）。"""
    import re as _re
    combined = "".join(all_parts) if all_parts else latest_chunk

    lines: list[str] = []

    if '"trend_signals"' in combined:
        signal_match = _re.search(r'"signal"\s*:\s*"([^"]+)"', combined)
        direction_match = _re.search(r'"direction"\s*:\s*"([^"]+)"', combined)
        if signal_match:
            lines.append(f"📊 趋势: {signal_match.group(1)}")
        if direction_match:
            lines.append(f"📈 方向: {direction_match.group(1)}")
        if not lines:
            lines.append("📊 正在分析跨笔记趋势信号...")

    if '"recommendations"' in combined:
        rec_match = _re.search(r'"title"\s*:\s*"([^"]+)"', combined)
        reason_match = _re.search(r'"reason"\s*:\s*"([^"]+)"', combined)
        if rec_match:
            lines.append(f"🎯 建议: {rec_match.group(1)}")
        if reason_match:
            lines.append(f"💡 理由: {reason_match.group(1)}")
        if not any("建议" in l or "理由" in l for l in lines):
            lines.append("🎯 正在生成选题方向建议...")

    if '"execution_brief"' in combined:
        lines.append("📝 正在生成执行指令...")

    if not lines:
        if len(combined) < 50:
            lines.append("🔬 正在做深度归因分析...")
        else:
            lines.append("⚙️ 正在生成深度分析...")

    return "\n".join(lines)
