"""Guardian: tool-call safety gate.

Ref: Codex exec.rs — every tool call goes through an approval chain:
  1. Policy check (is this tool allowed in this context?)
  2. Confirmation gate (does this high-risk action need user approval?)
  3. Argument validation (are the arguments safe and well-formed?)

Our adaptation:
  - Guardian wraps _dispatch_tool in LoopExecutor
  - Three-stage pipeline: policy -> confirm -> validate
  - Each stage can ALLOW, DENY, or NEEDS_CONFIRM
  - DENY returns error as observation (doesn't crash the loop)
  - NEEDS_CONFIRM pauses the loop and asks the user
  - All decisions are logged for audit

Usage:
    guardian = Guardian()
    decision = await guardian.check(tool_name, arguments, context, skill)
    if decision.action == Action.ALLOW:
        result = await skill.execute(inputs)
    elif decision.action == Action.DENY:
        observation = decision.to_observation()
    elif decision.action == Action.NEEDS_CONFIRM:
        # pause loop, ask user
"""

from __future__ import annotations

import logging
import re
from enum import Enum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.engine.schemas import Permission, WorkflowContext
    from app.tools.base import Skill

logger = logging.getLogger(__name__)


class GuardianAction(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    NEEDS_CONFIRM = "needs_confirm"


class GuardianDecision(BaseModel):
    action: GuardianAction
    reason: str = ""
    confirmation_prompt: str = ""
    risk_level: str = "low"
    hint: str = ""
    """给 LLM 的下一步指引（如权限被拒时告知如何向用户求助）。回喂 LLM 时不脱敏。"""

    def to_observation(self) -> str:
        import json

        payload = {
            "error": "guardian_denied",
            "reason": self.reason,
            "risk_level": self.risk_level,
        }
        if self.hint:
            payload["hint"] = self.hint
        return json.dumps(payload, ensure_ascii=False)


class GuardianPolicy(BaseModel):
    """Per-tool policy rule.

    Ref: Codex exec.rs — each Command has an associated policy:
      - Shell commands: sandboxed, needs confirmation
      - File reads: auto-allowed
      - File writes: needs confirmation
      - MCP calls: depends on the tool's risk level
    """

    tool_name: str
    auto_allow: bool = False
    needs_confirmation: bool = False
    max_argument_length: int = 10000
    denied_patterns: list[str] = []
    risk_level: str = "low"


_DEFAULT_POLICIES: dict[str, GuardianPolicy] = {
    "trending_search": GuardianPolicy(
        tool_name="trending_search",
        auto_allow=True,
        risk_level="low",
    ),
    "xhs_search": GuardianPolicy(
        tool_name="xhs_search",
        auto_allow=True,
        risk_level="low",
    ),
    "vl_analyze": GuardianPolicy(
        tool_name="vl_analyze",
        auto_allow=True,
        risk_level="low",
    ),
    "analyze": GuardianPolicy(
        tool_name="analyze",
        auto_allow=True,
        risk_level="low",
    ),
    "copywrite": GuardianPolicy(
        tool_name="copywrite",
        auto_allow=True,
        risk_level="medium",
    ),
    "blueprint": GuardianPolicy(
        tool_name="blueprint",
        auto_allow=True,
        risk_level="medium",
    ),
    "audit": GuardianPolicy(
        tool_name="audit",
        auto_allow=True,
        risk_level="medium",
    ),
    "image_gen": GuardianPolicy(
        tool_name="image_gen",
        auto_allow=True,
        risk_level="medium",
    ),
    "spawn_agent": GuardianPolicy(
        tool_name="spawn_agent",
        auto_allow=True,
        risk_level="medium",
    ),
    "wait_agent": GuardianPolicy(
        tool_name="wait_agent",
        auto_allow=True,
        risk_level="low",
    ),
    "list_agents": GuardianPolicy(
        tool_name="list_agents",
        auto_allow=True,
        risk_level="low",
    ),
    "send_message": GuardianPolicy(
        tool_name="send_message",
        auto_allow=True,
        risk_level="low",
    ),
    "interrupt_agent": GuardianPolicy(
        tool_name="interrupt_agent",
        auto_allow=True,
        risk_level="low",
    ),
    "file_write": GuardianPolicy(
        tool_name="file_write",
        needs_confirmation=True,
        risk_level="high",
        denied_patterns=[r"\.\./", r"/etc/", r"/proc/", r"C:\\Windows"],
    ),
    "bash_exec": GuardianPolicy(
        tool_name="bash_exec",
        needs_confirmation=True,
        risk_level="high",
        denied_patterns=[r"rm\s+-rf", r"sudo\s+", r"chmod\s+"],
    ),
    "bash": GuardianPolicy(
        tool_name="bash",
        needs_confirmation=True,
        risk_level="high",
        denied_patterns=[r"rm\s+-rf", r"sudo\s+", r"chmod\s+"],
    ),
}

_ARGUMENT_INJECTION_PATTERNS = [
    r";\s*rm\s",
    r";\s*sudo\s",
    r"\$\(",
    r"`",
    r"&&\s*rm\s",
    r"\|\s*sh\b",
    r"\b(eval|exec|system|subprocess|os\.system)\s*\(",
]


class Guardian:
    """Tool-call safety gate.

    Ref: Codex exec.rs architecture:
      - exec_command() checks policy before running
      - SandboxPolicy determines if command needs confirmation
      - UserConfirmation handles the interactive approval flow

    Our adaptation:
      - check() runs the three-stage pipeline
      - Stages are overridable for custom policies
      - Audit log records every decision
    """

    def __init__(
        self,
        policies: dict[str, GuardianPolicy] | None = None,
        strict_mode: bool = False,
    ) -> None:
        self._policies = policies or dict(_DEFAULT_POLICIES)
        self._strict_mode = strict_mode
        self._audit_log: list[dict[str, Any]] = []
        self._denied_count = 0
        self._allowed_count = 0
        self._confirmed_count = 0

    async def check(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: WorkflowContext | None = None,
        skill: Skill | None = None,
    ) -> GuardianDecision:
        policy = self._policies.get(tool_name)

        if policy is None:
            if self._strict_mode:
                decision = GuardianDecision(
                    action=GuardianAction.DENY,
                    reason=f"no policy for tool '{tool_name}' and strict mode is on",
                    risk_level="unknown",
                )
            else:
                decision = GuardianDecision(
                    action=GuardianAction.ALLOW,
                    reason=f"no policy for tool '{tool_name}', defaulting to allow",
                    risk_level="unknown",
                )
            self._record(tool_name, decision)
            return decision

        # Stage 1: auto-allow shortcut
        if policy.auto_allow and not policy.needs_confirmation:
            decision = GuardianDecision(
                action=GuardianAction.ALLOW,
                reason=f"auto-allowed by policy for '{tool_name}'",
                risk_level=policy.risk_level,
            )
            self._record(tool_name, decision)
            return decision

        # Stage 2: argument validation
        arg_decision = self._validate_arguments(tool_name, arguments, policy)
        if arg_decision is not None:
            self._record(tool_name, arg_decision)
            return arg_decision

        # Stage 3: permission gate (ref: Codex's permission check in exec.rs)
        if skill is not None and skill.required_permissions:
            from app.tools.permissions import permission_gate

            for perm in skill.required_permissions:
                if not permission_gate.is_allowed(perm, context):
                    decision = GuardianDecision(
                        action=GuardianAction.DENY,
                        reason=f"permission denied: {perm.value}",
                        risk_level=policy.risk_level,
                        hint=(
                            f"该权限（{perm.value}）未开放，这不是任务终点。"
                            "向用户说明缺少该权限、开启方法（backend/.env 的 "
                            "PERMISSIONS_ALLOW 加入对应值并重启后端），并明确询问"
                            "用户是否开启后继续。不要默默放弃或只字不提地结束任务。"
                        ),
                    )
                    self._record(tool_name, decision)
                    return decision

        # Stage 4: confirmation gate
        # 红线：bash / bash_exec 任何模式下都不自动放行（"deny 恒胜"原则，
        if policy.needs_confirmation:
            prompt = self._build_confirmation_prompt(tool_name, arguments, policy.risk_level)
            decision = GuardianDecision(
                action=GuardianAction.NEEDS_CONFIRM,
                reason=f"tool '{tool_name}' requires user confirmation",
                confirmation_prompt=prompt,
                risk_level=policy.risk_level,
            )
            self._confirmed_count += 1
            self._record(tool_name, decision)
            return decision

        decision = GuardianDecision(
            action=GuardianAction.ALLOW,
            reason=f"allowed by policy for '{tool_name}'",
            risk_level=policy.risk_level,
        )
        self._record(tool_name, decision)
        return decision

    def _validate_arguments(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        policy: GuardianPolicy,
    ) -> GuardianDecision | None:
        args_str = str(arguments)

        if len(args_str) > policy.max_argument_length:
            return GuardianDecision(
                action=GuardianAction.DENY,
                reason=f"arguments too long ({len(args_str)} > {policy.max_argument_length})",
                risk_level=policy.risk_level,
            )

        for pattern in policy.denied_patterns:
            try:
                if re.search(pattern, args_str):
                    return GuardianDecision(
                        action=GuardianAction.DENY,
                        reason=f"argument matches denied pattern: {pattern}",
                        risk_level=policy.risk_level,
                    )
            except re.error as e:
                logger.warning(f"[guardian] invalid denied_pattern regex '{pattern}': {e}")

        for pattern in _ARGUMENT_INJECTION_PATTERNS:
            try:
                if re.search(pattern, args_str, re.IGNORECASE):
                    return GuardianDecision(
                        action=GuardianAction.DENY,
                        reason=f"argument contains potential injection: {pattern}",
                        risk_level="high",
                    )
            except re.error as e:
                logger.warning(f"[guardian] invalid injection_pattern regex '{pattern}': {e}")

        return None

    def _build_confirmation_prompt(
        self, tool_name: str, arguments: dict[str, Any], risk_level: str = "high"
    ) -> str:
        args_summary = str(arguments)[:200]
        if risk_level == "high":
            risk_label = "⚠️ 高风险操作，请谨慎确认"
        elif risk_level == "medium":
            risk_label = "中等风险操作，需要您确认"
        else:
            risk_label = "低风险操作，需要您确认"
        return (
            f"Tool '{tool_name}' is about to execute with arguments:\n"
            f"{args_summary}\n\n"
            f"{risk_label}。是否继续？"
        )

    def _record(self, tool_name: str, decision: GuardianDecision) -> None:
        entry = {
            "tool": tool_name,
            "action": decision.action.value,
            "reason": decision.reason,
            "risk_level": decision.risk_level,
        }
        self._audit_log.append(entry)
        if decision.action == GuardianAction.DENY:
            self._denied_count += 1
        elif decision.action == GuardianAction.ALLOW:
            self._allowed_count += 1

        if decision.action == GuardianAction.DENY:
            logger.warning(f"[guardian] DENIED: {entry}")
        elif decision.action == GuardianAction.NEEDS_CONFIRM:
            logger.info(f"[guardian] NEEDS_CONFIRM: {entry}")
        else:
            logger.debug(f"[guardian] ALLOWED: {entry}")

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "allowed": self._allowed_count,
            "denied": self._denied_count,
            "confirmed": self._confirmed_count,
            "audit_log_size": len(self._audit_log),
        }

    def get_audit_log(self, last_n: int = 50) -> list[dict[str, Any]]:
        return self._audit_log[-last_n:]