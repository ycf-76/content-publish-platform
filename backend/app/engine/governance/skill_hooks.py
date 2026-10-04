"""Lightweight governance hooks for Skill layer.

Problem: LangGraph nodes bypass Harness, so governance (token_budget, llm_queue, guardian)
is never invoked. This module provides singleton governance that Skills can use directly
without going through Harness.

Usage in Skill.execute():
    from app.engine.governance.skill_hooks import skill_governance

    # Before LLM call: rate limit + token check
    await skill_governance.pre_llm_call(estimated_tokens=2000)

    # After LLM call: record usage
    skill_governance.post_llm_call(tokens_used=1500)
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class SkillGovernance:
    """Singleton governance context for Skill layer.

    Provides:
    - Rate limiting: ensures LLM calls don't exceed RPM/concurrency limits
    - Token tracking: records token usage per workflow
    - Safety gate: basic content safety check before publish
    """

    def __init__(
        self,
        max_rpm: int = 200,
        max_concurrent: int = 10,
        token_window: int = 128_000,
        token_warn_threshold: float = 0.8,
    ) -> None:
        self._max_rpm = max_rpm
        self._max_concurrent = max_concurrent
        self._token_window = token_window
        self._token_warn_threshold = token_warn_threshold

        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._call_timestamps: list[float] = []
        self._total_tokens = 0
        self._total_calls = 0
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        logger.info(
            f"[skill-governance] started: rpm={self._max_rpm}, "
            f"concurrent={self._max_concurrent}, "
            f"token_window={self._token_window}"
        )

    async def pre_llm_call(self, estimated_tokens: int = 0) -> None:
        """Call before each LLM invocation. Enforces rate limit + concurrency."""
        if not self._started:
            self.start()

        await self._enforce_rpm()
        await self._semaphore.acquire()

        if estimated_tokens > 0:
            remaining = self._token_window - self._total_tokens
            if remaining < estimated_tokens:
                logger.warning(
                    f"[skill-governance] token budget low: "
                    f"remaining={remaining}, estimated={estimated_tokens}"
                )

    def post_llm_call(self, tokens_used: int = 0) -> None:
        """Call after each LLM invocation. Records usage."""
        self._semaphore.release()
        if tokens_used > 0:
            self._total_tokens += tokens_used
        self._total_calls += 1

        if self._total_tokens > self._token_window * self._token_warn_threshold:
            logger.warning(
                f"[skill-governance] token usage at "
                f"{self._total_tokens / self._token_window:.1%} of window"
            )

    async def _enforce_rpm(self) -> None:
        """Token-bucket RPM enforcement."""
        now = time.monotonic()
        cutoff = now - 60.0
        self._call_timestamps = [t for t in self._call_timestamps if t > cutoff]

        if len(self._call_timestamps) >= self._max_rpm:
            oldest = self._call_timestamps[0]
            wait = 60.0 - (now - oldest) + 0.1
            logger.warning(f"[skill-governance] RPM limit hit, waiting {wait:.1f}s")
            await asyncio.sleep(wait)

        self._call_timestamps.append(time.monotonic())

    def content_safety_check(self, text: str) -> list[str]:
        """Basic content safety scan. Returns list of warnings (empty = safe)."""
        warnings: list[str] = []
        if not text:
            return warnings

        import re

        api_key_patterns = [
            r"sk-[a-zA-Z0-9]{20,}",
            r"AKIA[0-9A-Z]{16}",
            r"AIza[a-zA-Z0-9_-]{35}",
        ]
        for pattern in api_key_patterns:
            if re.search(pattern, text):
                warnings.append(f"Possible API key detected (pattern: {pattern[:6]}...)")

        internal_url_pattern = r"https?://(localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+|192\.168\.\d+\.\d+)"
        if re.search(internal_url_pattern, text):
            warnings.append("Internal/private URL detected")

        return warnings

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "total_calls": self._total_calls,
            "total_tokens": self._total_tokens,
            "token_window": self._token_window,
            "token_usage_pct": f"{self._total_tokens / self._token_window:.1%}" if self._token_window else "N/A",
        }


_global_governance: SkillGovernance | None = None


def get_skill_governance() -> SkillGovernance:
    global _global_governance
    if _global_governance is None:
        _global_governance = SkillGovernance()
        _global_governance.start()
    return _global_governance


skill_governance = get_skill_governance()