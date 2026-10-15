"""Tests for multi_image_video Skill — unit tests without real API calls.

Covers:
1. MultiImageVideoInput validation
2. _vl_understand_images — VL 降级（无 API key → None）
3. _generate_storyboard — LLM 降级（无 LLM → 默认分镜）
4. _generate_shot_frames — 无 API key → 用参考图作关键帧
5. _generate_shot_clips — adapter 不可用 → ken_burns 降级
6. _compose_final — 无视频片段 → ken-burns 降级
7. MultiImageVideoSkill 注册和元数据
8. SSE 进度事件格式
9. compose_video_concat / compose_video_concat_simple 边界
10. 全链路降级：VL→LLM→text2image→image2video→compose 每步可缺
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.skills.produce.multi_image_video import (
    MultiImageVideoInput,
    MultiImageVideoSkill,
    _VL_SCENE_PROMPT,
    _STORYBOARD_PROMPT,
    _generate_shot_frames,
    _generate_shot_clips,
    _generate_storyboard,
    _vl_understand_images,
    _compose_final,
)


@pytest.fixture(autouse=True)
def _bypass_asset_guard():
    """2026-10-14：execute 入口新增 asset_id 守卫（app.services.asset_ref.guard_asset_ids，
    防 LLM 幻觉 img_1 这类假 ID）。本文件的流水线测试用占位 asset_id + mock 内部函数，
    统一放行守卫；守卫自身的格式/归属校验由 tests/test_asset_ref.py 覆盖。"""
    with patch(
        "app.services.asset_ref.guard_asset_ids",
        new=AsyncMock(return_value={"ok": True, "ids": []}),
    ):
        yield


# ── 1. MultiImageVideoInput validation ──────────────────────

class TestMultiImageVideoInput:
    def test_minimal_valid(self):
        inp = MultiImageVideoInput(
            image_asset_ids=["asset_001"],
            prompt="从全景推到特写",
        )
        assert len(inp.image_asset_ids) == 1
        assert inp.prompt == "从全景推到特写"
        assert inp.target_duration == 15.0
        assert inp.ratio == "9:16"
        assert inp.style == "电影感"
        assert inp.shot_duration == 5.0
        assert inp.provider is None

    def test_max_images(self):
        inp = MultiImageVideoInput(
            image_asset_ids=[f"asset_{i}" for i in range(10)],
            prompt="多场景视频",
        )
        assert len(inp.image_asset_ids) == 10

    def test_too_many_images(self):
        with pytest.raises(Exception):
            MultiImageVideoInput(
                image_asset_ids=[f"asset_{i}" for i in range(11)],
                prompt="too many",
            )

    def test_no_images(self):
        with pytest.raises(Exception):
            MultiImageVideoInput(
                image_asset_ids=[],
                prompt="no images",
            )

    def test_prompt_too_short(self):
        with pytest.raises(Exception):
            MultiImageVideoInput(
                image_asset_ids=["a"],
                prompt="hi",
            )

    def test_prompt_too_long(self):
        with pytest.raises(Exception):
            MultiImageVideoInput(
                image_asset_ids=["a"],
                prompt="x" * 2001,
            )

    def test_custom_params(self):
        inp = MultiImageVideoInput(
            image_asset_ids=["a1", "a2", "a3"],
            prompt="三场景切换",
            target_duration=30.0,
            ratio="16:9",
            style="纪实",
            shot_duration=6.0,
            provider="kling",
        )
        assert inp.target_duration == 30.0
        assert inp.ratio == "16:9"
        assert inp.style == "纪实"
        assert inp.shot_duration == 6.0
        assert inp.provider == "kling"

    def test_duration_bounds(self):
        with pytest.raises(Exception):
            MultiImageVideoInput(image_asset_ids=["a"], prompt="test", target_duration=4.0)
        with pytest.raises(Exception):
            MultiImageVideoInput(image_asset_ids=["a"], prompt="test", target_duration=61.0)

    def test_shot_duration_bounds(self):
        with pytest.raises(Exception):
            MultiImageVideoInput(image_asset_ids=["a"], prompt="test", shot_duration=1.0)
        with pytest.raises(Exception):
            MultiImageVideoInput(image_asset_ids=["a"], prompt="test", shot_duration=11.0)


# ── 2. _vl_understand_images — 降级测试 ────────────────────

def _mock_tier_router():
    router = MagicMock()
    router.resolve.return_value = "qwen-vl-max"
    return router


def _mock_settings(**overrides):
    """构造含 DB 属性的 mock settings，避免 import chain 崩溃。

    _vl_understand_images 内部 from app.services.asset_library import url_to_base64
    会触发 app.db.session 模块级 create_async_engine()，需要有效的 database_url。
    """
    s = MagicMock()
    s.dashscope_api_key = overrides.get("dashscope_api_key", "test-key")
    s.qwen_vl_model = overrides.get("qwen_vl_model", "qwen-vl-max")
    s.database_url = "sqlite+aiosqlite://"
    s.db_echo = False
    s.db_pool_size = 5
    s.db_max_overflow = 10
    return s


class TestVLUnderstandImages:
    @pytest.mark.asyncio
    async def test_no_api_key_returns_none(self):
        with patch("app.config.get_settings") as mock_settings:
            settings = _mock_settings(dashscope_api_key="")
            mock_settings.return_value = settings
            result = await _vl_understand_images(["http://example.com/img1.jpg"])
            assert result is None

    @pytest.mark.asyncio
    async def test_vl_adapter_failure_returns_none(self):
        with patch("app.config.get_settings") as mock_settings:
            settings = _mock_settings()
            mock_settings.return_value = settings

            with patch("app.adapters.video_pipeline.get_tier_router", return_value=_mock_tier_router()):
                with patch("app.adapters.qwen_vl.QwenVLAdapter") as MockVL:
                    MockVL.side_effect = Exception("VL unavailable")
                    result = await _vl_understand_images(["http://example.com/img1.jpg"])
                    assert result is None

    @pytest.mark.asyncio
    async def test_vl_returns_valid_json(self):
        with patch("app.config.get_settings") as mock_settings:
            settings = _mock_settings()
            mock_settings.return_value = settings

            mock_adapter = AsyncMock()
            mock_adapter.chat.return_value = {
                "content": json.dumps({
                    "scenes": [{"image_index": 1, "location": "咖啡馆"}],
                    "cross_scene": {"shared_subjects": [], "visual_style": "暖色调", "color_system": "棕色系"},
                }),
            }

            with patch("app.adapters.video_pipeline.get_tier_router", return_value=_mock_tier_router()):
                with patch("app.adapters.qwen_vl.QwenVLAdapter", return_value=mock_adapter):
                    result = await _vl_understand_images(["http://example.com/img1.jpg"])
                    assert result is not None
                    assert "scenes" in result
                    assert len(result["scenes"]) == 1
                    assert result["scenes"][0]["location"] == "咖啡馆"

    @pytest.mark.asyncio
    async def test_vl_returns_non_json_returns_none(self):
        with patch("app.config.get_settings") as mock_settings:
            settings = _mock_settings()
            mock_settings.return_value = settings

            mock_adapter = AsyncMock()
            mock_adapter.chat.return_value = {"content": "这是普通文本，不是JSON"}

            with patch("app.adapters.video_pipeline.get_tier_router", return_value=_mock_tier_router()):
                with patch("app.adapters.qwen_vl.QwenVLAdapter", return_value=mock_adapter):
                    result = await _vl_understand_images(["http://example.com/img1.jpg"])
                    assert result is None


# ── 3. _generate_storyboard — LLM 降级测试 ─────────────────

class TestGenerateStoryboard:
    @pytest.mark.asyncio
    async def test_llm_failure_returns_default_storyboard(self):
        with patch("app.engine.factory.get_deepseek_llm", return_value=None):
            result = await _generate_storyboard(
                scene_description=None,
                user_prompt="从全景推到特写",
                target_duration=15.0,
                shot_duration=5.0,
                style="电影感",
                num_reference_images=3,
            )
            assert "shots" in result
            assert len(result["shots"]) == 3
            assert result["shots"][0]["shot_index"] == 1

    @pytest.mark.asyncio
    async def test_llm_returns_valid_json(self):
        storyboard_json = json.dumps({
            "title": "咖啡馆的一天",
            "total_shots": 3,
            "shots": [
                {"shot_index": 1, "caption": "清晨咖啡馆", "image_prompt": "A cozy cafe in morning light", "motion_prompt": "缓慢推进", "reference_images": [1], "duration": 5.0, "transition": "cut"},
                {"shot_index": 2, "caption": "咖啡特写", "image_prompt": "Close-up of latte art", "motion_prompt": "从左摇到右", "reference_images": [2], "duration": 5.0, "transition": "dissolve"},
                {"shot_index": 3, "caption": "窗外街景", "image_prompt": "Street view through window", "motion_prompt": "俯拍拉远", "reference_images": [3], "duration": 5.0, "transition": "cut"},
            ],
        })

        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = storyboard_json
        mock_llm.ainvoke.return_value = mock_response

        with patch("app.engine.factory.get_deepseek_llm", return_value=mock_llm):
            result = await _generate_storyboard(
                scene_description={"scenes": [{"image_index": 1, "location": "咖啡馆"}]},
                user_prompt="从全景推到特写",
                target_duration=15.0,
                shot_duration=5.0,
                style="电影感",
                num_reference_images=3,
            )
            assert result["title"] == "咖啡馆的一天"
            assert len(result["shots"]) == 3
            assert result["shots"][0]["image_prompt"] == "A cozy cafe in morning light"

    @pytest.mark.asyncio
    async def test_llm_returns_bad_json_fallback(self):
        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = "这不是JSON"
        mock_llm.ainvoke.return_value = mock_response

        with patch("app.engine.factory.get_deepseek_llm", return_value=mock_llm):
            result = await _generate_storyboard(
                scene_description=None,
                user_prompt="测试降级",
                target_duration=10.0,
                shot_duration=5.0,
                style="纪实",
                num_reference_images=2,
            )
            assert "shots" in result
            assert len(result["shots"]) >= 1

    @pytest.mark.asyncio
    async def test_default_storyboard_reference_images_capped(self):
        with patch("app.engine.factory.get_deepseek_llm", return_value=None):
            result = await _generate_storyboard(
                scene_description=None,
                user_prompt="测试",
                target_duration=20.0,
                shot_duration=5.0,
                style="电影感",
                num_reference_images=2,
            )
            for shot in result["shots"]:
                for ref in shot.get("reference_images", []):
                    assert ref <= 2


# ── 4. _generate_shot_frames — 无 API key 降级 ─────────────

class TestGenerateShotFrames:
    @pytest.mark.asyncio
    async def test_no_api_key_uses_reference_images(self):
        shots = [
            {"shot_index": 1, "image_prompt": "test prompt 1"},
            {"shot_index": 2, "image_prompt": "test prompt 2"},
        ]
        image_urls = ["http://example.com/ref1.jpg", "http://example.com/ref2.jpg"]

        with patch("app.config.get_settings") as mock_settings:
            settings = MagicMock()
            settings.dashscope_api_key = ""
            mock_settings.return_value = settings

            result = await _generate_shot_frames(shots, "9:16", "user1", image_urls)
            assert result[0]["frame_url"] == "http://example.com/ref1.jpg"
            assert result[0]["frame_source"] == "reference"
            assert result[1]["frame_url"] == "http://example.com/ref2.jpg"
            assert result[1]["frame_source"] == "reference"

    @pytest.mark.asyncio
    async def test_adapter_failure_uses_reference_fallback(self):
        shots = [{"shot_index": 1, "image_prompt": "test"}]
        image_urls = ["http://example.com/ref1.jpg"]

        with patch("app.config.get_settings") as mock_settings:
            settings = MagicMock()
            settings.dashscope_api_key = "test-key"
            settings.wanx_model = "wanx2.1-t2i-turbo"
            settings.multi_image_video_max_concurrent_frames = 3
            mock_settings.return_value = settings

            with patch("app.adapters.image_gen.WanxAdapter") as MockWanx:
                MockWanx.side_effect = Exception("Wanx unavailable")
                result = await _generate_shot_frames(shots, "9:16", "user1", image_urls)
                assert result[0]["frame_source"] == "reference_fallback"


# ── 5. _generate_shot_clips — adapter 不可用降级 ────────────

class TestGenerateShotClips:
    @pytest.mark.asyncio
    async def test_adapter_not_available_ken_burns_fallback(self):
        from app.adapters.video_gen import VideoGenError

        shots = [
            {"shot_index": 1, "frame_url": "http://example.com/frame1.jpg", "motion_prompt": "推进"},
        ]

        with patch("app.skills.produce.video_gen._resolve_adapter") as mock_resolve:
            mock_resolve.side_effect = VideoGenError("not_configured", "未配置 API Key")
            result = await _generate_shot_clips(
                shots=shots,
                ratio="9:16",
                shot_duration=5.0,
                user_id="user1",
            )
            assert result[0]["clip_mode"] == "ken_burns"
            assert "clip_error" in result[0]

    @pytest.mark.asyncio
    async def test_no_frame_url_ken_burns(self):
        shots = [{"shot_index": 1, "motion_prompt": "推进"}]

        with patch("app.skills.produce.video_gen._resolve_adapter") as mock_resolve:
            mock_adapter = AsyncMock()
            mock_resolve.return_value = (mock_adapter, "dashscope")

            with patch("app.config.get_settings") as mock_settings:
                settings = MagicMock()
                settings.dashscope_i2v_model = "wan2.1-i2v-turbo"
                mock_settings.return_value = settings

                import sys
                mock_asset_lib = MagicMock()
                mock_asset_lib.save_video_asset = AsyncMock()
                with patch.dict(sys.modules, {"app.services.asset_library": mock_asset_lib}):
                    result = await _generate_shot_clips(
                        shots=shots,
                        ratio="9:16",
                        shot_duration=5.0,
                        user_id="user1",
                    )
                    assert result[0]["clip_mode"] == "ken_burns"


# ── 6. _compose_final — 降级测试 ───────────────────────────

class TestComposeFinal:
    @pytest.mark.asyncio
    async def test_all_ken_burns_tries_compose_video(self):
        shots = [
            {"shot_index": 1, "clip_mode": "ken_burns", "frame_url": "http://example.com/frame1.jpg", "caption": "测试", "duration": 5.0},
        ]

        with patch("app.adapters.video_compose.compose_video") as mock_compose:
            from pathlib import Path
            mock_compose.return_value = Path("/tmp/test_output.mp4")

            with patch.object(Path, "read_bytes", return_value=b"fake_mp4_data"):
                result_bytes, degradation = await _compose_final(
                    shots=shots,
                    ratio="9:16",
                    user_id="user1",
                    title="测试视频",
                )
                assert "无视频片段" in " ".join(degradation)


# ── 7. Skill 注册和元数据 ──────────────────────────────────

class TestMultiImageVideoSkillMeta:
    def test_skill_metadata(self):
        assert MultiImageVideoSkill.name == "multi_image_video"
        assert MultiImageVideoSkill.display_name == "多图参考视频生成"
        assert MultiImageVideoSkill.node_type == "produce"
        assert MultiImageVideoSkill.skill_category == "create"
        assert MultiImageVideoSkill.skill_priority == "hot"

    def test_trigger_words(self):
        words = MultiImageVideoSkill.trigger_words
        assert "多图生视频" in words
        assert "用这些图做视频" in words
        assert "根据图片生成视频" in words

    def test_input_schema(self):
        assert MultiImageVideoSkill.input_schema is MultiImageVideoInput

    def test_description_mentions_pipeline(self):
        desc = MultiImageVideoSkill.description
        assert "VL" in desc or "看图" in desc
        assert "分镜" in desc
        assert "降级" in desc

    def test_registered_in_registry(self):
        from app.core.skill_registry import ensure_builtin_skills_registered, get_skill_class_by_name
        ensure_builtin_skills_registered()
        cls = get_skill_class_by_name("multi_image_video")
        assert cls is MultiImageVideoSkill


# ── 8. Prompt 常量 ─────────────────────────────────────────

class TestPromptConstants:
    def test_vl_prompt_requests_json(self):
        assert "JSON" in _VL_SCENE_PROMPT or "json" in _VL_SCENE_PROMPT.lower()

    def test_vl_prompt_has_scenes_structure(self):
        assert "scenes" in _VL_SCENE_PROMPT
        assert "cross_scene" in _VL_SCENE_PROMPT

    def test_storyboard_prompt_has_shots(self):
        assert "shots" in _STORYBOARD_PROMPT
        assert "image_prompt" in _STORYBOARD_PROMPT
        assert "motion_prompt" in _STORYBOARD_PROMPT

    def test_storyboard_prompt_references_scene(self):
        assert "{scene_description}" in _STORYBOARD_PROMPT
        assert "{user_prompt}" in _STORYBOARD_PROMPT


# ── 9. compose_video_concat 边界 ───────────────────────────

class TestComposeVideoConcat:
    def test_empty_clips_raises(self):
        from app.adapters.video_compose import ComposeError, compose_video_concat
        with pytest.raises(ComposeError) as exc_info:
            import asyncio
            # 2026-10-13：get_event_loop().run_until_complete() 在 Python 3.12
            # 主线程无事件循环时直接 RuntimeError，根本跑不到被测函数。
            asyncio.run(compose_video_concat([]))
        assert exc_info.value.error_type == "empty_clips"

    def test_simple_concat_empty_clips_raises(self):
        from app.adapters.video_compose import ComposeError, compose_video_concat_simple
        with pytest.raises(ComposeError) as exc_info:
            import asyncio
            asyncio.run(compose_video_concat_simple([]))
        assert exc_info.value.error_type == "empty_clips"


# ── 10. 全链路降级 ─────────────────────────────────────────

class TestFullPipelineDegradation:
    @pytest.mark.asyncio
    async def test_vl_none_still_produces_storyboard(self):
        with patch("app.engine.factory.get_deepseek_llm", return_value=None):
            result = await _generate_storyboard(
                scene_description=None,
                user_prompt="测试全链路降级",
                target_duration=10.0,
                shot_duration=5.0,
                style="纪实",
                num_reference_images=2,
            )
            assert "shots" in result
            assert len(result["shots"]) >= 1

    @pytest.mark.asyncio
    async def test_every_step_degradable(self):
        shots = [
            {"shot_index": 1, "caption": "测试", "image_prompt": "test prompt", "motion_prompt": "推进", "reference_images": [1], "duration": 5.0, "transition": "cut"},
        ]
        image_urls = ["http://example.com/ref1.jpg"]

        with patch("app.config.get_settings") as mock_settings:
            settings = MagicMock()
            settings.dashscope_api_key = ""
            mock_settings.return_value = settings

            result_frames = await _generate_shot_frames(shots, "9:16", "user1", image_urls)
            assert "frame_url" in result_frames[0]
            assert result_frames[0]["frame_source"] == "reference"

    @pytest.mark.asyncio
    async def test_execute_with_all_degradations(self):
        skill = MultiImageVideoSkill()

        import sys
        mock_asset_lib = MagicMock()
        mock_asset_lib.save_video_asset = AsyncMock(return_value={"original_url": "/uploads/test.mp4", "asset_id": "a1", "id": "a1"})

        with patch("app.skills.produce.multi_image_video._resolve_image_urls", return_value=["http://img.jpg"]):
            with patch("app.skills.produce.multi_image_video._vl_understand_images", return_value=None):
                with patch("app.skills.produce.multi_image_video._generate_storyboard", return_value={"title": "降级测试", "shots": [{"shot_index": 1, "caption": "测试", "image_prompt": "test", "motion_prompt": "推进", "reference_images": [1], "duration": 5.0, "transition": "cut"}]}):
                    with patch("app.skills.produce.multi_image_video._generate_shot_frames", return_value=[{"shot_index": 1, "frame_url": "http://frame.jpg", "frame_source": "reference"}]):
                        with patch("app.skills.produce.multi_image_video._generate_shot_clips", return_value=[{"shot_index": 1, "clip_mode": "ken_burns", "frame_url": "http://frame.jpg", "caption": "测试", "duration": 5.0}]):
                            with patch("app.skills.produce.multi_image_video._compose_final", return_value=(b"fake_mp4_bytes", ["降级提示"])):
                                with patch.dict(sys.modules, {"app.services.asset_library": mock_asset_lib}):
                                    result = await skill.execute({
                                        "image_asset_ids": ["asset_001"],
                                        "prompt": "全降级测试",
                                        "_context": MagicMock(user_id="user1"),
                                        "_workflow_id": None,
                                    })
                                    assert result["success"] is True
                                    assert "degradation" in result
                                    assert result["shots_count"] == 1

    @pytest.mark.asyncio
    async def test_execute_compose_failure_returns_clips(self):
        skill = MultiImageVideoSkill()

        with patch("app.skills.produce.multi_image_video._resolve_image_urls", return_value=["http://img.jpg"]):
            with patch("app.skills.produce.multi_image_video._vl_understand_images", return_value=None):
                with patch("app.skills.produce.multi_image_video._generate_storyboard", return_value={"title": "拼接失败测试", "shots": [{"shot_index": 1, "caption": "测试", "image_prompt": "test", "motion_prompt": "推进", "reference_images": [1], "duration": 5.0, "transition": "cut"}]}):
                    with patch("app.skills.produce.multi_image_video._generate_shot_frames", return_value=[{"shot_index": 1, "frame_url": "http://frame.jpg", "frame_source": "reference"}]):
                        with patch("app.skills.produce.multi_image_video._generate_shot_clips", return_value=[{"shot_index": 1, "clip_mode": "video", "clip_url": "http://clip.mp4", "frame_url": "http://frame.jpg"}]):
                            with patch("app.skills.produce.multi_image_video._compose_final", return_value=(None, ["拼接失败"])):
                                result = await skill.execute({
                                    "image_asset_ids": ["asset_001"],
                                    "prompt": "拼接失败测试",
                                    "_context": MagicMock(user_id="user1"),
                                    "_workflow_id": None,
                                })
                                assert result["success"] is False
                                assert "clip_urls" in result


# ── 11. 全链路集成测试（不用真实 token，mock 外部依赖） ──────

class TestFullPipelineIntegration:
    """端到端走一遍 6 步流水线，验证：
    - 每步降级路径是否正确触发
    - SSE 事件是否按序发出
    - 最终返回结构是否完整
    - 不需要任何真实 API key / token
    """

    @pytest.mark.asyncio
    async def test_full_pipeline_all_apis_available(self):
        """场景 A：所有 API 可用，6 步全走通"""
        skill = MultiImageVideoSkill()
        sse_events: list[dict] = []

        mock_sse_bus = MagicMock()
        mock_sse_bus.publish = AsyncMock(side_effect=lambda wid, evt, payload: sse_events.append({"event": evt, "payload": payload}))

        import sys
        mock_asset_lib = MagicMock()
        mock_asset_lib.save_video_asset = AsyncMock(return_value={"original_url": "/uploads/final.mp4", "asset_id": "vid_001", "id": "vid_001"})
        mock_asset_lib.save_asset = AsyncMock(return_value={"original_url": "/uploads/frame.png", "id": "frame_001"})

        with patch.dict(sys.modules, {
            "app.services.asset_library": mock_asset_lib,
            "app.services.sse_bus": MagicMock(sse_bus=mock_sse_bus),
        }):
            with patch("app.skills.produce.multi_image_video._resolve_image_urls", return_value=[
                "http://img1.jpg", "http://img2.jpg", "http://img3.jpg"
            ]):
                with patch("app.skills.produce.multi_image_video._vl_understand_images", return_value={
                    "scenes": [
                        {"image_index": 1, "location": "咖啡厅", "subjects": ["咖啡杯"], "props": ["书"], "lighting": "暖光", "color_tone": "暖棕", "composition": "中景", "mood": "安静"},
                        {"image_index": 2, "location": "街道", "subjects": ["行人"], "props": ["伞"], "lighting": "自然光", "color_tone": "灰蓝", "composition": "全景", "mood": "匆忙"},
                        {"image_index": 3, "location": "公园", "subjects": ["狗"], "props": ["飞盘"], "lighting": "夕阳", "color_tone": "金橙", "composition": "低角度", "mood": "欢快"},
                    ],
                    "cross_scene": {"shared_subjects": [], "visual_style": "日常纪实", "color_system": "暖色系"},
                }):
                    with patch("app.skills.produce.multi_image_video._generate_storyboard", return_value={
                        "title": "日常三幕",
                        "total_shots": 3,
                        "shots": [
                            {"shot_index": 1, "caption": "咖啡厅安静午后", "image_prompt": "coffee shop afternoon, warm light", "motion_prompt": "缓慢推进", "reference_images": [1], "duration": 5.0, "transition": "dissolve"},
                            {"shot_index": 2, "caption": "街头匆匆行人", "image_prompt": "street pedestrians, natural light", "motion_prompt": "从左摇到右", "reference_images": [2], "duration": 5.0, "transition": "dissolve"},
                            {"shot_index": 3, "caption": "公园夕阳飞盘", "image_prompt": "park sunset dog frisbee, golden", "motion_prompt": "俯拍拉远", "reference_images": [3], "duration": 5.0, "transition": "cut"},
                        ],
                    }):
                        with patch("app.skills.produce.multi_image_video._generate_shot_frames", return_value=[
                            {"shot_index": 1, "caption": "咖啡厅安静午后", "image_prompt": "coffee shop afternoon", "motion_prompt": "缓慢推进", "reference_images": [1], "duration": 5.0, "transition": "dissolve", "frame_url": "http://frame1.png", "frame_source": "ai_generated"},
                            {"shot_index": 2, "caption": "街头匆匆行人", "image_prompt": "street pedestrians", "motion_prompt": "从左摇到右", "reference_images": [2], "duration": 5.0, "transition": "dissolve", "frame_url": "http://frame2.png", "frame_source": "ai_generated"},
                            {"shot_index": 3, "caption": "公园夕阳飞盘", "image_prompt": "park sunset dog", "motion_prompt": "俯拍拉远", "reference_images": [3], "duration": 5.0, "transition": "cut", "frame_url": "http://frame3.png", "frame_source": "ai_generated"},
                        ]):
                            with patch("app.skills.produce.multi_image_video._generate_shot_clips", return_value=[
                                {"shot_index": 1, "caption": "咖啡厅安静午后", "frame_url": "http://frame1.png", "duration": 5.0, "clip_mode": "video", "clip_url": "http://clip1.mp4", "clip_asset_id": "ca1"},
                                {"shot_index": 2, "caption": "街头匆匆行人", "frame_url": "http://frame2.png", "duration": 5.0, "clip_mode": "video", "clip_url": "http://clip2.mp4", "clip_asset_id": "ca2"},
                                {"shot_index": 3, "caption": "公园夕阳飞盘", "frame_url": "http://frame3.png", "duration": 5.0, "clip_mode": "video", "clip_url": "http://clip3.mp4", "clip_asset_id": "ca3"},
                            ]):
                                with patch("app.skills.produce.multi_image_video._compose_final", return_value=(
                                    b"\x00\x00\x00\x20ftypisom",
                                    [],
                                )):
                                    result = await skill.execute({
                                        "image_asset_ids": ["a1", "a2", "a3"],
                                        "prompt": "日常三幕：咖啡厅、街道、公园",
                                        "_context": MagicMock(user_id="user1"),
                                        "_workflow_id": "wf_001",
                                    })

        assert result["success"] is True
        assert result["asset_id"] == "vid_001"
        assert result["shots_count"] == 3
        assert result["video_clips"] == 3
        assert result["ken_burns_clips"] == 0
        assert result["degradation"] == []
        assert result["title"] == "日常三幕"

        progress_events = [e for e in sse_events if e["event"] == "multi_image_video_progress"]
        assert len(progress_events) == 6
        steps_seen = [e["payload"]["step"] for e in progress_events]
        assert steps_seen == [1, 2, 3, 4, 5, 6]
        labels = [e["payload"]["label"] for e in progress_events]
        assert labels == ["VL理解参考图", "编排分镜脚本", "生成分镜关键帧", "逐镜生成视频", "拼接成片", "保存交付"]

        card_events = [e for e in sse_events if e["event"] == "card_draft_ready"]
        assert len(card_events) == 1
        assert card_events[0]["payload"]["card_draft"]["template"] == "video"
        assert card_events[0]["payload"]["card_draft"]["pages"][0]["mediaType"] == "video"

    @pytest.mark.asyncio
    async def test_full_pipeline_vl_down_llm_down(self):
        """场景 B：VL 和 LLM 都不可用 → 降级到默认分镜"""
        skill = MultiImageVideoSkill()
        sse_events: list[dict] = []

        mock_sse_bus = MagicMock()
        mock_sse_bus.publish = AsyncMock(side_effect=lambda wid, evt, payload: sse_events.append({"event": evt, "payload": payload}))

        import sys
        mock_asset_lib = MagicMock()
        mock_asset_lib.save_video_asset = AsyncMock(return_value={"original_url": "/uploads/final.mp4", "asset_id": "vid_002", "id": "vid_002"})

        with patch.dict(sys.modules, {
            "app.services.asset_library": mock_asset_lib,
            "app.services.sse_bus": MagicMock(sse_bus=mock_sse_bus),
        }):
            with patch("app.skills.produce.multi_image_video._resolve_image_urls", return_value=["http://img1.jpg"]):
                with patch("app.skills.produce.multi_image_video._vl_understand_images", return_value=None):
                    with patch("app.skills.produce.multi_image_video._generate_storyboard") as mock_sb:
                        mock_sb.return_value = {
                            "title": "默认分镜",
                            "total_shots": 3,
                            "shots": [
                                {"shot_index": i + 1, "caption": f"第{i+1}镜", "image_prompt": f"scene {i+1}", "motion_prompt": "缓慢推进", "reference_images": [1], "duration": 5.0, "transition": "cut"}
                                for i in range(3)
                            ],
                        }
                        with patch("app.skills.produce.multi_image_video._generate_shot_frames", return_value=[
                            {"shot_index": 1, "caption": "第1镜", "image_prompt": "scene 1", "motion_prompt": "缓慢推进", "reference_images": [1], "duration": 5.0, "transition": "cut", "frame_url": "http://img1.jpg", "frame_source": "reference"},
                            {"shot_index": 2, "caption": "第2镜", "image_prompt": "scene 2", "motion_prompt": "缓慢推进", "reference_images": [1], "duration": 5.0, "transition": "cut", "frame_url": "http://img1.jpg", "frame_source": "reference"},
                            {"shot_index": 3, "caption": "第3镜", "image_prompt": "scene 3", "motion_prompt": "缓慢推进", "reference_images": [1], "duration": 5.0, "transition": "cut", "frame_url": "http://img1.jpg", "frame_source": "reference"},
                        ]):
                            with patch("app.skills.produce.multi_image_video._generate_shot_clips", return_value=[
                                {"shot_index": 1, "caption": "第1镜", "frame_url": "http://img1.jpg", "duration": 5.0, "clip_mode": "ken_burns", "clip_error": "image2video 不可用"},
                                {"shot_index": 2, "caption": "第2镜", "frame_url": "http://img1.jpg", "duration": 5.0, "clip_mode": "ken_burns", "clip_error": "image2video 不可用"},
                                {"shot_index": 3, "caption": "第3镜", "frame_url": "http://img1.jpg", "duration": 5.0, "clip_mode": "ken_burns", "clip_error": "image2video 不可用"},
                            ]):
                                with patch("app.skills.produce.multi_image_video._compose_final", return_value=(
                                    b"\x00\x00\x00\x20ftypisom",
                                    ["3 镜退化为 ken-burns 图片缓动", "无视频片段，尝试图片 ken-burns 合成"],
                                )):
                                    result = await skill.execute({
                                        "image_asset_ids": ["a1"],
                                        "prompt": "简单测试视频",
                                        "_context": MagicMock(user_id="user1"),
                                        "_workflow_id": "wf_002",
                                    })

        assert result["success"] is True
        assert result["shots_count"] == 3
        assert result["video_clips"] == 0
        assert result["ken_burns_clips"] == 3
        assert "VL理解：不可用" in result["degradation"][0]
        assert any("ken-burns" in d for d in result["degradation"])

        progress_events = [e for e in sse_events if e["event"] == "multi_image_video_progress"]
        assert len(progress_events) == 6

    @pytest.mark.asyncio
    async def test_full_pipeline_compose_fails_returns_clips(self):
        """场景 C：拼接失败 → 返回各片段 URL"""
        skill = MultiImageVideoSkill()

        import sys
        mock_asset_lib = MagicMock()
        mock_asset_lib.save_video_asset = AsyncMock(return_value={"original_url": "/uploads/clip.mp4", "asset_id": "vid_003", "id": "vid_003"})

        with patch.dict(sys.modules, {
            "app.services.asset_library": mock_asset_lib,
            "app.services.sse_bus": MagicMock(sse_bus=MagicMock(publish=AsyncMock())),
        }):
            with patch("app.skills.produce.multi_image_video._resolve_image_urls", return_value=["http://img1.jpg"]):
                with patch("app.skills.produce.multi_image_video._vl_understand_images", return_value=None):
                    with patch("app.skills.produce.multi_image_video._generate_storyboard", return_value={
                        "title": "拼接失败",
                        "total_shots": 2,
                        "shots": [
                            {"shot_index": 1, "caption": "镜1", "image_prompt": "s1", "motion_prompt": "推进", "reference_images": [1], "duration": 5.0, "transition": "cut"},
                            {"shot_index": 2, "caption": "镜2", "image_prompt": "s2", "motion_prompt": "拉远", "reference_images": [1], "duration": 5.0, "transition": "cut"},
                        ],
                    }):
                        with patch("app.skills.produce.multi_image_video._generate_shot_frames", return_value=[
                            {"shot_index": 1, "caption": "镜1", "frame_url": "http://f1.png", "frame_source": "reference", "duration": 5.0},
                            {"shot_index": 2, "caption": "镜2", "frame_url": "http://f2.png", "frame_source": "reference", "duration": 5.0},
                        ]):
                            with patch("app.skills.produce.multi_image_video._generate_shot_clips", return_value=[
                                {"shot_index": 1, "caption": "镜1", "frame_url": "http://f1.png", "duration": 5.0, "clip_mode": "video", "clip_url": "http://clip1.mp4"},
                                {"shot_index": 2, "caption": "镜2", "frame_url": "http://f2.png", "duration": 5.0, "clip_mode": "video", "clip_url": "http://clip2.mp4"},
                            ]):
                                with patch("app.skills.produce.multi_image_video._compose_final", return_value=(None, ["xfade 拼接失败", "简单拼接也失败"])):
                                    result = await skill.execute({
                                        "image_asset_ids": ["a1"],
                                        "prompt": "拼接失败测试",
                                        "_context": MagicMock(user_id="user1"),
                                        "_workflow_id": None,
                                    })

        assert result["success"] is False
        assert result["error"] == "成片拼接失败"
        assert "clip_urls" in result
        assert len(result["clip_urls"]) == 2
        assert result["shots_count"] == 2

    @pytest.mark.asyncio
    async def test_full_pipeline_no_workflow_id_no_sse(self):
        """场景 D：无 workflow_id → 不发 SSE 事件，但流程正常走完"""
        skill = MultiImageVideoSkill()

        import sys
        mock_asset_lib = MagicMock()
        mock_asset_lib.save_video_asset = AsyncMock(return_value={"original_url": "/uploads/final.mp4", "asset_id": "vid_004", "id": "vid_004"})

        with patch.dict(sys.modules, {
            "app.services.asset_library": mock_asset_lib,
        }):
            with patch("app.skills.produce.multi_image_video._resolve_image_urls", return_value=["http://img.jpg"]):
                with patch("app.skills.produce.multi_image_video._vl_understand_images", return_value=None):
                    with patch("app.skills.produce.multi_image_video._generate_storyboard", return_value={
                        "title": "无SSE",
                        "total_shots": 1,
                        "shots": [{"shot_index": 1, "caption": "测试", "image_prompt": "test", "motion_prompt": "推进", "reference_images": [1], "duration": 5.0, "transition": "cut"}],
                    }):
                        with patch("app.skills.produce.multi_image_video._generate_shot_frames", return_value=[
                            {"shot_index": 1, "caption": "测试", "frame_url": "http://frame.png", "frame_source": "reference", "duration": 5.0},
                        ]):
                            with patch("app.skills.produce.multi_image_video._generate_shot_clips", return_value=[
                                {"shot_index": 1, "caption": "测试", "frame_url": "http://frame.png", "duration": 5.0, "clip_mode": "video", "clip_url": "http://clip.mp4"},
                            ]):
                                with patch("app.skills.produce.multi_image_video._compose_final", return_value=(
                                    b"\x00\x00\x00\x20ftypisom",
                                    [],
                                )):
                                    result = await skill.execute({
                                        "image_asset_ids": ["a1"],
                                        "prompt": "无SSE测试",
                                        "_context": MagicMock(user_id="user1"),
                                        "_workflow_id": None,
                                    })

        assert result["success"] is True
        assert result["shots_count"] == 1
        assert result["video_clips"] == 1

    @pytest.mark.asyncio
    async def test_full_pipeline_sse_step_percent_increases(self):
        """场景 E：SSE 进度百分比严格递增"""
        skill = MultiImageVideoSkill()
        sse_events: list[dict] = []

        mock_sse_bus = MagicMock()
        mock_sse_bus.publish = AsyncMock(side_effect=lambda wid, evt, payload: sse_events.append({"event": evt, "payload": payload}))

        import sys
        mock_asset_lib = MagicMock()
        mock_asset_lib.save_video_asset = AsyncMock(return_value={"original_url": "/uploads/final.mp4", "asset_id": "vid_005", "id": "vid_005"})

        with patch.dict(sys.modules, {
            "app.services.asset_library": mock_asset_lib,
            "app.services.sse_bus": MagicMock(sse_bus=mock_sse_bus),
        }):
            with patch("app.skills.produce.multi_image_video._resolve_image_urls", return_value=["http://img.jpg"]):
                with patch("app.skills.produce.multi_image_video._vl_understand_images", return_value=None):
                    with patch("app.skills.produce.multi_image_video._generate_storyboard", return_value={
                        "title": "进度测试",
                        "total_shots": 1,
                        "shots": [{"shot_index": 1, "caption": "测试", "image_prompt": "test", "motion_prompt": "推进", "reference_images": [1], "duration": 5.0, "transition": "cut"}],
                    }):
                        with patch("app.skills.produce.multi_image_video._generate_shot_frames", return_value=[
                            {"shot_index": 1, "caption": "测试", "frame_url": "http://frame.png", "frame_source": "reference", "duration": 5.0},
                        ]):
                            with patch("app.skills.produce.multi_image_video._generate_shot_clips", return_value=[
                                {"shot_index": 1, "caption": "测试", "frame_url": "http://frame.png", "duration": 5.0, "clip_mode": "video", "clip_url": "http://clip.mp4"},
                            ]):
                                with patch("app.skills.produce.multi_image_video._compose_final", return_value=(
                                    b"\x00\x00\x00\x20ftypisom",
                                    [],
                                )):
                                    result = await skill.execute({
                                        "image_asset_ids": ["a1"],
                                        "prompt": "进度测试视频",
                                        "_context": MagicMock(user_id="user1"),
                                        "_workflow_id": "wf_005",
                                    })

        progress_events = [e for e in sse_events if e["event"] == "multi_image_video_progress"]
        percents = [e["payload"]["percent"] for e in progress_events]
        for i in range(1, len(percents)):
            assert percents[i] > percents[i - 1], f"Step {i+1} percent {percents[i]} should > step {i} percent {percents[i-1]}"
        assert percents[-1] == 100


# ── 12. Seedance 首尾帧连贯策略测试 ──────────────────────

class TestSeedanceFirstLastFrame:
    """验证 Seedance (provider=ark) 的首尾帧连贯策略：
    - provider=ark 时，shot[i] (i>0) 的 last_frame_url = shot[i-1].frame_url
    - provider!=ark 时，last_frame_url 始终为 None
    - 成功生成的 clip 带 clip_coherence="first_last_frame" 标记
    """

    @pytest.mark.asyncio
    async def test_ark_provider_passes_last_frame(self):
        """provider=ark → 第 2 镜起传入 last_frame_url"""
        shots = [
            {"shot_index": 1, "frame_url": "http://frame1.png", "motion_prompt": "推进"},
            {"shot_index": 2, "frame_url": "http://frame2.png", "motion_prompt": "拉远"},
            {"shot_index": 3, "frame_url": "http://frame3.png", "motion_prompt": "摇镜"},
        ]

        call_log: list[dict] = []

        mock_adapter = AsyncMock()
        mock_adapter.image2video = AsyncMock(side_effect=lambda **kwargs: (
            call_log.append(kwargs),
            b"\x00\x00\x00\x20ftypisom",
        )[1])

        import sys
        mock_asset_lib = MagicMock()
        mock_asset_lib.save_video_asset = AsyncMock(return_value={"original_url": "/uploads/clip.mp4", "asset_id": "a1", "id": "a1"})

        with patch("app.skills.produce.video_gen._resolve_adapter", return_value=(mock_adapter, "ark")):
            with patch.dict(sys.modules, {"app.services.asset_library": mock_asset_lib}):
                with patch("app.config.get_settings") as mock_settings:
                    settings = MagicMock()
                    settings.dashscope_i2v_model = "doubao-seedance-1-0-lite-i2v-250428"
                    mock_settings.return_value = settings

                    result = await _generate_shot_clips(
                        shots=shots,
                        ratio="9:16",
                        shot_duration=5.0,
                        user_id="user1",
                        provider="ark",
                    )

        assert len(call_log) == 3
        assert call_log[0].get("last_frame_url") is None
        assert call_log[1].get("last_frame_url") == "http://frame1.png"
        assert call_log[2].get("last_frame_url") == "http://frame2.png"

        assert result[0].get("clip_coherence") is None
        assert result[1]["clip_coherence"] == "first_last_frame"
        assert result[2]["clip_coherence"] == "first_last_frame"

    @pytest.mark.asyncio
    async def test_dashscope_provider_no_last_frame(self):
        """provider=dashscope → 不传 last_frame_url"""
        shots = [
            {"shot_index": 1, "frame_url": "http://frame1.png", "motion_prompt": "推进"},
            {"shot_index": 2, "frame_url": "http://frame2.png", "motion_prompt": "拉远"},
        ]

        call_log: list[dict] = []

        mock_adapter = AsyncMock()
        mock_adapter.image2video = AsyncMock(side_effect=lambda **kwargs: (
            call_log.append(kwargs),
            b"\x00\x00\x00\x20ftypisom",
        )[1])

        import sys
        mock_asset_lib = MagicMock()
        mock_asset_lib.save_video_asset = AsyncMock(return_value={"original_url": "/uploads/clip.mp4", "asset_id": "a1", "id": "a1"})

        with patch("app.skills.produce.video_gen._resolve_adapter", return_value=(mock_adapter, "dashscope")):
            with patch.dict(sys.modules, {"app.services.asset_library": mock_asset_lib}):
                with patch("app.config.get_settings") as mock_settings:
                    settings = MagicMock()
                    settings.dashscope_i2v_model = "wan2.1-i2v-turbo"
                    mock_settings.return_value = settings

                    result = await _generate_shot_clips(
                        shots=shots,
                        ratio="9:16",
                        shot_duration=5.0,
                        user_id="user1",
                        provider="dashscope",
                    )

        assert len(call_log) == 2
        assert call_log[0].get("last_frame_url") is None
        assert call_log[1].get("last_frame_url") is None

        assert result[0].get("clip_coherence") is None
        assert result[1].get("clip_coherence") is None

    @pytest.mark.asyncio
    async def test_ark_first_shot_no_last_frame(self):
        """第 1 镜永远不传 last_frame_url（没有前镜）"""
        shots = [{"shot_index": 1, "frame_url": "http://frame1.png", "motion_prompt": "推进"}]

        call_log: list[dict] = []

        mock_adapter = AsyncMock()
        mock_adapter.image2video = AsyncMock(side_effect=lambda **kwargs: (
            call_log.append(kwargs),
            b"\x00\x00\x00\x20ftypisom",
        )[1])

        import sys
        mock_asset_lib = MagicMock()
        mock_asset_lib.save_video_asset = AsyncMock(return_value={"original_url": "/uploads/clip.mp4", "asset_id": "a1", "id": "a1"})

        with patch("app.skills.produce.video_gen._resolve_adapter", return_value=(mock_adapter, "ark")):
            with patch.dict(sys.modules, {"app.services.asset_library": mock_asset_lib}):
                with patch("app.config.get_settings") as mock_settings:
                    settings = MagicMock()
                    settings.dashscope_i2v_model = "doubao-seedance-1-0-lite-i2v-250428"
                    mock_settings.return_value = settings

                    result = await _generate_shot_clips(
                        shots=shots,
                        ratio="9:16",
                        shot_duration=5.0,
                        user_id="user1",
                        provider="ark",
                    )

        assert len(call_log) == 1
        assert call_log[0].get("last_frame_url") is None
        assert result[0].get("clip_coherence") is None

    @pytest.mark.asyncio
    async def test_ark_prev_shot_no_frame_skips_last_frame(self):
        """前镜无 frame_url → 当前镜不传 last_frame_url"""
        shots = [
            {"shot_index": 1, "motion_prompt": "推进"},
            {"shot_index": 2, "frame_url": "http://frame2.png", "motion_prompt": "拉远"},
        ]

        call_log: list[dict] = []

        mock_adapter = AsyncMock()
        mock_adapter.image2video = AsyncMock(side_effect=lambda **kwargs: (
            call_log.append(kwargs),
            b"\x00\x00\x00\x20ftypisom",
        )[1])

        import sys
        mock_asset_lib = MagicMock()
        mock_asset_lib.save_video_asset = AsyncMock(return_value={"original_url": "/uploads/clip.mp4", "asset_id": "a1", "id": "a1"})

        with patch("app.skills.produce.video_gen._resolve_adapter", return_value=(mock_adapter, "ark")):
            with patch.dict(sys.modules, {"app.services.asset_library": mock_asset_lib}):
                with patch("app.config.get_settings") as mock_settings:
                    settings = MagicMock()
                    settings.dashscope_i2v_model = "doubao-seedance-1-0-lite-i2v-250428"
                    mock_settings.return_value = settings

                    result = await _generate_shot_clips(
                        shots=shots,
                        ratio="9:16",
                        shot_duration=5.0,
                        user_id="user1",
                        provider="ark",
                    )

        assert result[0]["clip_mode"] == "ken_burns"
        assert result[1]["clip_mode"] == "video"
        assert call_log[0].get("last_frame_url") is None


# ── 13. 预览 + 微调模式测试 ─────────────────────────────

class TestPreviewAndRefine:
    """验证两阶段交互式微调：
    - preview_only=True → 只走 VL+LLM，返回分镜草稿，不生成视频
    - refine_shots → 跳过 VL+LLM，从 Step 3 开始生成
    """

    @pytest.mark.asyncio
    async def test_preview_only_returns_storyboard(self):
        """preview_only=True → 返回分镜草稿，不触发生成"""
        skill = MultiImageVideoSkill()
        sse_events: list[dict] = []

        mock_sse_bus = MagicMock()
        mock_sse_bus.publish = AsyncMock(side_effect=lambda wid, evt, payload: sse_events.append({"event": evt, "payload": payload}))

        import sys
        with patch.dict(sys.modules, {"app.services.sse_bus": MagicMock(sse_bus=mock_sse_bus)}):
            with patch("app.skills.produce.multi_image_video._resolve_image_urls", return_value=["http://img1.jpg", "http://img2.jpg"]):
                with patch("app.skills.produce.multi_image_video._vl_understand_images", return_value={"scenes": [], "cross_scene": {}}):
                    with patch("app.skills.produce.multi_image_video._generate_storyboard", return_value={
                        "title": "预览测试",
                        "total_shots": 2,
                        "shots": [
                            {"shot_index": 1, "caption": "镜1", "image_prompt": "scene 1", "motion_prompt": "推进", "reference_images": [1], "duration": 5.0, "transition": "cut"},
                            {"shot_index": 2, "caption": "镜2", "image_prompt": "scene 2", "motion_prompt": "拉远", "reference_images": [2], "duration": 5.0, "transition": "dissolve"},
                        ],
                    }):
                        result = await skill.execute({
                            "image_asset_ids": ["a1", "a2"],
                            "prompt": "预览测试视频",
                            "preview_only": True,
                            "_context": MagicMock(user_id="user1"),
                            "_workflow_id": "wf_preview",
                        })

        assert result["mode"] == "preview"
        assert result["title"] == "预览测试"
        assert len(result["shots"]) == 2
        assert result["total_shots"] == 2
        assert result["estimated_duration"] == 10.0
        assert "hint" in result
        assert "refine_shots" in result["hint"]

        progress_events = [e for e in sse_events if e["event"] == "multi_image_video_progress"]
        preview_events = [e for e in progress_events if e["payload"]["label"] == "分镜预览就绪"]
        assert len(preview_events) == 1

        card_events = [e for e in sse_events if e["event"] == "card_draft_ready"]
        assert len(card_events) == 1
        assert card_events[0]["payload"]["card_draft"]["template"] == "storyboard_preview"
        assert len(card_events[0]["payload"]["card_draft"]["pages"]) == 2

    @pytest.mark.asyncio
    async def test_preview_no_workflow_id_still_works(self):
        """preview_only + 无 workflow_id → 不发 SSE 但正常返回"""
        skill = MultiImageVideoSkill()

        with patch("app.skills.produce.multi_image_video._resolve_image_urls", return_value=["http://img1.jpg"]):
            with patch("app.skills.produce.multi_image_video._vl_understand_images", return_value=None):
                with patch("app.skills.produce.multi_image_video._generate_storyboard", return_value={
                    "title": "无SSE预览",
                    "total_shots": 1,
                    "shots": [{"shot_index": 1, "caption": "镜1", "image_prompt": "s1", "motion_prompt": "推进", "reference_images": [1], "duration": 5.0, "transition": "cut"}],
                }):
                    result = await skill.execute({
                        "image_asset_ids": ["a1"],
                        "prompt": "无SSE预览测试",
                        "preview_only": True,
                        "_context": MagicMock(user_id="user1"),
                        "_workflow_id": None,
                    })

        assert result["mode"] == "preview"
        assert result["total_shots"] == 1
        assert len(result["degradation"]) >= 1

    @pytest.mark.asyncio
    async def test_refine_shots_skips_vl_llm(self):
        """refine_shots → 跳过 VL+LLM，从 Step 3 开始"""
        skill = MultiImageVideoSkill()
        sse_events: list[dict] = []

        mock_sse_bus = MagicMock()
        mock_sse_bus.publish = AsyncMock(side_effect=lambda wid, evt, payload: sse_events.append({"event": evt, "payload": payload}))

        import sys
        mock_asset_lib = MagicMock()
        mock_asset_lib.save_video_asset = AsyncMock(return_value={"original_url": "/uploads/refine.mp4", "asset_id": "vid_refine", "id": "vid_refine"})

        with patch.dict(sys.modules, {
            "app.services.asset_library": mock_asset_lib,
            "app.services.sse_bus": MagicMock(sse_bus=mock_sse_bus),
        }):
            with patch("app.skills.produce.multi_image_video._resolve_image_urls", return_value=["http://img1.jpg"]):
                with patch("app.skills.produce.multi_image_video._generate_shot_frames", return_value=[
                    {"shot_index": 1, "caption": "编辑后镜1", "frame_url": "http://frame1.png", "frame_source": "ai_generated", "duration": 5.0},
                ]):
                    with patch("app.skills.produce.multi_image_video._generate_shot_clips", return_value=[
                        {"shot_index": 1, "caption": "编辑后镜1", "frame_url": "http://frame1.png", "duration": 5.0, "clip_mode": "video", "clip_url": "http://clip1.mp4"},
                    ]):
                        with patch("app.skills.produce.multi_image_video._compose_final", return_value=(
                            b"\x00\x00\x00\x20ftypisom",
                            [],
                        )):
                            result = await skill.execute({
                                "image_asset_ids": ["a1"],
                                "prompt": "微调测试视频",
                                "refine_shots": [
                                    {"shot_index": 1, "caption": "编辑后镜1", "image_prompt": "edited scene", "motion_prompt": "俯拍", "reference_images": [1], "duration": 5.0, "transition": "cut"},
                                ],
                                "_context": MagicMock(user_id="user1"),
                                "_workflow_id": "wf_refine",
                            })

        assert result["success"] is True
        assert result["mode"] == "refine"
        assert result["shots_count"] == 1
        assert result["video_clips"] == 1
        assert any("微调模式" in d for d in result["degradation"])

        progress_events = [e for e in sse_events if e["event"] == "multi_image_video_progress"]
        steps = [e["payload"]["step"] for e in progress_events]
        assert 3 in steps
        assert 4 in steps
        assert 5 in steps
        assert 6 in steps
        assert 1 not in steps
        assert 2 not in steps

    @pytest.mark.asyncio
    async def test_refine_empty_shots_returns_error(self):
        """refine_shots=[] → 返回错误"""
        skill = MultiImageVideoSkill()

        result = await skill.execute({
            "image_asset_ids": ["a1"],
            "prompt": "空微调测试视频",
            "refine_shots": [],
            "_context": MagicMock(user_id="user1"),
        })

        assert "error" in result

    @pytest.mark.asyncio
    async def test_refine_with_different_image_assets(self):
        """refine_image_asset_ids → 使用新参考图"""
        skill = MultiImageVideoSkill()

        import sys
        mock_asset_lib = MagicMock()
        mock_asset_lib.save_video_asset = AsyncMock(return_value={"original_url": "/uploads/refine2.mp4", "asset_id": "vid_r2", "id": "vid_r2"})

        resolve_calls: list[list[str]] = []

        async def _mock_resolve(asset_ids, user_id):
            resolve_calls.append(list(asset_ids))
            return [f"http://img_{aid}.jpg" for aid in asset_ids]

        with patch.dict(sys.modules, {"app.services.asset_library": mock_asset_lib, "app.services.sse_bus": MagicMock(sse_bus=MagicMock(publish=AsyncMock()))}):
            with patch("app.skills.produce.multi_image_video._resolve_image_urls", side_effect=_mock_resolve):
                with patch("app.skills.produce.multi_image_video._generate_shot_frames", return_value=[
                    {"shot_index": 1, "frame_url": "http://frame.png", "frame_source": "reference", "duration": 5.0},
                ]):
                    with patch("app.skills.produce.multi_image_video._generate_shot_clips", return_value=[
                        {"shot_index": 1, "frame_url": "http://frame.png", "duration": 5.0, "clip_mode": "video", "clip_url": "http://clip.mp4"},
                    ]):
                        with patch("app.skills.produce.multi_image_video._compose_final", return_value=(
                            b"\x00\x00\x00\x20ftypisom",
                            [],
                        )):
                            result = await skill.execute({
                                "image_asset_ids": ["a1"],
                                "prompt": "换图微调测试视频",
                                "refine_shots": [
                                    {"shot_index": 1, "image_prompt": "new scene", "motion_prompt": "推进", "reference_images": [1], "duration": 5.0, "transition": "cut"},
                                ],
                                "refine_image_asset_ids": ["b1", "b2"],
                                "_context": MagicMock(user_id="user1"),
                                "_workflow_id": None,
                            })

        assert result["success"] is True
        assert result["mode"] == "refine"
        assert resolve_calls[-1] == ["b1", "b2"]