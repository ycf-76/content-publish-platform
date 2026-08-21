from app.agents.skills.permissions import resolve_execution_policy


def test_resolve_execution_policy_direct_is_trusted():
    assert resolve_execution_policy("direct") == (True, False)


def test_resolve_execution_policy_mcp_is_trusted():
    assert resolve_execution_policy("mcp") == (True, False)


def test_resolve_execution_policy_sandbox_is_untrusted():
    assert resolve_execution_policy("sandbox") == (False, True)
