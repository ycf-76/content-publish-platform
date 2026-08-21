import asyncio

from app.agents.intent_parser import ActionType, RuleBasedIntentParser


def _parse(message: str):
    return asyncio.run(RuleBasedIntentParser().parse(message))


def test_parse_full_pipeline_with_topic():
    intent = _parse("帮我写一篇关于 AI 教育的小红书文章")
    assert intent.action == ActionType.FULL_PIPELINE
    assert intent.params.get("topic") == "AI 教育"
    assert intent.confidence > 0.7


def test_parse_full_pipeline_short_phrase():
    intent = _parse("写一篇美食探店笔记")
    assert intent.action == ActionType.FULL_PIPELINE
    assert intent.params.get("topic") == "美食探店"


def test_parse_chat_when_no_workflow_intent():
    intent = _parse("今天天气怎么样")
    assert intent.action == ActionType.CHAT


def test_parse_empty_message_falls_back_to_chat():
    intent = _parse("")
    assert intent.action == ActionType.CHAT


def test_parse_search_only():
    intent = _parse("搜一下 AI 教育")
    assert intent.action == ActionType.SEARCH_ONLY
    assert intent.params.get("topic") == "AI 教育"


def test_parse_analyze_only():
    intent = _parse("分析一下 AI 教育")
    assert intent.action == ActionType.ANALYZE_ONLY
    assert intent.params.get("topic") == "AI 教育"


def test_parse_follow_up():
    intent = _parse("换个风格")
    assert intent.action == ActionType.FOLLOW_UP
    assert intent.params.get("modifier") == "换个风格"


def test_parse_explore():
    intent = _parse("调研一下 AI 教育的爆款规律")
    assert intent.action == ActionType.EXPLORE
    assert "AI 教育" in intent.params.get("topic", "")
