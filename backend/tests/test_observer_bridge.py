import asyncio

from app.agents.harnesses.factory import _make_observer
from app.services.sse_bus import sse_bus


def _patch_publish(monkeypatch, calls: list):
    async def fake_publish(workflow_id: str, event_type: str, payload: dict) -> str:
        calls.append((workflow_id, event_type, payload))
        return "evt_test"

    monkeypatch.setattr(sse_bus, "publish", fake_publish)


def test_observer_bridge_publishes_agent_thinking(monkeypatch):
    calls: list = []
    _patch_publish(monkeypatch, calls)

    observer = _make_observer("wf_1")
    asyncio.run(observer.emit_llm_stream("node1", {"content": "hello"}))

    assert calls == [
        ("wf_1", "agent_thinking", {"node_id": "node1", "chunk": {"content": "hello"}})
    ]


def test_observer_bridge_publishes_tool_call_recovery_circuit(monkeypatch):
    calls: list = []
    _patch_publish(monkeypatch, calls)

    observer = _make_observer("wf_1")

    async def run():
        await observer.emit_tool_call_start("node1", "xhs_search", {"keyword": "AI"})
        await observer.log_attempt("node1", 1, "retry", {"kw": "AI"})
        await observer.log_circuit_open("node1", "open")

    asyncio.run(run())

    assert ("wf_1", "tool_call_start", {"node_id": "node1", "tool_name": "xhs_search", "inputs": {"keyword": "AI"}}) in calls
    assert ("wf_1", "recovery_attempt", {"node_id": "node1", "attempt": 1, "strategy": "retry", "adjusted": {"kw": "AI"}}) in calls
    assert ("wf_1", "circuit_open", {"node_id": "node1", "state": "open"}) in calls
