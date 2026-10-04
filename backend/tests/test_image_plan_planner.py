import asyncio

from app.agents.nodes.image_plan_planner import (
    ContentPlanner,
    TemplateMatcher,
    _build_structured_draft,
    build_content_plan_prompt,
)
from app.templates.registry import TemplateRegistry


def test_prompt_schema_is_generated_from_registry():
    prompt = build_content_plan_prompt(
        topic="AI 教育",
        title="AI 学习",
        content="正文",
        tags=["AI"],
        key_points=["要点"],
        visual_suggestion="",
    )

    assert '"type": "cover"' in prompt
    assert '"type": "steps"' in prompt
    assert '"type": "big_quote"' in prompt


def test_template_matcher_returns_registered_template():
    matcher = TemplateMatcher(TemplateRegistry())

    template_id = matcher.match_template("AI 编程入门", "教程型")
    assert template_id in {"dark_tech", "minimal_white"}

    decoration = matcher.match_decoration(template_id, "教程型")
    assert decoration["type"]


def test_content_planner_structured_path_builds_format_plan():
    async def run():
        planner = ContentPlanner(TemplateRegistry())
        draft, model_used = await planner.plan(
            topic="知识清单",
            title="标题",
            content="",
            tags=[],
            key_points=[],
            structured_items=[
                {"term": "A", "definition": "a"},
                {"term": "B", "definition": "b"},
                {"term": "C", "definition": "c"},
                {"term": "D", "definition": "d"},
            ],
            content_type="清单型",
            visual_suggestion="",
            llm=None,
        )
        return draft, model_used

    draft, model_used = asyncio.run(run())
    assert model_used == "structured_split (no LLM)"
    assert draft["pages"][0]["type"] == "cover"
    assert draft["suggested_template"]
    assert draft["suggested_decoration"]["type"]


def test_content_planner_llm_path_does_not_require_llm_to_select_template():
    class _ScriptedLLM:
        model_name = "mock"

        async def chat(self, messages, response_format=None):
            return {
                "content": (
                    '{"pages":[{"type":"cover","title":"封面","subtitle":"副标题",'
                    '"footer":"@灵犀工坊"},{"type":"steps","title":"步骤",'
                    '"steps":[{"title":"第一步","desc":"描述"}]}]}'
                ),
                "token_usage": 1,
            }

    async def run():
        planner = ContentPlanner(TemplateRegistry())
        draft, model_used = await planner.plan(
            topic="AI 教育",
            title="AI 教育",
            content="这是正文内容",
            tags=["AI"],
            key_points=["要点"],
            structured_items=[],
            content_type="教程型",
            visual_suggestion="",
            llm=_ScriptedLLM(),
        )
        return draft, model_used

    draft, model_used = asyncio.run(run())
    assert model_used == "mock"
    assert draft["pages"][0]["type"] == "cover"
    assert draft["suggested_template"]
    assert draft["suggested_template"] != "suggested_template"


def test_structured_draft_follows_template_page_fields():
    registry = TemplateRegistry()
    structured_items = [
        {"term": "A", "definition": "a"},
        {"term": "B", "definition": "b"},
        {"term": "C", "definition": "c"},
        {"term": "D", "definition": "d"},
    ]

    minimal = _build_structured_draft(
        registry=registry,
        topic="知识清单",
        title="标题",
        structured_items=structured_items,
        suggested_template="minimal_white",
    )
    assert "highlight" not in minimal["pages"][0]
    assert all(page["type"] != "end_page" for page in minimal["pages"])

    dark = _build_structured_draft(
        registry=registry,
        topic="知识清单",
        title="标题",
        structured_items=structured_items,
        suggested_template="dark_tech",
    )
    assert dark["pages"][0].get("highlight", "") == "" or "highlight" not in dark["pages"][0]


def test_format_plan_uses_platform_profile():
    matcher = TemplateMatcher(TemplateRegistry())
    format_plan = matcher.build_format_plan(
        page_count=3,
        template_id="dark_tech",
        platform="douyin",
        format_name="9:16",
    )

    assert format_plan["platform"] == "douyin"
    assert format_plan["format"] == "9:16"
    assert format_plan["width"] == 1080
    assert format_plan["height"] == 1920


def test_brand_config_overrides_accent():
    async def run():
        planner = ContentPlanner(TemplateRegistry())
        draft, _model_used = await planner.plan(
            topic="AI 教育",
            title="AI 教育",
            content="这是正文内容",
            tags=["AI"],
            key_points=["要点"],
            structured_items=[],
            content_type="教程型",
            visual_suggestion="",
            brand={"primary": "#123456", "accent": "#654321"},
            llm=None,
        )
        return draft

    draft = asyncio.run(run())
    assert draft["custom_accent"] == "#123456"
    assert draft["brand"]["primary"] == "#123456"