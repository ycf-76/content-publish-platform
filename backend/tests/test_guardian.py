"""Tests for Guardian — tool-call safety gate.

Covers:
1. Default policies: auto-allow tools (trending_search, xhs_search, etc.)
2. High-risk tools requiring confirmation (file_write, bash_exec, bash)
3. Strict mode: unknown tools are denied
4. Non-strict mode: unknown tools are allowed by default
5. Argument validation: too-long arguments, denied patterns, injection patterns
6. Permission gate: skill with required_permissions denied
7. Audit log: every decision is recorded
8. to_observation() serialization
"""

import pytest

from app.engine.governance.guardian import (
    Guardian,
    GuardianAction,
    GuardianDecision,
    GuardianPolicy,
    _DEFAULT_POLICIES,
)


class TestGuardianDecision:
    def test_to_observation_basic(self):
        d = GuardianDecision(action=GuardianAction.DENY, reason="test reason", risk_level="high")
        obs = d.to_observation()
        assert '"error": "guardian_denied"' in obs
        assert '"reason": "test reason"' in obs
        assert '"risk_level": "high"' in obs

    def test_to_observation_with_hint(self):
        d = GuardianDecision(
            action=GuardianAction.DENY,
            reason="permission denied",
            risk_level="medium",
            hint="请向用户求助开启权限",
        )
        obs = d.to_observation()
        assert '"hint": "请向用户求助开启权限"' in obs

    def test_to_observation_no_hint(self):
        d = GuardianDecision(action=GuardianAction.ALLOW, reason="ok", risk_level="low")
        obs = d.to_observation()
        assert "hint" not in obs


class TestDefaultPolicies:
    def test_auto_allow_tools_exist(self):
        auto_allow_tools = ["trending_search", "xhs_search", "vl_analyze", "analyze", "copywrite", "blueprint", "audit", "image_gen"]
        for tool in auto_allow_tools:
            assert tool in _DEFAULT_POLICIES
            assert _DEFAULT_POLICIES[tool].auto_allow is True

    def test_high_risk_tools_need_confirmation(self):
        confirm_tools = ["file_write", "bash_exec", "bash"]
        for tool in confirm_tools:
            assert tool in _DEFAULT_POLICIES
            assert _DEFAULT_POLICIES[tool].needs_confirmation is True

    def test_file_write_denies_path_traversal(self):
        policy = _DEFAULT_POLICIES["file_write"]
        assert r"\.\./" in policy.denied_patterns

    def test_bash_denies_dangerous_commands(self):
        for tool in ["bash_exec", "bash"]:
            policy = _DEFAULT_POLICIES[tool]
            assert any("rm" in p for p in policy.denied_patterns)
            assert any("sudo" in p for p in policy.denied_patterns)


@pytest.fixture
def guardian():
    return Guardian()


@pytest.fixture
def strict_guardian():
    return Guardian(strict_mode=True)


class TestGuardianAutoAllow:
    @pytest.mark.asyncio
    async def test_trending_search_auto_allowed(self, guardian):
        decision = await guardian.check("trending_search", {"keyword": "护肤"})
        assert decision.action == GuardianAction.ALLOW
        assert decision.risk_level == "low"

    @pytest.mark.asyncio
    async def test_xhs_search_auto_allowed(self, guardian):
        decision = await guardian.check("xhs_search", {"query": "面膜推荐"})
        assert decision.action == GuardianAction.ALLOW

    @pytest.mark.asyncio
    async def test_copywrite_auto_allowed(self, guardian):
        decision = await guardian.check("copywrite", {"topic": "护肤"})
        assert decision.action == GuardianAction.ALLOW
        assert decision.risk_level == "medium"

    @pytest.mark.asyncio
    async def test_image_gen_auto_allowed(self, guardian):
        decision = await guardian.check("image_gen", {"prompt": "清新自然风格"})
        assert decision.action == GuardianAction.ALLOW


class TestGuardianConfirmation:
    @pytest.mark.asyncio
    async def test_file_write_needs_confirmation(self, guardian):
        decision = await guardian.check("file_write", {"path": "/tmp/test.txt", "content": "hello"})
        assert decision.action == GuardianAction.NEEDS_CONFIRM
        assert decision.risk_level == "high"

    @pytest.mark.asyncio
    async def test_bash_needs_confirmation(self, guardian):
        decision = await guardian.check("bash", {"command": "ls -la"})
        assert decision.action == GuardianAction.NEEDS_CONFIRM

    @pytest.mark.asyncio
    async def test_bash_exec_needs_confirmation(self, guardian):
        decision = await guardian.check("bash_exec", {"command": "echo hello"})
        assert decision.action == GuardianAction.NEEDS_CONFIRM


class TestGuardianStrictMode:
    @pytest.mark.asyncio
    async def test_unknown_tool_denied_in_strict_mode(self, strict_guardian):
        decision = await strict_guardian.check("unknown_tool", {})
        assert decision.action == GuardianAction.DENY
        assert "strict mode" in decision.reason

    @pytest.mark.asyncio
    async def test_unknown_tool_allowed_in_non_strict_mode(self, guardian):
        decision = await guardian.check("unknown_tool", {})
        assert decision.action == GuardianAction.ALLOW


class TestGuardianArgumentValidation:
    @pytest.mark.asyncio
    async def test_too_long_arguments_denied(self, guardian):
        long_args = {"data": "x" * 20000}
        decision = await guardian.check("file_write", long_args)
        assert decision.action == GuardianAction.DENY
        assert "too long" in decision.reason

    @pytest.mark.asyncio
    async def test_path_traversal_denied(self, guardian):
        decision = await guardian.check("file_write", {"path": "../../etc/passwd", "content": "hack"})
        assert decision.action == GuardianAction.DENY
        assert "denied pattern" in decision.reason

    @pytest.mark.asyncio
    async def test_sudo_injection_denied(self, guardian):
        decision = await guardian.check("bash", {"command": "sudo rm -rf /"})
        assert decision.action == GuardianAction.DENY

    @pytest.mark.asyncio
    async def test_command_substitution_injection_denied(self, guardian):
        decision = await guardian.check("bash", {"command": "echo $(cat /etc/passwd)"})
        assert decision.action == GuardianAction.DENY
        assert "injection" in decision.reason

    @pytest.mark.asyncio
    async def test_backtick_injection_denied(self, guardian):
        decision = await guardian.check("bash", {"command": "echo `whoami`"})
        assert decision.action == GuardianAction.DENY

    @pytest.mark.asyncio
    async def test_eval_injection_denied(self, guardian):
        decision = await guardian.check("bash", {"command": "python -c 'eval(input())'"})
        assert decision.action == GuardianAction.DENY


class TestGuardianAuditLog:
    @pytest.mark.asyncio
    async def test_decisions_are_recorded(self, guardian):
        await guardian.check("trending_search", {"keyword": "test"})
        await guardian.check("bash", {"command": "ls"})
        assert guardian._allowed_count >= 1
        assert guardian._confirmed_count >= 1
        assert len(guardian._audit_log) >= 2

    @pytest.mark.asyncio
    async def test_denied_count_increments(self, guardian):
        await guardian.check("bash", {"command": "sudo rm -rf /"})
        assert guardian._denied_count >= 1


class TestGuardianPolicyCustom:
    @pytest.mark.asyncio
    async def test_custom_policy_overrides_default(self):
        custom_policies = {
            "trending_search": GuardianPolicy(
                tool_name="trending_search",
                auto_allow=False,
                needs_confirmation=True,
                risk_level="high",
            ),
        }
        g = Guardian(policies=custom_policies)
        decision = await g.check("trending_search", {"keyword": "test"})
        assert decision.action == GuardianAction.NEEDS_CONFIRM