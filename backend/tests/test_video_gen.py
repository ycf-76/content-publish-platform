"""Tests for video_gen adapters — unit tests without real API calls.

Covers:
1. VideoGenAdapter ABC contract
2. DashScopeVideoAdapter payload construction (text2video / image2video)
3. KlingVideoAdapter JWT generation
4. ArkVideoAdapter payload construction
5. create_video_adapter factory
6. _find_video_url extraction
7. _poll timeout and bad status
8. VideoGenError structure
9. GenerateVideoSkill input validation
10. asset_library save_video_asset
"""

import json
import time

import pytest

from app.adapters.video_gen import (
    ArkVideoAdapter,
    DashScopeVideoAdapter,
    KlingVideoAdapter,
    VideoGenAdapter,
    VideoGenError,
    _find_video_url,
    _poll,
    create_video_adapter,
)


# ── 1. ABC contract ──────────────────────────────────────────

class TestVideoGenAdapterABC:
    def test_cannot_instantiate_abc(self):
        with pytest.raises(TypeError):
            VideoGenAdapter()

    def test_subclass_must_implement_text2video(self):
        class Incomplete(VideoGenAdapter):
            async def image2video(self, image, prompt="", *, ratio="9:16", duration=5.0, model=None):
                return b""
        with pytest.raises(TypeError):
            Incomplete()

    def test_subclass_must_implement_image2video(self):
        class Incomplete(VideoGenAdapter):
            async def text2video(self, prompt, *, ratio="9:16", duration=5.0, model=None):
                return b""
        with pytest.raises(TypeError):
            Incomplete()


# ── 2. DashScopeVideoAdapter ────────────────────────────────

class TestDashScopeVideoAdapter:
    def test_init_defaults(self):
        adapter = DashScopeVideoAdapter(api_key="test-key")
        assert adapter.api_key == "test-key"
        assert adapter.model == "wan2.1-t2v-turbo"
        assert "dashscope" in adapter.base_url

    def test_capabilities(self):
        adapter = DashScopeVideoAdapter(api_key="test-key")
        assert adapter.capabilities["native_audio"] is False
        assert adapter.capabilities["dialogue"] is False

    @pytest.mark.asyncio
    async def test_check_configured(self):
        adapter = DashScopeVideoAdapter(api_key="test-key")
        assert await adapter.check() == {"configured": True}

    @pytest.mark.asyncio
    async def test_check_not_configured(self):
        adapter = DashScopeVideoAdapter(api_key="")
        assert await adapter.check() == {"configured": False}

    def test_last_error_type_initial(self):
        adapter = DashScopeVideoAdapter(api_key="test-key")
        assert adapter.last_error_type is None
        assert adapter.last_error_message == ""


# ── 3. KlingVideoAdapter JWT ────────────────────────────────

class TestKlingJWT:
    def test_jwt_structure(self):
        """JWT 应该是 header.payload.signature 三段式。"""
        token = KlingVideoAdapter._jwt("test_ak", "test_sk")
        parts = token.split(".")
        assert len(parts) == 3

    def test_jwt_header_is_hs256(self):
        """JWT header 应该声明 alg=HS256, typ=JWT。"""
        import base64
        token = KlingVideoAdapter._jwt("test_ak", "test_sk")
        header_b64 = token.split(".")[0]
        padding = 4 - len(header_b64) % 4
        header_json = base64.urlsafe_b64decode(header_b64 + "=" * padding)
        header = json.loads(header_json)
        assert header["alg"] == "HS256"
        assert header["typ"] == "JWT"

    def test_jwt_payload_contains_iss(self):
        """JWT payload 应该包含 iss=access_key。"""
        import base64
        token = KlingVideoAdapter._jwt("my_access_key", "my_secret_key")
        payload_b64 = token.split(".")[1]
        padding = 4 - len(payload_b64) % 4
        payload_json = base64.urlsafe_b64decode(payload_b64 + "=" * padding)
        payload = json.loads(payload_json)
        assert payload["iss"] == "my_access_key"
        assert "exp" in payload
        assert "nbf" in payload

    def test_jwt_different_keys_produce_different_tokens(self):
        t1 = KlingVideoAdapter._jwt("ak1", "sk1")
        t2 = KlingVideoAdapter._jwt("ak2", "sk2")
        assert t1 != t2


class TestKlingVideoAdapter:
    def test_init_defaults(self):
        adapter = KlingVideoAdapter(access_key="ak", secret_key="sk")
        assert adapter.model == "kling-v1"
        assert "klingai" in adapter.base_url

    def test_capabilities(self):
        adapter = KlingVideoAdapter(access_key="ak", secret_key="sk")
        assert adapter.capabilities["native_audio"] is False

    @pytest.mark.asyncio
    async def test_check_configured(self):
        adapter = KlingVideoAdapter(access_key="ak", secret_key="sk")
        assert await adapter.check() == {"configured": True}

    @pytest.mark.asyncio
    async def test_check_not_configured(self):
        adapter = KlingVideoAdapter(access_key="", secret_key="sk")
        assert await adapter.check() == {"configured": False}


# ── 4. ArkVideoAdapter ──────────────────────────────────────

class TestArkVideoAdapter:
    def test_init_defaults(self):
        adapter = ArkVideoAdapter(api_key="test-key")
        assert adapter.model == ""
        assert "volces" in adapter.base_url

    def test_capabilities_native_audio(self):
        """Ark Seedance 支持 native_audio 和 dialogue。"""
        adapter = ArkVideoAdapter(api_key="test-key")
        assert adapter.capabilities["native_audio"] is True
        assert adapter.capabilities["dialogue"] is True
        assert adapter.capabilities["dialogue_faithful"] is False

    @pytest.mark.asyncio
    async def test_check_configured(self):
        adapter = ArkVideoAdapter(api_key="test-key")
        assert await adapter.check() == {"configured": True}


# ── 5. create_video_adapter factory ──────────────────────────

class TestCreateVideoAdapter:
    def test_dashscope(self):
        adapter = create_video_adapter("dashscope", api_key="key")
        assert isinstance(adapter, DashScopeVideoAdapter)

    def test_kling(self):
        adapter = create_video_adapter("kling", access_key="ak", secret_key="sk")
        assert isinstance(adapter, KlingVideoAdapter)

    def test_ark(self):
        adapter = create_video_adapter("ark", api_key="key")
        assert isinstance(adapter, ArkVideoAdapter)

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="未知的视频 provider"):
            create_video_adapter("nonexistent")

    def test_custom_model(self):
        adapter = create_video_adapter("dashscope", api_key="key", model="wan2.1-t2v-plus")
        assert adapter.model == "wan2.1-t2v-plus"


# ── 6. _find_video_url ──────────────────────────────────────

class TestFindVideoUrl:
    def test_output_video_url(self):
        data = {"output": {"video_url": "https://cdn.example.com/video.mp4"}}
        assert _find_video_url(data) == "https://cdn.example.com/video.mp4"

    def test_output_video(self):
        data = {"output": {"video": "https://cdn.example.com/v.mp4"}}
        assert _find_video_url(data) == "https://cdn.example.com/v.mp4"

    def test_data_url(self):
        data = {"data": {"video_url": "https://cdn.example.com/v.mp4"}}
        assert _find_video_url(data) == "https://cdn.example.com/v.mp4"

    def test_root_url(self):
        data = {"url": "https://cdn.example.com/v.mp4"}
        assert _find_video_url(data) == "https://cdn.example.com/v.mp4"

    def test_no_url(self):
        data = {"output": {"task_status": "SUCCEEDED"}}
        assert _find_video_url(data) is None

    def test_non_http_url_ignored(self):
        data = {"output": {"video_url": "data:base64,..."}}
        assert _find_video_url(data) is None

    def test_content_video_url_ark(self):
        data = {"content": {"video_url": "https://ark-tos.example.com/seedance.mp4"}}
        assert _find_video_url(data) == "https://ark-tos.example.com/seedance.mp4"


# ── 7. _poll ────────────────────────────────────────────────

class TestPoll:
    @pytest.mark.asyncio
    async def test_poll_timeout(self):
        """轮询超时应抛 VideoGenError("timeout")。"""
        import httpx

        async with httpx.AsyncClient() as client:
            with pytest.raises(VideoGenError) as exc_info:
                await _poll(
                    client,
                    url="https://httpbin.org/delay/10",
                    headers={},
                    poll_interval=0.1,
                    max_wait=0.3,
                )
            assert exc_info.value.error_type == "timeout"

    @pytest.mark.asyncio
    async def test_poll_bad_status(self):
        """任务 FAILED 应抛 VideoGenError("task_failed")。"""
        import httpx
        from unittest.mock import AsyncMock, patch

        mock_resp = httpx.Response(
            200,
            json={"output": {"task_status": "FAILED", "message": "content policy"}},
        )
        mock_resp._request = httpx.Request("GET", "http://test")

        async with httpx.AsyncClient() as client:
            with patch.object(client, "get", new_callable=AsyncMock, return_value=mock_resp):
                with pytest.raises(VideoGenError) as exc_info:
                    await _poll(
                        client,
                        url="http://test",
                        headers={},
                        poll_interval=0.01,
                        max_wait=5.0,
                    )
                assert "task_failed" in exc_info.value.error_type


# ── 8. VideoGenError ────────────────────────────────────────

class TestVideoGenError:
    def test_error_type_and_message(self):
        err = VideoGenError("rate_limited", "请求过于频繁")
        assert err.error_type == "rate_limited"
        assert err.message == "请求过于频繁"
        assert str(err) == "请求过于频繁"

    def test_is_exception(self):
        err = VideoGenError("api_error", "fail")
        assert isinstance(err, Exception)


# ── 9. GenerateVideoSkill input validation ──────────────────

class TestVideoGenInput:
    def test_valid_input(self):
        from app.skills.produce.video_gen import VideoGenInput
        inp = VideoGenInput(prompt="一只猫在阳光下伸懒腰")
        assert inp.mode == "text2video"
        assert inp.duration == 5.0
        assert inp.ratio == "9:16"

    def test_prompt_too_short(self):
        from app.skills.produce.video_gen import VideoGenInput
        with pytest.raises(Exception):
            VideoGenInput(prompt="太短")

    def test_prompt_too_long(self):
        from app.skills.produce.video_gen import VideoGenInput
        with pytest.raises(Exception):
            VideoGenInput(prompt="x" * 2001)

    def test_duration_range(self):
        from app.skills.produce.video_gen import VideoGenInput
        with pytest.raises(Exception):
            VideoGenInput(prompt="valid prompt", duration=0.5)
        with pytest.raises(Exception):
            VideoGenInput(prompt="valid prompt", duration=15.0)

    def test_image2video_mode(self):
        from app.skills.produce.video_gen import VideoGenInput
        inp = VideoGenInput(
            prompt="画面缓缓推进",
            mode="image2video",
            image_asset_id="01JQX123",
        )
        assert inp.mode == "image2video"
        assert inp.image_asset_id == "01JQX123"

    def test_provider_optional(self):
        from app.skills.produce.video_gen import VideoGenInput
        inp = VideoGenInput(prompt="valid prompt", provider="kling")
        assert inp.provider == "kling"
        inp2 = VideoGenInput(prompt="valid prompt")
        assert inp2.provider is None


# ── 10. asset_library save_video_asset ──────────────────────

class TestSaveVideoAsset:
    def test_ext_for_content_type(self):
        from app.services.asset_library import _ext_for_content_type
        assert _ext_for_content_type("video/mp4") == ".mp4"
        assert _ext_for_content_type("video/webm") == ".webm"
        assert _ext_for_content_type("audio/mpeg") == ".mp3"
        assert _ext_for_content_type("audio/wav") == ".wav"
        assert _ext_for_content_type("application/octet-stream") == ".bin"

    def test_allowed_content_types_includes_video(self):
        from app.services.asset_library import ALLOWED_CONTENT_TYPES
        assert "video/mp4" in ALLOWED_CONTENT_TYPES
        assert "video/webm" in ALLOWED_CONTENT_TYPES
        assert "audio/mpeg" in ALLOWED_CONTENT_TYPES
        assert "audio/wav" in ALLOWED_CONTENT_TYPES

    def test_max_upload_bytes_increased(self):
        from app.services.asset_library import MAX_UPLOAD_BYTES
        assert MAX_UPLOAD_BYTES == 50 * 1024 * 1024