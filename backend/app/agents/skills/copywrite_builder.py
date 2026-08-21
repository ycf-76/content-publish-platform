"""文案生成 Skill 集合：基于分析洞察 + 图片描述生成小红书文案。

可插拔架构（v2）：
- CopywriteSkillBase：基类，封装 LLM 调用 + JSON 解析 + 降级逻辑
- 4 个内置风格 Skill 子类：LivelyGirlCopywriteSkill / ElegantCopywriteSkill /
  ProfessionalCopywriteSkill / CasualCopywriteSkill
- 第三方可在 backend/skills/ 下新增自己的 CopywriteSkillBase 子类并 @register

风格作为 Skill 子类的类属性（style_instruction / fallback_template）注入，
不再硬编码到提示词字符串里。节点运行时按用户选择加载对应 Skill 子类。

红线：
- LLM 不可用时降级为模板，不抛异常
- 输出 JSON 解析失败时降级为模板
- 成本控制：max_tokens 由 DeepSeekAdapter 控制（默认 1500）
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.agents.skills.base import Skill
from app.agents.skills.registry import register

logger = logging.getLogger(__name__)


# ============================================================================
# 基类：所有文案 Skill 的公共逻辑
# ============================================================================


class CopywriteSkillBase(Skill):
    """文案 Skill 基类。

    子类只需声明：
    - name: Skill 唯一标识（如 "lively_girl"）
    - display_name: 前端展示名（如 "活泼少女风文案"）
    - style_instruction: 注入到 prompt 的调性指令（中文一段话）
    - fallback_template: LLM 不可用时的降级模板（含 {topic}/{direction} 占位符）

    子类可选择性覆盖：
    - build_prompt(): 自定义 prompt 构造逻辑
    - parse_response(): 自定义 LLM 输出解析
    - fallback(): 自定义降级文案
    """

    node_type = "copywrite"
    # 子类必须覆盖以下字段
    name: str = ""
    display_name: str = ""
    description: str = ""
    style_instruction: str = ""
    fallback_template: str = ""

    # 公共 prompt 模板（子类一般不需要改）
    # v3：主题类型感知——知识型/清单型主题生成结构化干货，而非种草文案
    # v4：注入用户级长期记忆（偏好文风/历史选题/历史文案摘要）
    # v5：消费 analyze 的 execution_brief 执行指令 + Layer2 patterns 爆款模式
    PROMPT_TEMPLATE = """你是一位资深小红书内容创作师，严格按照执行指令产出高质量内容。

**主题（必须围绕，不可偏离）**: {topic}

**优先级规则**: 执行指令中的 user_creative_brief、selected_direction、direction_note
优先于热点分析；如果热点执行建议与用户创作要求冲突，必须服从用户创作要求。

**【执行指令】（来自分析节点，必须严格遵循）**:
{execution_brief_section}

**爆款模式分析**（Layer2 识别的标题钩子/内容结构/情绪触发点，作为创作参考）:
{patterns_json}

**深度分析摘要**（Layer3 趋势信号 + 选题建议，仅作参考，不得改变主题方向）:
{insights_json}

**图片描述**（image_gen 节点生成的图片信息）:
{images_json}
{reference_section}{memory_section}
**创作要求**:

1. 内容类型：严格按照执行指令的 content_type 产出，不要自行判断主题类型
   - 清单型：正文必须是结构化清单，用编号或分点呈现实际知识点，每项配简短释义或例句
   - 叙事型：正文以故事/经历为主线，有场景描写和情感推进
   - 对比型：正文对比两个或多个事物的优劣，用表格或分栏呈现
   - 教程型：正文按步骤教学，每步配操作说明和注意事项
   - 观点型：正文表达明确观点，有论据支撑，引发讨论

2. 正文结构：严格按照执行指令的 recommended_structure 顺序组织段落，不要自行调整结构

3. 标题：15-20字，使用执行指令的 title_style 类型，可参考爆款模式分析的标题模板
   - 清单型标题直接点明主题和价值（如"四级高频词100个｜考前必背"）
   - 其他类型标题有吸引力{emoji_clause}

4. 语气：遵循执行指令的 tone，同时叠加下方"用户指定文风"

5. key_points：把正文核心要点拆成 5-10 个独立条目
   - 清单型：每条是一个完整的知识点（如 "abandon v.放弃；抛弃"）
   - 其他类型：每条 15 字以内的核心要点

6. structured_items：仅清单型输出，每项 {{ "term": "词条", "definition": "释义/例句" }}

7. 标签：{tag_instruction}

8. 正文长度：{length_instruction}

9. 若提供了"用户历史记忆"，可参考其历史选题/文案风格保持个人调性连贯，但不要直接复制历史文案

**用户指定文风（叠加在执行指令 tone 之上）**: {style_instruction}

**输出严格 JSON**（不要 markdown fence，不要额外文字）:
{{
  "title": "标题",
  "content": "正文（按执行指令的结构和类型产出）",
  "tags": ["标签1", "标签2", "标签3", "标签4", "标签5"],
  "key_points": ["知识点1", "知识点2", "知识点3"],
  "structured_items": [{{"term": "词条", "definition": "释义"}}]
}}
"""

    STREAMING_PROMPT_TEMPLATE = """你是一位资深小红书内容创作师，请直接产出高质量的小红书文案。

**主题**: {topic}

**执行指令**:
{execution_brief_section}

**爆款参考**:
{patterns_json}

**深度分析**:
{insights_json}
{reference_section}{memory_section}

**要求**:
- 内容类型：{content_type_hint}
- 结构：{structure_hint}
- 标题风格：{title_style_hint}
- 语气：{tone_hint} + {style_instruction}
- 长度：{length_instruction}
- 标签：{tag_instruction}
{emoji_clause}

**请直接输出文案，格式如下**（不要输出JSON，不要加任何解释说明）:

---
📌 标题：（你的标题）

正文开始...
（按要求的结构和类型撰写正文内容）

#标签1 #标签2 #标签3 #标签4 #标签5
---

直接开始写，不要有任何前缀或解释。
"""

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """执行文案生成。

        inputs 约定：
        - llm: LLMProtocol 实例（None 时降级为模板）
        - topic: 工作流主题
        - insights: analyze 节点的 insights 字段（Layer3 输出：trend_signals + recommendations）
        - patterns: analyze 节点的 patterns 字段（Layer2 输出：标题钩子/内容结构/情绪触发点）
        - execution_brief: analyze Layer3 给下游的执行指令，字段：
            content_type / recommended_structure / tone / title_style / visual_suggestion
        - image_details: image_gen 节点的 image_details 列表
        - image_style: image_gen 节点的 style 字段
        - reference: 选题池参考素材（可选 dict），含 title/summary/url/platform 等
        - user_memory: 用户级长期记忆（可选 dict），字段：
            writing_style / image_style / preferred_topics / avoided_topics
            / recent_topics / recent_copywrites
        """
        llm = inputs.get("llm")
        topic = inputs.get("topic", "")
        insights = inputs.get("insights", {}) or {}
        patterns = inputs.get("patterns", {}) or {}
        execution_brief = inputs.get("execution_brief", {}) or {}
        image_details = inputs.get("image_details", []) or []
        image_style = inputs.get("image_style", "")
        reference = inputs.get("reference", {}) or {}
        user_memory = inputs.get("user_memory", {}) or {}
        content_length = inputs.get("content_length")
        auto_emoji = inputs.get("auto_emoji", True)
        auto_tags = inputs.get("auto_tags", True)

        if not llm:
            logger.warning(
                f"[{self.__class__.__name__}] LLM unavailable, using fallback"
            )
            return self.fallback(topic, insights, image_details)

        prompt = self.build_prompt(
            topic, insights, patterns, execution_brief,
            image_details, image_style, reference, user_memory,
            content_length=content_length,
            auto_emoji=auto_emoji,
            auto_tags=auto_tags,
        )

        try:
            resp = await llm.chat(
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            raw = resp.get("content", "")
            result = self.parse_response(raw)
            if result is None:
                logger.warning(
                    f"[{self.__class__.__name__}] LLM JSON parse failed, fallback"
                )
                return self.fallback(topic, insights, image_details)
            return result
        except Exception as e:
            logger.exception(f"[{self.__class__.__name__}] LLM call failed: {e}")
            return self.fallback(topic, insights, image_details)

    async def execute_streaming(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """流式文案生成：纯文本prompt → LLM streaming → SSE逐字推送 → 完成后解析为结构化数据。

        与 execute 的区别：
        - 使用 STREAMING_PROMPT_TEMPLATE（纯文本输出，不强制JSON）
        - 不使用 response_format={"type": "json_object"}
        - 每个 chunk 直接推送给前端显示（用户看到的是可读文案）
        - 收集完整文本后，后处理解析为结构化字段用于卡片渲染
        """
        from app.services.sse_bus import sse_bus
        import re as _re

        llm = inputs.get("llm")
        topic = inputs.get("topic", "")
        insights = inputs.get("insights", {}) or {}
        patterns = inputs.get("patterns", {}) or {}
        execution_brief = inputs.get("execution_brief", {}) or {}
        image_details = inputs.get("image_details", []) or []
        image_style = inputs.get("image_style", "")
        reference = inputs.get("reference", {}) or {}
        user_memory = inputs.get("user_memory", {}) or {}
        content_length = inputs.get("content_length")
        auto_emoji = inputs.get("auto_emoji", True)
        auto_tags = inputs.get("auto_tags", True)
        workflow_id = inputs.get("workflow_id", "")
        node_id = inputs.get("node_id", "copywrite")

        if not llm:
            logger.warning(f"[{self.__class__.__name__}] LLM unavailable, using fallback")
            return self.fallback(topic, insights, image_details)

        prompt = self._build_streaming_prompt(
            topic, insights, patterns, execution_brief,
            image_details, image_style, reference, user_memory,
            content_length=content_length,
            auto_emoji=auto_emoji,
            auto_tags=auto_tags,
        )

        try:
            raw_parts: list[str] = []
            async for chunk in llm.stream_chat(
                messages=[{"role": "user", "content": prompt}],
            ):
                content = chunk.get("content")
                if content:
                    raw_parts.append(content)
                    if workflow_id:
                        await sse_bus.publish(workflow_id, "agent_thinking", {
                            "node_id": node_id,
                            "chunk": {"content": content},
                        })

            full_text = "".join(raw_parts)
            result = self._parse_streaming_response(full_text)
            return result
        except Exception as e:
            logger.exception(f"[{self.__class__.__name__}] LLM streaming failed: {e}")
            return self.fallback(topic, insights, image_details)

    def _build_streaming_prompt(
        self,
        topic: str,
        insights: dict,
        patterns: dict,
        execution_brief: dict,
        image_details: list[dict],
        image_style: str,
        reference: dict | None = None,
        user_memory: dict | None = None,
        content_length: int | None = None,
        auto_emoji: bool = True,
        auto_tags: bool = True,
    ) -> str:
        """构造流式输出的纯文本prompt。"""
        execution_brief_section = _build_execution_brief_section(execution_brief)
        patterns_summary = _build_patterns_summary(patterns)
        insights_summary = _build_insights_summary(insights)
        reference_section = _build_reference_summary(reference or {})
        memory_section = _build_memory_summary(user_memory or {})
        length_instruction = _build_length_instruction(content_length)
        emoji_clause = _build_emoji_clause(auto_emoji)
        tag_instruction = _build_tag_instruction(auto_tags)

        content_type_hint = execution_brief.get("content_type", "叙事型") or "叙事型"
        structure_hint = ", ".join(execution_brief.get("recommended_structure", []) or ["引入", "主体内容", "总结"])
        title_style_hint = execution_brief.get("title_style", "利益型") or "利益型"
        tone_hint = execution_brief.get("tone", "自然口语化") or "自然口语化"

        return self.STREAMING_PROMPT_TEMPLATE.format(
            topic=topic,
            execution_brief_section=execution_brief_section,
            patterns_json=patterns_summary[:1500],
            insights_json=insights_summary[:1000],
            reference_section=reference_section,
            memory_section=memory_section,
            style_instruction=self.style_instruction,
            length_instruction=length_instruction,
            emoji_clause=emoji_clause,
            tag_instruction=tag_instruction,
            content_type_hint=content_type_hint,
            structure_hint=structure_hint,
            title_style_hint=title_style_hint,
            tone_hint=tone_hint,
        )

    def _parse_streaming_response(self, text: str) -> dict[str, Any]:
        """从流式纯文本中解析出结构化字段。

        尝试多种模式匹配：
        1. 📌 标题：xxx → 提取标题
        2. #标签 格式 → 提取tags
        3. 剩余正文 → content
        """
        import re as _re

        result = {
            "title": "",
            "content": text,
            "tags": [],
            "key_points": [],
            "structured_items": [],
            "_source": "streaming",
        }

        cleaned = text.strip()

        title_match = _re.search(r"[📌｜]*\s*标题[：:]\s*(.+?)(?:\n|$)", cleaned)
        if title_match:
            result["title"] = title_match.group(1).strip()
            cleaned = cleaned[title_match.end():].strip()

        tags_matches = _re.findall(r"#([\w\u4e00-\u9fff]+)", cleaned)
        if tags_matches:
            result["tags"] = tags_matches[:5]
            cleaned = _re.sub(r"\s*#[\w\u4e00-\u9fff]+\s*", "", cleaned).strip()

        if cleaned.startswith("---"):
            cleaned = _re.sub(r"^---+\s*", "", cleaned).strip()
        if cleaned.endswith("---"):
            cleaned = _re.sub(r"\s*---+$", "", cleaned).strip()

        result["content"] = cleaned.strip() or text

        lines = [l.strip() for l in result["content"].split("\n") if l.strip()]
        key_points = [l for l in lines if len(l) <= 50 and not l.startswith("#")]
        result["key_points"] = key_points[:10]

        if not result["title"]:
            first_line = lines[0] if lines else topic
            result["title"] = first_line[:30]

        if not result["tags"]:
            result["tags"] = ["小红书运营", "内容创作", "干货分享"]

        return result

    def build_prompt(
        self,
        topic: str,
        insights: dict,
        patterns: dict,
        execution_brief: dict,
        image_details: list[dict],
        image_style: str,
        reference: dict | None = None,
        user_memory: dict | None = None,
        content_length: int | None = None,
        auto_emoji: bool = True,
        auto_tags: bool = True,
    ) -> str:
        """构造 LLM prompt。子类可覆盖以自定义 prompt 结构。"""
        execution_brief_section = _build_execution_brief_section(execution_brief)
        patterns_summary = _build_patterns_summary(patterns)
        insights_summary = _build_insights_summary(insights)
        images_summary = _build_images_summary(image_details, image_style)
        reference_section = _build_reference_summary(reference or {})
        memory_section = _build_memory_summary(user_memory or {})
        # 根据开关构造动态指令片段
        length_instruction = _build_length_instruction(content_length)
        emoji_clause = _build_emoji_clause(auto_emoji)
        tag_instruction = _build_tag_instruction(auto_tags)
        return self.PROMPT_TEMPLATE.format(
            topic=topic,
            execution_brief_section=execution_brief_section,
            patterns_json=patterns_summary,
            insights_json=insights_summary,
            images_json=images_summary,
            reference_section=reference_section,
            memory_section=memory_section,
            style_instruction=self.style_instruction,
            length_instruction=length_instruction,
            emoji_clause=emoji_clause,
            tag_instruction=tag_instruction,
        )

    def parse_response(self, raw: str) -> dict | None:
        """解析 LLM 输出的 JSON。三级降级（直接/去 fence/提取首个对象）。"""
        if not raw:
            return None

        # Level 1: 直接解析
        try:
            return _validate_copywrite_json(json.loads(raw))
        except json.JSONDecodeError:
            pass

        # Level 2: 去 markdown fence
        fenced = re.sub(r"^```(?:json)?\s*\n?", "", raw.strip(), flags=re.MULTILINE)
        fenced = re.sub(r"\n?```\s*$", "", fenced).strip()
        try:
            return _validate_copywrite_json(json.loads(fenced))
        except json.JSONDecodeError:
            pass

        # Level 3: 提取首个 JSON 对象
        match = re.search(r"\{[\s\S]*\}", fenced)
        if match:
            try:
                return _validate_copywrite_json(json.loads(match.group(0)))
            except json.JSONDecodeError:
                pass

        logger.warning(
            f"[{self.__class__.__name__}] JSON parse failed, raw[:200]={raw[:200]}"
        )
        return None

    def fallback(
        self,
        topic: str,
        insights: dict,
        image_details: list[dict],
    ) -> dict:
        """降级：LLM 不可用时，用模板生成基础文案。子类可覆盖。

        红线：fallback 始终围绕用户 topic，不用 insights 的 topic_direction
        （topic_direction 来自搜索结果分析，可能偏离用户原始意图）。
        """
        # 模板标题
        title = f"{topic}分享｜干货整理"[:20]

        # 模板正文（用 Skill 自带的 fallback_template，体现风格差异）
        template = self.fallback_template or _DEFAULT_FALLBACK_TEMPLATE
        content = template.format(topic=topic, direction=topic)

        # 模板标签
        tags = [topic, "分享", "干货", "日常"][:5]

        # 模板 key_points（供 image_gen 渲染卡片，避免正则乱提取）
        key_points = [
            f"{topic}核心概念",
            "实操建议与注意事项",
            "常见问题与避坑指南",
        ][:5]

        return {
            "title": title,
            "content": content,
            "tags": tags,
            "key_points": key_points,
            "_source": "fallback",
            "_skill": self.name,
        }


# ============================================================================
# 内置 4 种风格 Skill 子类
# ============================================================================


@register
class LivelyGirlCopywriteSkill(CopywriteSkillBase):
    """活泼少女风文案。"""

    name = "lively_girl"
    display_name = "活泼少女风"
    description = "语气可爱俏皮，多用感叹号和 emoji，像闺蜜聊天"
    style_instruction = (
        "活泼少女风：语气可爱俏皮，多用感叹号和 emoji（2-3个），"
        "有少女感，像闺蜜聊天"
    )
    fallback_template = (
        "{topic}也太可爱了吧！✨\n\n"
        "今天来聊聊{direction}～\n\n"
        "1. 核心要点：找到适合自己的方式最重要！\n"
        "2. 实操建议：从小处着手，慢慢来～\n"
        "3. 注意事项：保持耐心，不要急！\n\n"
        "希望这篇对你有帮助呀，评论区聊～💕\n"
        "（注：LLM 不可用，降级模板生成）"
    )


@register
class ElegantCopywriteSkill(CopywriteSkillBase):
    """知性优雅风文案。"""

    name = "elegant"
    display_name = "知性优雅风"
    description = "语气从容得体，措辞考究，像杂志专栏"
    style_instruction = (
        "知性优雅风：语气从容得体，措辞考究，少用 emoji（最多1个），"
        "有沉淀感，像杂志专栏"
    )
    fallback_template = (
        "关于{topic}，一些沉淀的思考。\n\n"
        "{direction}这件事，需要从容地对待。\n\n"
        "1. 核心要点：找到自己的节奏\n"
        "2. 实操建议：循序渐进，不疾不徐\n"
        "3. 注意事项：保持耐心，时间会给出答案\n\n"
        "愿你在这条路上走得从容。\n"
        "（注：LLM 不可用，降级模板生成）"
    )


@register
class ProfessionalCopywriteSkill(CopywriteSkillBase):
    """专业干货风文案。"""

    name = "professional"
    display_name = "专业干货风"
    description = "语气专业克制，逻辑清晰，分点论述，像行业分享"
    style_instruction = (
        "专业干货风：语气专业克制，逻辑清晰，分点论述，"
        "几乎不用 emoji，像行业分享"
    )
    fallback_template = (
        "{topic}｜核心要点整理\n\n"
        "关于{direction}，整理如下：\n\n"
        "1. 核心要点：围绕主线，建立体系\n"
        "2. 实操建议：拆解为可执行步骤，逐项落地\n"
        "3. 注意事项：关注关键指标，及时复盘调整\n\n"
        "以上，供参考。\n"
        "（注：LLM 不可用，降级模板生成）"
    )


@register
class CasualCopywriteSkill(CopywriteSkillBase):
    """慵懒随性风文案。"""

    name = "casual"
    display_name = "慵懒随性风"
    description = "语气松弛随性，口语化，偶尔吐槽，像周末下午的闲聊"
    style_instruction = (
        "慵懒随性风：语气松弛随性，口语化，偶尔吐槽，"
        "像周末下午的闲聊"
    )
    fallback_template = (
        "今天想聊聊{topic}～\n\n"
        "{direction}这事儿吧，说难也不难。\n\n"
        "随便说几点：\n"
        "1. 别太较真，慢慢来\n"
        "2. 找到自己舒服的方式就行\n"
        "3. 急不来的，急也没用\n\n"
        "就这样吧，有问题评论区唠～\n"
        "（注：LLM 不可用，降级模板生成）"
    )


# ============================================================================
# 公共辅助函数（保持向后兼容）
# ============================================================================


_DEFAULT_FALLBACK_TEMPLATE = (
    f"今天来聊聊{{topic}}～\n\n"
    f"整理了一些实用要点：\n\n"
    f"1. 核心要点：找到适合自己的方式\n"
    f"2. 实操建议：从小处着手，循序渐进\n"
    f"3. 注意事项：保持耐心，不要急于求成\n\n"
    f"希望这篇分享对你有帮助～\n"
    f"（注：LLM 不可用，降级模板生成）"
)


def _build_execution_brief_section(brief: dict) -> str:
    """把 analyze 的 execution_brief 压缩成 prompt 用的执行指令段落。

    无 execution_brief 时返回兜底指令（让 LLM 自由发挥，不阻塞流程）。
    有 execution_brief 时返回格式化的指令，作为硬约束注入 prompt。
    """
    if not brief or not isinstance(brief, dict):
        return (
            "（无执行指令，请基于主题自由判断内容类型和结构）\n"
            "- content_type: 叙事型\n"
            "- recommended_structure: [\"引入\", \"主体内容\", \"总结\"]\n"
            "- tone: 自然口语化\n"
            "- title_style: 利益型\n"
            "- visual_suggestion: 简洁排版"
        )

    content_type = brief.get("content_type", "叙事型")
    structure = brief.get("recommended_structure", [])
    if isinstance(structure, list):
        structure_str = " → ".join(str(s) for s in structure) if structure else "未指定"
    else:
        structure_str = str(structure) or "未指定"
    tone = brief.get("tone", "自然口语化")
    title_style = brief.get("title_style", "利益型")
    visual = brief.get("visual_suggestion", "简洁排版")
    user_brief = str(brief.get("user_creative_brief", "") or "").strip()
    selected_direction = str(brief.get("selected_direction", "") or "").strip()
    direction_note = str(brief.get("direction_note", "") or "").strip()

    priority_lines: list[str] = []
    if user_brief:
        priority_lines.append(f"- 用户创作要求（最高优先级）: {user_brief[:1200]}")
    if selected_direction:
        priority_lines.append(f"- 用户选择方向: {selected_direction[:300]}")
    if direction_note:
        priority_lines.append(f"- 用户补充要求: {direction_note[:600]}")

    priority_section = "\n".join(priority_lines) + "\n" if priority_lines else ""
    return priority_section + (
        f"- 内容类型 (content_type): {content_type}\n"
        f"- 正文结构 (recommended_structure): {structure_str}\n"
        f"- 语气风格 (tone): {tone}\n"
        f"- 标题类型 (title_style): {title_style}\n"
        f"- 配图建议 (visual_suggestion): {visual}"
    )


def _build_patterns_summary(patterns: dict) -> str:
    """把 analyze Layer2 的 patterns 压缩成 prompt 用的摘要。

    patterns 结构（Layer2 输出）：
    - title_patterns: list[dict]（标题钩子模式）
    - content_structures: list[dict]（内容结构骨架）
    - emotion_triggers: list[dict]（情绪触发点）

    无 patterns 时返回空（prompt 中段落消失，不影响流程）。
    """
    if not patterns or not isinstance(patterns, dict):
        return "（无爆款模式分析数据）"

    # 如果是降级输出（_skipped / _error / _parse_failed），直接返回空
    if any(k in patterns for k in ("_skipped", "_error", "_parse_failed")):
        return "（爆款模式分析未执行或失败，请基于主题自由发挥）"

    parts: list[str] = []

    # 标题钩子模式
    title_patterns = patterns.get("title_patterns", [])
    if title_patterns and isinstance(title_patterns, list):
        parts.append("标题钩子模式:")
        for i, p in enumerate(title_patterns[:3], 1):
            if isinstance(p, dict):
                ptype = p.get("type", "")
                template = p.get("template", "")
                parts.append(f"  {i}. [{ptype}] 模板: {template}")

    # 内容结构骨架
    content_structures = patterns.get("content_structures", [])
    if content_structures and isinstance(content_structures, list):
        parts.append("内容结构骨架:")
        for i, s in enumerate(content_structures[:2], 1):
            if isinstance(s, dict):
                structure = s.get("structure", "")
                desc = s.get("description", "")
                parts.append(f"  {i}. {structure} — {desc}")

    # 情绪触发点
    emotion_triggers = patterns.get("emotion_triggers", [])
    if emotion_triggers and isinstance(emotion_triggers, list):
        parts.append("情绪触发点:")
        for i, e in enumerate(emotion_triggers[:2], 1):
            if isinstance(e, dict):
                emotion = e.get("emotion", "")
                reason = e.get("reason", "")
                parts.append(f"  {i}. [{emotion}] {reason}")

    return "\n".join(parts) if parts else "（无有效爆款模式数据）"


def _build_insights_summary(insights: dict) -> str:
    """把 analyze Layer3 的 insights 压缩成 prompt 用的摘要。

    修 bug：原来从 insights 里读 patterns，但 patterns 是 analyze_output 顶层字段，
    不在 insights 里。现在只处理 insights 自身的 trend_signals + recommendations，
    patterns 由专门的 _build_patterns_summary 处理。

    注意：recommendations 只取 title_template / content_structure / emotion_hook，
    不取 topic_direction（避免 LLM 被 topic_direction 带偏，改变用户原始主题）。
    """
    if not insights or not isinstance(insights, dict):
        return "（无深度分析数据）"

    # 降级输出直接返回
    if any(k in insights for k in ("_skipped", "_error", "_parse_failed")):
        return "（深度分析未执行或失败，请基于主题自由发挥）"

    parts: list[str] = []

    # 趋势信号
    trend_signals = insights.get("trend_signals", {})
    if trend_signals and isinstance(trend_signals, dict):
        is_trend = trend_signals.get("is_topic_trend")
        strength = trend_signals.get("trend_strength", "")
        basis = trend_signals.get("trend_basis", "")
        if is_trend is not None:
            parts.append(f"趋势信号: {'是话题型趋势' if is_trend else '非话题型趋势'}, 强度={strength}")
            if basis:
                parts.append(f"  依据: {basis[:100]}")

    # 选题建议（只取风格/结构字段，不取 topic_direction 避免带偏主题）
    recommendations = insights.get("recommendations", [])
    if recommendations and isinstance(recommendations, list):
        parts.append("选题建议参考:")
        for i, r in enumerate(recommendations[:2], 1):
            if isinstance(r, dict):
                title_template = r.get("title_template", "")
                content_structure = r.get("content_structure", "")
                emotion_hook = r.get("emotion_hook", "")
                parts.append(
                    f"  {i}. 标题模板: {title_template} | 结构: {content_structure} | 情绪: {emotion_hook}"
                )

    return "\n".join(parts) if parts else "（无有效深度分析数据）"


def _build_images_summary(image_details: list[dict], style: str) -> str:
    """把 image_gen 的 image_details 压缩成 prompt 用的摘要。"""
    if not image_details:
        return "（无图片信息，请基于主题撰写通用文案）"

    parts: list[str] = []
    if style:
        parts.append(f"统一风格: {style}")

    for i, detail in enumerate(image_details[:3], 1):
        role = detail.get("role", f"image_{i}")
        desc = detail.get("description", "")
        prompt = detail.get("prompt", "")[:80]
        parts.append(f"  图{i} [{role}]: {desc or prompt}")

    return "\n".join(parts)


def _build_reference_summary(reference: dict) -> str:
    """把选题池参考素材压缩成 prompt 用的段落。

    无参考素材时返回空字符串（prompt 中该段落消失，不影响原有流程）。
    有参考素材时返回格式化的段落，明确告知 LLM "参考"而非"抄袭"。
    """
    if not reference:
        return ""

    parts: list[str] = ["", "**参考素材**（来自选题池，请参考其角度/结构，切勿直接抄袭）:"]

    title = (reference.get("title") or "").strip()
    if title:
        parts.append(f"  参考标题: {title[:200]}")

    summary = (reference.get("summary") or "").strip()
    if summary:
        parts.append(f"  参考摘要: {summary[:500]}")

    platform = (reference.get("platform") or "").strip()
    if platform:
        parts.append(f"  来源平台: {platform}")

    # 互动数据（帮助 LLM 判断参考内容的受欢迎程度）
    likes = reference.get("likes") or 0
    comments = reference.get("comments") or 0
    collects = reference.get("collects") or 0
    if likes or comments or collects:
        parts.append(f"  互动数据: 点赞{likes} 评论{comments} 收藏{collects}")

    source_keyword = (reference.get("source_keyword") or "").strip()
    if source_keyword:
        parts.append(f"  来源关键词: {source_keyword}")

    parts.append("")  # 末尾空行，与后续"文案要求"分隔
    return "\n".join(parts)


def _build_memory_summary(user_memory: dict) -> str:
    """把用户级长期记忆压缩成 prompt 用的段落。

    控制策略（避免 prompt 膨胀）：
    - 偏好主题/避免主题：截前 5 个
    - 历史选题：截前 5 条
    - 历史文案：截前 3 条 title
    - 无任何记忆时返回空串（prompt 中段落消失）
    """
    if not user_memory:
        return ""

    parts: list[str] = ["", "**用户历史记忆**（供参考保持个人调性，不要直接复制）:"]
    has_any = False

    preferred = user_memory.get("preferred_topics") or []
    if preferred:
        has_any = True
        parts.append(f"  偏好主题: {', '.join(str(t) for t in preferred[:5])}")

    avoided = user_memory.get("avoided_topics") or []
    if avoided:
        has_any = True
        parts.append(f"  避免主题: {', '.join(str(t) for t in avoided[:5])}")

    recent_topics = user_memory.get("recent_topics") or []
    if recent_topics:
        has_any = True
        parts.append(f"  最近选题: {', '.join(str(t)[:20] for t in recent_topics[:5])}")

    recent_copywrites = user_memory.get("recent_copywrites") or []
    if recent_copywrites:
        has_any = True
        parts.append("  最近文案标题:")
        for i, c in enumerate(recent_copywrites[:3], 1):
            if isinstance(c, dict):
                parts.append(f"    {i}. {str(c.get('title', ''))[:40]}")

    if not has_any:
        return ""

    parts.append("")  # 末尾空行，与后续分隔
    return "\n".join(parts)


def _validate_copywrite_json(parsed: dict) -> dict | None:
    """校验并补全 LLM 输出的 JSON 字段。返回 None 表示校验失败。"""
    if not isinstance(parsed, dict):
        return None

    title = (parsed.get("title") or "").strip()
    content = (parsed.get("content") or "").strip()
    tags = parsed.get("tags") or []
    key_points = parsed.get("key_points") or []
    structured_items = parsed.get("structured_items") or []

    if not title:
        title = "关于这个话题的分享"
    if not content:
        return None  # 内容空说明 LLM 输出异常，触发降级
    if not isinstance(tags, list):
        tags = []
    tags = [str(t).strip() for t in tags if str(t).strip()][:8]
    if not tags:
        tags = ["分享", "日常", "干货"]
    # key_points 校验：必须是字符串列表，每个不超过 30 字
    if not isinstance(key_points, list):
        key_points = []
    key_points = [
        str(p).strip()[:30]
        for p in key_points
        if str(p).strip()
    ][:5]
    # structured_items 校验：知识清单型主题的结构化数据，供卡片精确排版
    if not isinstance(structured_items, list):
        structured_items = []
    cleaned_items = []
    for item in structured_items:
        if not isinstance(item, dict):
            continue
        term = str(item.get("term") or "").strip()
        definition = str(item.get("definition") or "").strip()
        if term:
            cleaned_items.append({"term": term[:50], "definition": definition[:200]})
    structured_items = cleaned_items[:30]  # 上限 30 项，避免卡片过多

    result = {
        "title": title,
        "content": content,
        "tags": tags,
        "_source": "llm",
    }
    if key_points:
        result["key_points"] = key_points
    if structured_items:
        result["structured_items"] = structured_items
    return result


# ============================================================================
# 向后兼容入口：旧代码 build_copywrite() / _fallback_copywrite() 仍可调用
# ============================================================================


async def build_copywrite(
    llm: Any,
    topic: str,
    insights: dict,
    image_details: list[dict],
    image_style: str = "",
    writing_style: str = "",
) -> dict:
    """向后兼容入口：按 writing_style 名称加载对应 Skill 并执行。

    新代码应直接用 CopywriteSkillBase 子类 + registry.get() 调用。
    """
    from app.agents.skills.registry import SkillRegistry

    registry = SkillRegistry.instance()
    # writing_style 是中文名（如"活泼少女"），需要映射到 skill name
    skill_name = _WRITING_STYLE_TO_SKILL_NAME.get(writing_style.strip(), "lively_girl")
    skill_cls = registry.get("copywrite", skill_name) or LivelyGirlCopywriteSkill

    skill = skill_cls()  # type: ignore[assignment]
    result = await skill.execute({
        "llm": llm,
        "topic": topic,
        "insights": insights,
        "image_details": image_details,
        "image_style": image_style,
    })
    result["_skill"] = skill.name
    return result


def _fallback_copywrite(
    topic: str,
    insights: dict,
    image_details: list[dict],
    writing_style: str = "",
) -> dict:
    """向后兼容入口：降级文案。"""
    skill_name = _WRITING_STYLE_TO_SKILL_NAME.get(writing_style.strip(), "lively_girl")
    from app.agents.skills.registry import SkillRegistry

    registry = SkillRegistry.instance()
    skill_cls = registry.get("copywrite", skill_name) or LivelyGirlCopywriteSkill
    skill = skill_cls()  # type: ignore[assignment]
    return skill.fallback(topic, insights, image_details)


# 中文名 → skill name 映射（向后兼容旧版 model_settings.writing_style）
_WRITING_STYLE_TO_SKILL_NAME: dict[str, str] = {
    "活泼少女": "lively_girl",
    "知性优雅": "elegant",
    "专业干货": "professional",
    "慵懒随性": "casual",
}


# ============================================================================
# 配置中心开关 → prompt 指令片段构造（content_length / auto_emoji / auto_tags）
# ============================================================================


def _build_length_instruction(content_length: int | None) -> str:
    """把用户期望字数转成 prompt 里的长度指令。

    None 或越界 → 返回默认规则（清单型 400-800 字，其他 200-400 字）。
    有效值 → 清单型按知识点自适应但不超过用户值，其他类型严格按用户值 ±20%。
    """
    if content_length is None or content_length < 50 or content_length > 2000:
        return (
            "按知识点数量自适应（可 400-800 字），确保知识点完整不截断\n"
            "   - 其他类型：200-400字，分段清晰"
        )
    cl = int(content_length)
    lo = max(50, int(cl * 0.8))
    hi = int(cl * 1.2)
    return (
        f"清单型：按知识点数量自适应，但正文总长控制在 {lo}-{hi} 字，"
        f"确保知识点完整不截断\n"
        f"   - 其他类型：正文 {lo}-{hi}字，分段清晰"
    )


def _build_emoji_clause(auto_emoji: bool) -> str:
    """auto_emoji=False 时覆盖风格 skill 默认，指示完全不使用 emoji。"""
    if auto_emoji:
        return "，可用 emoji 点缀（1-2个）"
    return "，不要使用任何 emoji"


def _build_tag_instruction(auto_tags: bool) -> str:
    """auto_tags=False 时指示不生成标签，前端会得到空 tags 数组。"""
    if auto_tags:
        return "5-8个相关话题标签"
    return "不要生成任何标签，tags 返回空数组 []"