"""Regression tests for “send me the latest draft” follow-ups."""
from app.api.routers.chat_agent import _is_bare_analysis_request
from app.agents.top_planner import ToolName, _keyword_fallback
from app.engine.harness.executor.loop import LoopExecutor
from app.rpa.wechat_agent_bridge import BridgeAction, _classify_intent


def test_keyword_fallback_send_latest_uses_recent_title():
    plan = _keyword_fallback(
        "发给我",
        {"user_memory": {"recent_copywrites": [{"title": "今日热点新闻一览"}]}},
    )
    tools = [tc.tool for tc in plan.tools]
    assert tools == [ToolName.WECHAT_PUSH]
    assert plan.topic == "今日热点新闻一览"


def test_keyword_fallback_wechat_phrase_does_not_recreate_content():
    plan = _keyword_fallback(
        "将写完的内容发给我微信",
        {
            "user_memory": {"recent_copywrites": [{"title": "今日热点新闻一览"}]},
            "last_topic": "今日热点新闻",
        },
    )
    tools = [tc.tool for tc in plan.tools]
    assert tools == [ToolName.WECHAT_PUSH]
    assert plan.topic == "今日热点新闻一览"


def test_keyword_fallback_does_not_echo_plain_chat():
    plan = _keyword_fallback("今天天气怎么样")
    assert plan.is_chat is True
    assert not plan.direct_answer


def test_keyword_fallback_analyzes_copy_phrase():
    plan = _keyword_fallback("帮我分析一下这篇文案")
    tools = [tc.tool for tc in plan.tools]
    assert tools == [ToolName.ANALYZE]
    assert plan.is_chat is False


def test_wechat_bridge_classifies_send_latest():
    for text in ("发给我", "把写完的内容发给我", "发给我。"):
        action, _ = _classify_intent(text)
        assert action == BridgeAction.SEND_LATEST


def test_wechat_bridge_create_then_send_stays_agent_chat():
    action, _ = _classify_intent("写一篇咖啡文案发给我")
    assert action == BridgeAction.AGENT_CHAT


def test_bare_analysis_request_is_short_circuited_before_loop():
    assert _is_bare_analysis_request("帮我分析一下这篇文案") is True
    assert _is_bare_analysis_request("分析一下这篇") is True
    assert _is_bare_analysis_request("帮我分析一下这篇文案：标题是夏日穿搭") is False
    assert _is_bare_analysis_request("帮我写一篇文案") is False


def test_loop_does_not_require_copy_tools_for_bare_analysis():
    message = "帮我分析一下这篇文案"
    assert LoopExecutor._is_action_intent_text(message) is False
    assert LoopExecutor._required_tools_for_request(message, message) == set()
