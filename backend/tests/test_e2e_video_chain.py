"""End-to-end call chain verification: Agent → Skill → Pipeline → Provider.

No real API calls. Verifies the wiring is correct.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture(autouse=True)
def _bypass_asset_guard():
    """2026-10-14：execute 入口新增 asset_id 守卫（app.services.asset_ref.guard_asset_ids，
    防 LLM 幻觉 img_1 这类假 ID）。本文件的 skill execute 测试用占位 asset_id +
    mock 内部函数，统一放行守卫；守卫自身校验由 tests/test_asset_ref.py 覆盖。"""
    with patch(
        "app.services.asset_ref.guard_asset_ids",
        new=AsyncMock(return_value={"ok": True, "ids": []}),
    ):
        yield


class TestSkillRegistration:
    """Verify multi_image_video Skill is registered and discoverable."""

    def test_skill_registered_in_builtin_modules(self):
        from app.core.skill_registry import BUILTIN_SKILL_MODULES
        assert "app.skills.produce.multi_image_video" in BUILTIN_SKILL_MODULES

    def test_skill_class_discoverable_by_name(self):
        from app.core.skill_registry import get_skill_class_by_name
        cls = get_skill_class_by_name("multi_image_video")
        assert cls is not None
        assert cls.name == "multi_image_video"
        assert cls.node_type == "produce"

    def test_skill_has_input_schema(self):
        from app.core.skill_registry import get_skill_class_by_name
        cls = get_skill_class_by_name("multi_image_video")
        assert cls.input_schema is not None
        schema = cls.input_schema.model_json_schema()
        assert "image_asset_ids" in schema["properties"]
        assert "prompt" in schema["properties"]
        assert "preview_only" in schema["properties"]
        assert "refine_shots" in schema["properties"]

    def test_skill_trigger_words(self):
        from app.core.skill_registry import get_skill_class_by_name
        cls = get_skill_class_by_name("multi_image_video")
        assert len(cls.trigger_words) > 0
        assert "多图生视频" in cls.trigger_words

    def test_skill_instantiation(self):
        from app.core.skill_registry import get_skill_class_by_name
        cls = get_skill_class_by_name("multi_image_video")
        instance = cls()
        assert instance.name == "multi_image_video"
        assert hasattr(instance, "execute")


class TestAgentSkillWiring:
    """Verify chat_agent can load multi_image_video skill."""

    def test_chat_agent_skills_none_loads_all(self):
        from app.agents.registry import BUILTIN_AGENTS
        chat_def = BUILTIN_AGENTS.get("chat_agent")
        assert chat_def is not None
        assert chat_def.skills is None

    def test_multi_image_video_in_all_registered_skills(self):
        from app.core.skill_registry import ensure_builtin_skills_registered, SkillRegistry
        ensure_builtin_skills_registered()
        registry = SkillRegistry.instance()
        all_names = [cls.name for cls in registry.all_skill_classes()]
        assert "multi_image_video" in all_names

    def test_skill_builds_into_harness(self):
        from app.agents.registry import AgentRegistry
        registry = AgentRegistry()
        try:
            harness = registry.build_harness("chat_agent")
            skill_names = [s.name for s in harness.skills]
            assert "multi_image_video" in skill_names, (
                f"multi_image_video not in harness skills. "
                f"Available: {skill_names[:20]}..."
            )
        except Exception as e:
            if "not_configured" in str(e).lower() or "api_key" in str(e).lower():
                pytest.skip(f"API key not configured: {e}")
            raise

    def test_skill_appears_in_openai_tools_schema(self):
        from app.agents.registry import AgentRegistry
        from app.engine.harness.executor.loop import LoopExecutor
        registry = AgentRegistry()
        try:
            harness = registry.build_harness("chat_agent")
        except Exception as e:
            if "not_configured" in str(e).lower() or "api_key" in str(e).lower():
                pytest.skip(f"API key not configured: {e}")
            raise

        executor = LoopExecutor()
        tools_schema = executor._build_tools_schema(harness)
        tool_names = [t["function"]["name"] for t in tools_schema]
        assert "multi_image_video" in tool_names, (
            f"multi_image_video not in tools schema. "
            f"Available: {tool_names[:20]}..."
        )

        multi_tool = next(t for t in tools_schema if t["function"]["name"] == "multi_image_video")
        params = multi_tool["function"]["parameters"]
        assert "image_asset_ids" in params["properties"]
        assert "prompt" in params["properties"]
        assert "preview_only" in params["properties"]
        assert "refine_shots" in params["properties"]


class TestPipelineProviderWiring:
    """Verify VideoPipeline → Provider chain works."""

    def test_resolve_provider_dashscope(self):
        from app.adapters.video_pipeline import resolve_provider, DashScopeProvider
        with patch("app.skills.produce.video_gen._resolve_adapter", return_value=(MagicMock(), "dashscope")):
            p = resolve_provider("dashscope")
            assert isinstance(p, DashScopeProvider)
            assert p.name == "dashscope"

    def test_resolve_provider_ark(self):
        from app.adapters.video_pipeline import resolve_provider, ArkProvider
        with patch("app.skills.produce.video_gen._resolve_adapter", return_value=(MagicMock(), "ark")):
            p = resolve_provider("ark")
            assert isinstance(p, ArkProvider)
            assert p.name == "ark"

    def test_pipeline_config_defaults(self):
        from app.adapters.video_pipeline import PipelineConfig
        config = PipelineConfig()
        assert config.native_audio is True
        assert config.first_last_frame is True
        assert config.ratio == "9:16"
        assert config.bgm_url is None
        assert config.subtitle_srt is None

    def test_capability_report_format(self):
        from app.adapters.video_pipeline import provider_capability_report, ArkProvider
        with patch("app.adapters.video_pipeline.resolve_provider", return_value=ArkProvider(MagicMock())):
            report = provider_capability_report("ark")
        assert "provider" in report
        assert "capabilities" in report
        assert "features" in report
        assert report["provider"] == "ark"
        assert report["features"]["首尾帧连贯"] is True
        assert report["features"]["原生音频"] is True


class TestSkillExecuteToPipeline:
    """Verify Skill.execute() can reach Pipeline internals."""

    @pytest.mark.asyncio
    async def test_skill_preview_only_calls_plan(self):
        from app.core.skill_registry import get_skill_class_by_name
        cls = get_skill_class_by_name("multi_image_video")
        skill = cls()

        with patch("app.skills.produce.multi_image_video._resolve_image_urls", return_value=["http://img1.jpg"]):
            with patch("app.skills.produce.multi_image_video._vl_understand_images", return_value=None):
                with patch("app.skills.produce.multi_image_video._generate_storyboard", return_value={
                    "title": "链路验证",
                    "total_shots": 1,
                    "shots": [{"shot_index": 1, "caption": "镜1", "image_prompt": "s1", "motion_prompt": "推进", "reference_images": [1], "duration": 5.0, "transition": "cut"}],
                }):
                    result = await skill.execute({
                        "image_asset_ids": ["a1"],
                        "prompt": "链路验证测试视频",
                        "preview_only": True,
                        "_context": MagicMock(user_id="user1"),
                        "_workflow_id": None,
                    })

        assert result["mode"] == "preview"
        assert result["total_shots"] == 1

    @pytest.mark.asyncio
    async def test_skill_refine_shots_skips_vl_llm(self):
        from app.core.skill_registry import get_skill_class_by_name
        cls = get_skill_class_by_name("multi_image_video")
        skill = cls()

        import sys
        mock_asset_lib = MagicMock()
        mock_asset_lib.save_video_asset = AsyncMock(return_value={"original_url": "/uploads/r.mp4", "asset_id": "vid1", "id": "vid1"})

        with patch.dict(sys.modules, {"app.services.asset_library": mock_asset_lib, "app.services.sse_bus": MagicMock(sse_bus=MagicMock(publish=AsyncMock()))}):
            with patch("app.skills.produce.multi_image_video._resolve_image_urls", return_value=["http://img1.jpg"]):
                with patch("app.skills.produce.multi_image_video._generate_shot_frames", return_value=[
                    {"shot_index": 1, "frame_url": "http://f.png", "frame_source": "ai", "duration": 5.0},
                ]):
                    with patch("app.skills.produce.multi_image_video._generate_shot_clips", return_value=[
                        {"shot_index": 1, "frame_url": "http://f.png", "duration": 5.0, "clip_mode": "video", "clip_url": "http://c.mp4"},
                    ]):
                        with patch("app.skills.produce.multi_image_video._compose_final", return_value=(b"\x00\x00\x00\x20ftypisom", [])):
                            result = await skill.execute({
                                "image_asset_ids": ["a1"],
                                "prompt": "微调链路验证视频",
                                "refine_shots": [
                                    {"shot_index": 1, "image_prompt": "edited", "motion_prompt": "俯拍", "reference_images": [1], "duration": 5.0, "transition": "cut"},
                                ],
                                "_context": MagicMock(user_id="user1"),
                                "_workflow_id": None,
                            })

        assert result["success"] is True
        assert result["mode"] == "refine"


class TestVideoPipelineModuleImport:
    """Verify video_pipeline module can be imported without errors."""

    def test_import_video_pipeline(self):
        from app.adapters.video_pipeline import (
            VideoCapability,
            VideoProvider,
            DashScopeProvider,
            KlingProvider,
            ArkProvider,
            create_provider,
            resolve_provider,
            PipelineConfig,
            PipelineResult,
            Shot,
            VideoPipeline,
            provider_capability_report,
        )
        assert VideoCapability.FIRST_LAST_FRAME is not None
        assert VideoCapability.NATIVE_AUDIO is not None

    def test_shot_dataclass_roundtrip(self):
        from app.adapters.video_pipeline import Shot
        s = Shot(shot_index=1, caption="测试", image_prompt="ip", motion_prompt="mp", duration=5.0)
        d = s.to_dict()
        s2 = Shot.from_dict(d)
        assert s2.shot_index == 1
        assert s2.caption == "测试"

    def test_pipeline_result_properties(self):
        from app.adapters.video_pipeline import PipelineResult, Shot
        r = PipelineResult(
            success=True,
            shots=[
                Shot(clip_mode="video", duration=5.0),
                Shot(clip_mode="ken_burns", duration=3.0),
            ],
        )
        assert r.video_clips == 1
        assert r.ken_burns_clips == 1
        assert r.estimated_duration == 8.0