"""Stream retry: LLM stream call retry with transport fallback.

Ref: Codex responses_retry.rs — the key insight is:
  1. Distinguish "connection errors" (network) from "API errors" (4xx/5xx)
  2. Connection errors: unbounded retry with exponential backoff + user notification
  3. API errors: bounded retry with fallback transport
  4. Rate limit (429): special handling with longer backoff

Our adaptation:
  - StreamRetryState tracks retry counts and backoff delays
  - handle_retryable_error() decides whether to retry, fallback, or give up
  - Connection errors get longer backoff and more retries
  - 429 errors get rate-limit-specific backoff
  - Other API errors get short retry then fail

Usage:
    state = StreamRetryState()
    for attempt in range(state.max_retries):
        try:
            async for chunk in llm.stream_chat(messages):
                yield chunk
            break
        except Exception as e:
            action = state.handle_error(e)
            if action == RetryAction.GIVE_UP:
                raise
            elif action == RetryAction.RETRY:
                await asyncio.sleep(state.next_delay())
            elif action == RetryAction.FALLBACK:
                # switch to non-streaming
                result = await llm.chat(messages)
                yield result
                break
"""

from __future__ import annotations

import asyncio
import logging
import time
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class RetryAction(str, Enum):
    RETRY = "retry"
    FALLBACK = "fallback"
    GIVE_UP = "give_up"


class StreamRetryState:
    """Tracks retry state for LLM stream calls.

    Ref: Codex ResponsesStreamRetryState — tracks:
      - retries: total retry count
      - connection_retries: connection-specific retry count
      - connection_retry_delay: exponential backoff for connection errors
    """

    def __init__(
        self,
        max_retries: int = 3,
        max_connection_retries: int = 10,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        rate_limit_delay: float = 5.0,
    ) -> None:
        self.max_retries = max_retries
        self.max_connection_retries = max_connection_retries
        self._initial_delay = initial_delay
        self._max_delay = max_delay
        self._rate_limit_delay = rate_limit_delay

        self.retries = 0
        self.connection_retries = 0
        self._current_delay = initial_delay
        self._last_error: Exception | None = None
        self._last_error_time: float = 0

    def handle_error(self, error: Exception) -> RetryAction:
        """Decide what to do with a stream error.

        Ref: Codex handle_retryable_response_stream_error():
          - Connection errors: unbounded retry with backoff
          - Rate limits: retry with longer delay
          - Other errors: bounded retry then fallback/give-up
        """
        self._last_error = error
        self._last_error_time = time.monotonic()
        err_str = str(error).lower()
        err_type = type(error).__name__

        is_connection = any(
            kw in err_str
            for kw in ["connection", "timeout", "eof", "reset", "broken"]
        ) or any(
            kw in err_type.lower()
            for kw in ["connection", "timeout"]
        )

        is_rate_limit = (
            "429" in err_str
            or "rate" in err_str
            or "ratelimit" in err_type.lower()
        )

        is_server_error = any(
            kw in err_str
            for kw in ["500", "502", "503", "504", "server error", "overloaded"]
        )

        is_unrecoverable = any(
            kw in err_str
            for kw in ["402", "401", "403", "payment", "insufficient balance", "unauthorized", "forbidden", "invalid api key", "authentication"]
        )

        if is_unrecoverable:
            logger.error(
                f"[stream-retry] unrecoverable client error, giving up immediately: {error}"
            )
            return RetryAction.GIVE_UP

        if is_connection:
            if self.connection_retries < self.max_connection_retries:
                self.connection_retries += 1
                self.retries += 1
                self._current_delay = min(
                    self._current_delay * 2, self._max_delay
                )
                logger.warning(
                    f"[stream-retry] connection error "
                    f"(conn_retry={self.connection_retries}/{self.max_connection_retries}), "
                    f"retrying in {self._current_delay:.1f}s: {error}"
                )
                return RetryAction.RETRY
            logger.error(
                f"[stream-retry] max connection retries exceeded, giving up"
            )
            return RetryAction.FALLBACK

        if is_rate_limit:
            if self.retries < self.max_retries:
                self.retries += 1
                self._current_delay = self._rate_limit_delay * (2 ** (self.retries - 1))
                self._current_delay = min(self._current_delay, self._max_delay)
                logger.warning(
                    f"[stream-retry] rate limited "
                    f"(retry={self.retries}/{self.max_retries}), "
                    f"retrying in {self._current_delay:.1f}s"
                )
                return RetryAction.RETRY
            logger.error("[stream-retry] max rate-limit retries exceeded, falling back")
            return RetryAction.FALLBACK

        if is_server_error:
            if self.retries < self.max_retries:
                self.retries += 1
                self._current_delay = min(
                    self._initial_delay * (2 ** self.retries),
                    self._max_delay,
                )
                logger.warning(
                    f"[stream-retry] server error "
                    f"(retry={self.retries}/{self.max_retries}), "
                    f"retrying in {self._current_delay:.1f}s: {error}"
                )
                return RetryAction.RETRY
            return RetryAction.FALLBACK

        if self.retries < self.max_retries:
            self.retries += 1
            self._current_delay = self._initial_delay
            logger.warning(
                f"[stream-retry] unknown error "
                f"(retry={self.retries}/{self.max_retries}): {error}"
            )
            return RetryAction.RETRY

        return RetryAction.GIVE_UP

    def next_delay(self) -> float:
        return self._current_delay

    @property
    def last_error(self) -> Exception | None:
        return self._last_error

    def to_dict(self) -> dict[str, Any]:
        return {
            "retries": self.retries,
            "connection_retries": self.connection_retries,
            "current_delay": self._current_delay,
            "last_error": str(self._last_error) if self._last_error else None,
        }


async def call_llm_with_retry(
    llm: Any,
    messages: list[dict[str, Any]],
    use_stream: bool = True,
    max_retries: int = 3,
) -> tuple[str, int]:
    """Call LLM with retry and optional stream-to-non-stream fallback.

    Ref: Codex turn.rs run_turn() — the sampling loop:
      1. Try streaming first
      2. On connection error: retry with backoff
      3. On persistent failure: fallback to non-streaming
      4. Return (content, token_usage)

    This function wraps the retry logic so callers don't need to
    implement it themselves.
    """
    state = StreamRetryState(max_retries=max_retries)

    while True:
        try:
            if use_stream:
                stream_fn = getattr(llm, "stream_chat", None)
                if stream_fn is not None:
                    content_parts: list[str] = []
                    token_usage = 0
                    async for chunk in stream_fn(messages):
                        text = chunk.get("content", "")
                        if text:
                            content_parts.append(text)
                        if chunk.get("is_final"):
                            token_usage = chunk.get("token_usage", 0) or token_usage
                    return "".join(content_parts), token_usage

            result = await llm.chat(messages)
            return result.get("content", ""), result.get("token_usage", 0)

        except Exception as e:
            action = state.handle_error(e)

            if action == RetryAction.GIVE_UP:
                raise

            if action == RetryAction.FALLBACK:
                logger.info("[stream-retry] falling back to non-streaming call")
                use_stream = False
                state.retries = 0
                continue

            if action == RetryAction.RETRY:
                delay = state.next_delay()
                await asyncio.sleep(delay)
                continue

            logger.error(f"[stream-retry] unexpected RetryAction: {action}, giving up")
            raise

    return "", 0