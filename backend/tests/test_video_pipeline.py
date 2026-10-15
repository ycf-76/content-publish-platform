"""Tests for video_pipeline framework — no real API calls."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.adapters.video_pipeline import (
    VideoCapability,
    DashScopeProvider,
    KlingProvider,
    ArkProvider,
    create_provider,
    PipelineConfig,
    PipelineResult,
    Shot,
    VideoPipeline,
    provider_capability_report,
)


# ── 1. Provider 能力协议 ─────────────────────────────────

class TestProviderCapabilities:

    def test_dashscope_capabilities(self):
        p = DashScopeProvider(MagicMock())
        assert p.name == "dashscope"
        assert p.supports(VideoCapability.TEXT_TO_VIDEO)
        assert p.supports(VideoCapability.IMAGE_TO_VIDEO)
        assert not p.supports(VideoCapability.FIRST_LAST_FRAME)
        assert not p.supports(VideoCapability.NATIVE_AUDIO)
        assert not p.supports(VideoCapability.DIALOGUE)

    def test_kling_capabilities(self):
        p = KlingProvider(MagicMock())
        assert p.name == "kling"
        assert p.supports(VideoCapability.TEXT_TO_VIDEO)
        assert p.supports(VideoCapability.IMAGE_TO_VIDEO)
        assert not p.supports(VideoCapability.FIRST_LAST_FRAME)
        assert not p.supports(VideoCapability.NATIVE_AUDIO)

    def test_ark_capabilities(self):
        p = ArkProvider(MagicMock())
        assert p.name == "ark"
        assert p.supports(VideoCapability.TEXT_TO_VIDEO)
        assert p.supports(VideoCapability.IMAGE_TO_VIDEO)
        assert p.supports(VideoCapability.FIRST_LAST_FRAME)
        assert p.supports(VideoCapability.NATIVE_AUDIO)
        assert p.supports(VideoCapability.DIALOGUE)
        assert p.supports(VideoCapability.MULTI_IMAGE_INPUT)

    def test_create_provider_unknown_raises(self):
        with pytest.raises(ValueError, match="未知 provider"):
            create_provider("unknown", MagicMock())


# ── 2. Shot 数据类 ───────────────────────────────────────

class TestShot:

    def test_from_dict_roundtrip(self):
        d = {
            "shot_index": 1,
            "caption": "咖啡厅",
            "image_prompt": "coffee shop",
            "motion_prompt": "缓慢推进",
            "reference_images": [1, 2],
            "duration": 5.0,
            "transition": "dissolve",
            "frame_url": "http://frame.png",
            "frame_source": "ai_generated",
        }
        shot = Shot.from_dict(d)
        assert shot.shot_index == 1
        assert shot.caption == "咖啡厅"
        assert shot.reference_images == [1, 2]

        out = shot.to_dict()
        assert out["shot_index"] == 1
        assert out["caption"] == "咖啡厅"

    def test_from_dict_ignores_extra_keys(self):
        d = {"shot_index": 1, "extra_field": "ignored"}
        shot = Shot.from_dict(d)
        assert shot.shot_index == 1
        assert not hasattr(shot, "extra_field")


# ── 3. PipelineResult ────────────────────────────────────

class TestPipelineResult:

    def test_video_clips_count(self):
        result = PipelineResult(
            success=True,
            shots=[
                Shot(clip_mode="video"),
                Shot(clip_mode="ken_burns"),
                Shot(clip_mode="video"),
            ],
        )
        assert result.video_clips == 2
        assert result.ken_burns_clips == 1

    def test_estimated_duration(self):
        result = PipelineResult(
            success=True,
            shots=[Shot(duration=5.0), Shot(duration=3.0), Shot(duration=7.0)],
        )
        assert result.estimated_duration == 15.0

    def test_to_dict_preview_mode(self):
        result = PipelineResult(
            success=True,
            mode="preview",
            title="测试",
            shots=[Shot(shot_index=1, caption="镜1")],
            scene_description={"scenes": []},
            image_urls=["http://img.jpg"],
        )
        d = result.to_dict()
        assert d["mode"] == "preview"
        assert "hint" in d
        assert len(d["shots"]) == 1
        assert d["scene_description"] == {"scenes": []}

    def test_to_dict_full_mode_no_shots_in_output(self):
        result = PipelineResult(
            success=True,
            mode="full",
            title="测试",
            asset_id="a1",
            asset_url="/uploads/v.mp4",
        )
        d = result.to_dict()
        assert "shots" not in d
        assert d["asset_id"] == "a1"


# ── 4. VideoPipeline 能力感知 ─────────────────────────────

class TestPipelineCapabilityAwareness:

    def test_should_use_first_last_frame_ark(self):
        with patch("app.adapters.video_pipeline.resolve_provider", return_value=ArkProvider(MagicMock())):
            pipeline = VideoPipeline(PipelineConfig(first_last_frame=True, provider_name="ark"))
            assert pipeline._should_use_first_last_frame() is True

    def test_should_use_first_last_frame_dashscope(self):
        with patch("app.adapters.video_pipeline.resolve_provider", return_value=DashScopeProvider(MagicMock())):
            pipeline = VideoPipeline(PipelineConfig(first_last_frame=True, provider_name="dashscope"))
            assert pipeline._should_use_first_last_frame() is False

    def test_should_use_native_audio_ark(self):
        with patch("app.adapters.video_pipeline.resolve_provider", return_value=ArkProvider(MagicMock())):
            pipeline = VideoPipeline(PipelineConfig(native_audio=True, provider_name="ark"))
            assert pipeline._should_use_native_audio() is True

    def test_should_use_native_audio_kling(self):
        with patch("app.adapters.video_pipeline.resolve_provider", return_value=KlingProvider(MagicMock())):
            pipeline = VideoPipeline(PipelineConfig(native_audio=True, provider_name="kling"))
            assert pipeline._should_use_native_audio() is False

    def test_config_disabled_overrides_capability(self):
        with patch("app.adapters.video_pipeline.resolve_provider", return_value=ArkProvider(MagicMock())):
            pipeline = VideoPipeline(PipelineConfig(native_audio=False, first_last_frame=False, provider_name="ark"))
            assert pipeline._should_use_native_audio() is False
            assert pipeline._should_use_first_last_frame() is False


# ── 5. Provider 能力报告 ─────────────────────────────────

class TestCapabilityReport:

    def test_ark_report(self):
        with patch("app.adapters.video_pipeline.resolve_provider", return_value=ArkProvider(MagicMock())):
            report = provider_capability_report("ark")
        assert report["provider"] == "ark"
        assert report["features"]["首尾帧连贯"] is True
        assert report["features"]["原生音频"] is True
        assert report["features"]["对白生成"] is True

    def test_dashscope_report(self):
        with patch("app.adapters.video_pipeline.resolve_provider", return_value=DashScopeProvider(MagicMock())):
            report = provider_capability_report("dashscope")
        assert report["provider"] == "dashscope"
        assert report["features"]["首尾帧连贯"] is False
        assert report["features"]["原生音频"] is False


# ── 6. ArkProvider 桥接测试 ──────────────────────────────

class TestArkProviderBridge:

    @pytest.mark.asyncio
    async def test_image2video_passes_last_frame_when_supported(self):
        mock_adapter = MagicMock()
        mock_adapter.image2video = AsyncMock(return_value=b"\x00\x00\x00\x20ftypisom")

        provider = ArkProvider(mock_adapter)
        await provider.image2video(
            image="http://frame.png",
            prompt="推进",
            last_frame_url="http://prev.png",
            native_audio=True,
        )

        call_kwargs = mock_adapter.image2video.call_args[1]
        assert call_kwargs["last_frame_url"] == "http://prev.png"
        assert call_kwargs["generate_audio"] is True

    @pytest.mark.asyncio
    async def test_text2video_passes_generate_audio(self):
        mock_adapter = MagicMock()
        mock_adapter.text2video = AsyncMock(return_value=b"\x00\x00\x00\x20ftypisom")

        provider = ArkProvider(mock_adapter)
        await provider.text2video(prompt="测试", native_audio=True)

        call_kwargs = mock_adapter.text2video.call_args[1]
        assert call_kwargs["generate_audio"] is True


class TestDashScopeProviderBridge:

    @pytest.mark.asyncio
    async def test_image2video_ignores_last_frame(self):
        mock_adapter = MagicMock()
        mock_adapter.image2video = AsyncMock(return_value=b"\x00\x00\x00\x20ftypisom")

        provider = DashScopeProvider(mock_adapter)
        await provider.image2video(
            image="http://frame.png",
            prompt="推进",
            last_frame_url="http://prev.png",
            native_audio=True,
        )

        call_kwargs = mock_adapter.image2video.call_args[1]
        assert "last_frame_url" not in call_kwargs or call_kwargs.get("last_frame_url") is None
        assert "generate_audio" not in call_kwargs


# ── 7. Pipeline plan 集成 ────────────────────────────────

class TestPipelinePlan:

    @pytest.mark.asyncio
    async def test_plan_returns_preview(self):
        with patch("app.skills.produce.multi_image_video._resolve_image_urls", return_value=["http://img1.jpg"]):
            with patch("app.skills.produce.multi_image_video._vl_understand_images", return_value=None):
                with patch("app.skills.produce.multi_image_video._generate_storyboard", return_value={
                    "title": "流水线预览",
                    "total_shots": 2,
                    "shots": [
                        {"shot_index": 1, "caption": "镜1", "image_prompt": "s1", "motion_prompt": "推进", "reference_images": [1], "duration": 5.0, "transition": "cut"},
                        {"shot_index": 2, "caption": "镜2", "image_prompt": "s2", "motion_prompt": "拉远", "reference_images": [1], "duration": 5.0, "transition": "dissolve"},
                    ],
                }):
                    with patch("app.adapters.video_pipeline.resolve_provider", return_value=ArkProvider(MagicMock())):
                        pipeline = VideoPipeline(PipelineConfig(provider_name="ark"))
                        result = await pipeline.plan(
                            image_asset_ids=["a1"],
                            user_id="user1",
                            prompt="流水线预览测试",
                        )

        assert result.success is True
        assert result.mode == "preview"
        assert len(result.shots) == 2
        assert result.title == "流水线预览"
        assert result.estimated_duration == 10.0
        assert len(result.degradation) >= 1

    @pytest.mark.asyncio
    async def test_plan_empty_storyboard_returns_error(self):
        with patch("app.skills.produce.multi_image_video._resolve_image_urls", return_value=["http://img1.jpg"]):
            with patch("app.skills.produce.multi_image_video._vl_understand_images", return_value=None):
                with patch("app.skills.produce.multi_image_video._generate_storyboard", return_value={
                    "title": "空",
                    "total_shots": 0,
                    "shots": [],
                }):
                    with patch("app.adapters.video_pipeline.resolve_provider", return_value=DashScopeProvider(MagicMock())):
                        pipeline = VideoPipeline(PipelineConfig(provider_name="dashscope"))
                        result = await pipeline.plan(
                            image_asset_ids=["a1"],
                            user_id="user1",
                            prompt="空分镜测试视频",
                        )

        assert result.success is False
        assert "空" in result.error