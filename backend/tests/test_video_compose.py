"""Tests for video_compose adapter and skills — unit tests without real ffmpeg calls.

Covers:
1. ComposeError structure
2. _fmt_ts SRT timestamp formatting
3. _ass_ts ASS timestamp conversion
4. _char_units CJK/Latin width
5. wrap_caption line wrapping
6. _auto_srt generation
7. _srt_to_ass conversion
8. _image_filter static/ken-burns
9. VideoComposeInput validation
10. AutoShortVideoInput validation
11. _check_ffmpeg raises when missing
12. _find_video_url (re-imported from video_gen)
"""

import json
import tempfile
from pathlib import Path

import pytest

from app.adapters.video_compose import (
    ComposeError,
    _ass_ts,
    _auto_srt,
    _char_units,
    _check_ffmpeg,
    _fmt_ts,
    _image_filter,
    _srt_to_ass,
    wrap_caption,
)


# ── 1. ComposeError ─────────────────────────────────────────

class TestComposeError:
    def test_error_type_and_message(self):
        err = ComposeError("ffmpeg_failed", "ffmpeg 执行失败")
        assert err.error_type == "ffmpeg_failed"
        assert err.message == "ffmpeg 执行失败"
        assert str(err) == "ffmpeg 执行失败"

    def test_is_exception(self):
        err = ComposeError("missing_file", "not found")
        assert isinstance(err, Exception)


# ── 2. _fmt_ts ─────────────────────────────────────────────

class TestFmtTs:
    def test_zero(self):
        assert _fmt_ts(0.0) == "00:00:00,000"

    def test_simple(self):
        assert _fmt_ts(3.5) == "00:00:03,500"

    def test_minutes(self):
        assert _fmt_ts(65.123) == "00:01:05,123"

    def test_hours(self):
        assert _fmt_ts(3661.0) == "01:01:01,000"


# ── 3. _ass_ts ─────────────────────────────────────────────

class TestAssTs:
    def test_simple(self):
        assert _ass_ts("00:00:03,500") == "0:00:03.50"

    def test_hours(self):
        assert _ass_ts("01:01:01,000") == "1:01:01.00"


# ── 4. _char_units ─────────────────────────────────────────

class TestCharUnits:
    def test_cjk(self):
        assert _char_units("你") == 1.0
        assert _char_units("猫") == 1.0

    def test_latin(self):
        assert _char_units("a") == 0.5
        assert _char_units(" ") == 0.5
        assert _char_units("1") == 0.5


# ── 5. wrap_caption ────────────────────────────────────────

class TestWrapCaption:
    def test_short_text_no_wrap(self):
        result = wrap_caption("短文本", 20.0)
        assert result == ["短文本"]

    def test_long_text_wraps(self):
        text = "这是一段很长的中文文本用来测试折行功能是否正常工作"
        result = wrap_caption(text, 5.0)
        assert len(result) > 1

    def test_empty_text(self):
        result = wrap_caption("", 20.0)
        assert result == []

    def test_latin_wraps_at_space(self):
        text = "hello world this is a test"
        result = wrap_caption(text, 6.0)
        assert len(result) > 1


# ── 6. _auto_srt ───────────────────────────────────────────

class TestAutoSrt:
    def test_generates_srt(self):
        shots = [
            {"caption": "第一句话"},
            {"caption": "第二句话"},
        ]
        durations = [3.0, 4.0]
        with tempfile.TemporaryDirectory() as td:
            srt_path = Path(td) / "test.srt"
            _auto_srt(shots, durations, srt_path)
            content = srt_path.read_text(encoding="utf-8")
            assert "第一句话" in content
            assert "第二句话" in content
            assert "00:00:00,000" in content
            assert "00:00:03,000" in content

    def test_skip_empty_caption(self):
        shots = [
            {"caption": "有字"},
            {"caption": ""},
        ]
        durations = [3.0, 3.0]
        with tempfile.TemporaryDirectory() as td:
            srt_path = Path(td) / "test.srt"
            _auto_srt(shots, durations, srt_path)
            content = srt_path.read_text(encoding="utf-8")
            assert "有字" in content
            assert "2\n" not in content


# ── 7. _srt_to_ass ─────────────────────────────────────────

class TestSrtToAss:
    def test_converts_srt_to_ass(self):
        with tempfile.TemporaryDirectory() as td:
            srt_path = Path(td) / "test.srt"
            srt_path.write_text(
                "1\n00:00:00,000 --> 00:00:03,000\n测试字幕\n",
                encoding="utf-8",
            )
            ass_path = Path(td) / "test.ass"
            _srt_to_ass(srt_path, ass_path, 1080, 1920)
            content = ass_path.read_text(encoding="utf-8")
            assert "PlayResX: 1080" in content
            assert "PlayResY: 1920" in content
            assert "测试字幕" in content
            assert "Dialogue:" in content

    def test_font_size_from_resolution(self):
        with tempfile.TemporaryDirectory() as td:
            srt_path = Path(td) / "test.srt"
            srt_path.write_text(
                "1\n00:00:00,000 --> 00:00:01,000\nx\n",
                encoding="utf-8",
            )
            ass_path = Path(td) / "test.ass"
            _srt_to_ass(srt_path, ass_path, 1080, 1920)
            content = ass_path.read_text(encoding="utf-8")
            assert "54," in content


# ── 8. _image_filter ───────────────────────────────────────

class TestImageFilter:
    def test_static(self):
        vf = _image_filter("static", 1080, 1920, 90)
        assert "scale=1080:1920" in vf
        assert "pad=1080:1920" in vf
        assert "fps=30" in vf

    def test_ken_burns(self):
        vf = _image_filter("ken-burns", 1080, 1920, 90)
        assert "zoompan" in vf
        assert "s=1080x1920" in vf

    def test_bad_motion(self):
        with pytest.raises(ComposeError) as exc_info:
            _image_filter("bad", 1080, 1920, 90)
        assert exc_info.value.error_type == "bad_motion"


# ── 9. VideoComposeInput ───────────────────────────────────

class TestVideoComposeInput:
    def test_valid_input(self):
        from app.skills.produce.video_compose import VideoComposeInput
        inp = VideoComposeInput(
            storyboard={"shots": [{"image": "test.png", "duration": 3}]},
        )
        assert inp.pad_mode == "auto"
        assert inp.output_filename == "final.mp4"

    def test_custom_pad_mode(self):
        from app.skills.produce.video_compose import VideoComposeInput
        inp = VideoComposeInput(
            storyboard={"shots": []},
            pad_mode="trim",
        )
        assert inp.pad_mode == "trim"


# ── 10. AutoShortVideoInput ────────────────────────────────

class TestAutoShortVideoInput:
    def test_valid_input(self):
        from app.skills.produce.auto_short_video import AutoShortVideoInput
        inp = AutoShortVideoInput(topic="为什么 Rust 正在替代 C++")
        assert inp.target_duration == 30.0
        assert inp.ratio == "9:16"
        assert inp.need_narration is True
        assert inp.image_motion == "ken-burns"

    def test_custom_params(self):
        from app.skills.produce.auto_short_video import AutoShortVideoInput
        inp = AutoShortVideoInput(
            topic="测试主题",
            target_duration=60.0,
            ratio="16:9",
            style="科普",
            need_narration=False,
            need_bgm=True,
            image_motion="static",
        )
        assert inp.ratio == "16:9"
        assert inp.need_narration is False
        assert inp.need_bgm is True

    def test_topic_too_short(self):
        from app.skills.produce.auto_short_video import AutoShortVideoInput
        with pytest.raises(Exception):
            AutoShortVideoInput(topic="x")

    def test_duration_range(self):
        from app.skills.produce.auto_short_video import AutoShortVideoInput
        with pytest.raises(Exception):
            AutoShortVideoInput(topic="valid", target_duration=1.0)
        with pytest.raises(Exception):
            AutoShortVideoInput(topic="valid", target_duration=500.0)


# ── 11. _check_ffmpeg ──────────────────────────────────────

class TestCheckFfmpeg:
    def test_raises_when_missing(self):
        import shutil
        original = shutil.which
        shutil.which = lambda x: None
        try:
            with pytest.raises(ComposeError) as exc_info:
                _check_ffmpeg()
            assert exc_info.value.error_type == "missing_ffmpeg"
        finally:
            shutil.which = original