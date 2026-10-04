"""Time Reminder: inject current time awareness into LLM context.

Ref: Codex time_reminder.rs — the key insight is:
  LLMs have no built-in sense of "now". Without time context:
    - They can't reason about recency ("what's trending NOW?")
    - They can't calculate durations ("3 days ago was...")
    - They may hallucinate timestamps or use stale training data

  Codex solves this by periodically injecting a "contextual user fragment"
  that contains the current time. The fragment is lightweight and doesn't
  consume much context budget.

Our adaptation:
  - TimeReminder tracks when the last reminder was injected
  - It generates a time fragment at configurable intervals (default 5 min)
  - The fragment is injected as a system-level message prefix
  - It integrates with the LLM call pipeline via hooks (pre_llm)
  - The reminder is minimal: just date/time/timezone, no verbose text

Usage:
    reminder = TimeReminder(interval_seconds=300)
    # Before each LLM call:
    fragment = reminder.maybe_inject()
    if fragment:
        messages.insert(0, {"role": "system", "content": fragment})
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class TimeFragment(BaseModel):
    """A time-awareness fragment to inject into LLM context.

    Ref: Codex ContextualUserFragment — a lightweight piece of context
    that the system injects on behalf of the user (or system).
    """
    content: str
    injected_at: float
    timezone: str = "UTC"


class TimeReminder:
    """Periodic time-awareness injector for LLM conversations.

    Ref: Codex time_reminder.rs:
      - Tracks last_reminder_at (monotonic timestamp)
      - On each LLM call, checks if enough time has elapsed
      - If so, generates a time fragment and injects it
      - The fragment is a "contextual user fragment" — system-level
        context that doesn't count as user input

    Key design from Codex:
      1. Interval is configurable (default 5 minutes)
      2. Fragment is minimal (just date/time, no extra text)
      3. Injection is idempotent (won't double-inject)
      4. Timezone-aware (uses UTC by default, configurable)
    """

    def __init__(
        self,
        interval_seconds: int = 300,
        timezone: str = "UTC",
        format_style: str = "iso",
    ) -> None:
        self._interval = interval_seconds
        self._timezone = timezone
        self._format_style = format_style
        self._last_injection_time: float = 0
        self._injection_count: int = 0

    def maybe_inject(self) -> TimeFragment | None:
        """Check if a time reminder should be injected, and return it if so.

        Ref: Codex time_reminder.rs::maybe_inject_time_reminder():
          - Called before each LLM call
          - Returns None if not enough time has elapsed
          - Returns a TimeFragment if injection is needed

        This is the main API: call before each LLM call.
        """
        now = time.monotonic()
        elapsed = now - self._last_injection_time

        if self._last_injection_time > 0 and elapsed < self._interval:
            return None

        self._last_injection_time = now
        self._injection_count += 1

        content = self._format_time()
        fragment = TimeFragment(
            content=content,
            injected_at=now,
            timezone=self._timezone,
        )

        logger.debug(
            f"[time-reminder] injected #{self._injection_count} "
            f"(interval={self._interval}s, elapsed={elapsed:.0f}s)"
        )
        return fragment

    def force_inject(self) -> TimeFragment:
        """Force a time injection regardless of interval.

        Useful when starting a new conversation or after a long pause.
        """
        self._last_injection_time = time.monotonic()
        self._injection_count += 1

        content = self._format_time()
        return TimeFragment(
            content=content,
            injected_at=self._last_injection_time,
            timezone=self._timezone,
        )

    def _format_time(self) -> str:
        """Format current time as a minimal context fragment.

        Ref: Codex formats time as a short, human-readable string.
        We keep it minimal to save context tokens.
        """
        now = datetime.now(UTC)

        if self._format_style == "iso":
            ts = now.isoformat(timespec="seconds")
        elif self._format_style == "relative":
            ts = now.strftime("%Y-%m-%d %H:%M UTC")
        else:
            ts = now.strftime("%Y-%m-%d %H:%M:%S UTC")

        return f"[Current time: {ts}]"

    def inject_into_messages(
        self,
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Inject time fragment into message list if needed.

        Ref: Codex injects the fragment as a system message prefix.
        We insert it right after the system prompt (position 1)
        to keep it in the system context but not override the main prompt.

        This is a convenience method that combines maybe_inject()
        with message list manipulation.
        """
        fragment = self.maybe_inject()
        if fragment is None:
            return messages

        time_msg = {"role": "system", "content": fragment.content}

        if messages and messages[0].get("role") == "system":
            messages.insert(1, time_msg)
        else:
            messages.insert(0, time_msg)

        return messages

    def reset(self) -> None:
        """Reset the reminder timer.

        Useful when starting a new conversation or resuming after
        a long pause.
        """
        self._last_injection_time = 0

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "interval_seconds": self._interval,
            "timezone": self._timezone,
            "injection_count": self._injection_count,
            "last_injection_ago": (
                time.monotonic() - self._last_injection_time
                if self._last_injection_time > 0
                else None
            ),
        }