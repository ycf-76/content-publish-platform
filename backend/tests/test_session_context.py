from app.agents.context import SessionContext


def test_session_context_defaults():
    ctx = SessionContext(session_id="s1", user_id="u1")
    assert ctx.last_workflow_id is None
    assert ctx.upstream_outputs == {}
    assert ctx.working_state == {}


def test_session_context_records_and_clears_workflow():
    ctx = SessionContext(session_id="s1", user_id="u1")
    outputs = {"copywrite": {"title": "标题"}, "image_gen": {"count": 3}}
    ctx.record_workflow("wf_1", outputs)

    assert ctx.last_workflow_id == "wf_1"
    assert ctx.upstream_outputs == outputs

    ctx.clear_workflow()
    assert ctx.last_workflow_id is None
    assert ctx.upstream_outputs == {}
