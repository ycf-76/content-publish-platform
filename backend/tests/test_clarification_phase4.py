"""Phase 4 测试：LLM 自主澄清 — ClarificationTagDetector + _parse_clarification_tag"""

import pytest
from app.engine.harness.executor.loop import ClarificationTagDetector, LoopExecutor


class TestClarificationTagDetectorBasic:
    def test_no_tag_passthrough(self):
        det = ClarificationTagDetector()
        content, tag = det.feed("Hello world, this is normal text.")
        assert content == "Hello world, this is normal text."
        assert tag == ""

    def test_complete_tag_in_one_chunk(self):
        det = ClarificationTagDetector()
        content, tag = det.feed(
            'Some text <needs_clarification>question: 布局方式？\noptions: 左右|上下</needs_clarification> more text'
        )
        assert "Some text" in content
        assert "more text" in content
        assert "布局方式" in tag
        assert "左右" in tag

    def test_tag_at_start(self):
        det = ClarificationTagDetector()
        content, tag = det.feed(
            '<needs_clarification>question: 风格？</needs_clarification>After tag'
        )
        assert content == "After tag"
        assert "风格" in tag

    def test_tag_at_end(self):
        det = ClarificationTagDetector()
        content, tag = det.feed(
            'Before tag<needs_clarification>question: 受众？</needs_clarification>'
        )
        assert content == "Before tag"
        assert "受众" in tag

    def test_empty_tag(self):
        det = ClarificationTagDetector()
        content, tag = det.feed(
            'Text<needs_clarification></needs_clarification>More'
        )
        assert content == "TextMore"
        assert tag == ""


class TestClarificationTagDetectorStreaming:
    def test_tag_split_across_chunks(self):
        det = ClarificationTagDetector()
        c1, t1 = det.feed("Some text <needs_cla")
        assert c1 == "Some text "
        assert t1 == ""

        c2, t2 = det.feed("rification>question: 风格？</needs_cla")
        assert "风格" in t2
        assert c2 == ""

        c3, t3 = det.feed("rification> end")
        assert t3 == ""
        assert c3 == " end"

    def test_open_tag_split_char_by_char(self):
        det = ClarificationTagDetector()
        tag_str = "<needs_clarification>"
        content_before = "Hello "
        full = content_before + tag_str + "Q?</needs_clarification> World"

        all_content = ""
        all_tag = ""
        for i in range(len(full)):
            c, t = det.feed(full[i])
            all_content += c
            all_tag += t

        fc, ft = det.flush()
        all_content += fc
        all_tag += ft

        assert "Hello" in all_content
        assert "World" in all_content
        assert "Q?" in all_tag

    def test_close_tag_split_across_chunks(self):
        det = ClarificationTagDetector()
        c1, t1 = det.feed("<needs_clarification>Q?</needs_clari")
        assert "Q?" in t1

        c2, t2 = det.feed("fication>Rest")
        assert t2 == ""
        assert c2 == "Rest"


class TestClarificationTagDetectorThinkingCoexistence:
    def test_inside_thinking_suppresses_detection(self):
        det = ClarificationTagDetector()
        content, tag = det.feed(
            '<needs_clarification>question: 不应触发</needs_clarification>',
            is_inside_thinking=True,
        )
        assert tag == ""
        assert "不应触发" in content

    def test_outside_thinking_detects_normally(self):
        det = ClarificationTagDetector()
        content, tag = det.feed(
            '<needs_clarification>question: 应触发</needs_clarification>',
            is_inside_thinking=False,
        )
        assert "应触发" in tag
        assert content == ""


class TestClarificationTagDetectorFlush:
    def test_flush_empty(self):
        det = ClarificationTagDetector()
        c, t = det.flush()
        assert c == "" and t == ""

    def test_flush_partial_open_tag(self):
        det = ClarificationTagDetector()
        det.feed("Text <needs_cla")
        c, t = det.flush()
        assert "<needs_cla" in c
        assert t == ""

    def test_flush_unclosed_tag(self):
        det = ClarificationTagDetector()
        c, t = det.feed("<needs_clarification>question: 未关闭")
        assert "未关闭" in t
        assert c == ""
        fc, ft = det.flush()
        assert fc == "" and ft == ""

    def test_inside_property(self):
        det = ClarificationTagDetector()
        assert not det.inside
        det.feed("<needs_clarification>content")
        assert det.inside
        det.feed("</needs_clarification>")
        assert not det.inside


class TestParseClarificationTag:
    def test_key_value_format(self):
        result = LoopExecutor._parse_clarification_tag(
            "question: 第4张对比图的布局方式？\noptions: 左右对比 | 上下对比 | 表格对比"
        )
        assert result is not None
        assert result["question"] == "第4张对比图的布局方式？"
        assert result["options"] == ["左右对比", "上下对比", "表格对比"]

    def test_json_format(self):
        result = LoopExecutor._parse_clarification_tag(
            '{"question": "风格偏好？", "options": ["口语化", "专业"]}'
        )
        assert result is not None
        assert result["question"] == "风格偏好？"
        assert result["options"] == ["口语化", "专业"]

    def test_plain_text_fallback(self):
        result = LoopExecutor._parse_clarification_tag("我需要知道目标受众")
        assert result is not None
        assert result["question"] == "我需要知道目标受众"

    def test_empty_returns_none(self):
        result = LoopExecutor._parse_clarification_tag("")
        assert result is None

    def test_whitespace_only_returns_none(self):
        result = LoopExecutor._parse_clarification_tag("   \n  ")
        assert result is None

    def test_question_only_no_options(self):
        result = LoopExecutor._parse_clarification_tag("question: 受众是谁？")
        assert result is not None
        assert result["question"] == "受众是谁？"
        assert "options" not in result

    def test_json_without_question_key(self):
        result = LoopExecutor._parse_clarification_tag('{"info": "some data"}')
        assert result is not None
        assert "question" in result

    def test_options_with_pipe_separator(self):
        result = LoopExecutor._parse_clarification_tag(
            "question: 选哪个？\noptions: A | B | C"
        )
        assert result["options"] == ["A", "B", "C"]