"""Loop state persistence for confirmation gate (interrupt-resume).

When a Skill requires user confirmation, the LoopExecutor saves
the current loop state to a JSON file. The confirm API loads it
and resumes the loop with the user's decision.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CLARIFICATION_TIMEOUT_SECONDS = 30 * 60
_CLARIFICATION_EXPIRED_GRACE_SECONDS = 5 * 60

_loop_state_locks: dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()


def _get_lock(path: str) -> threading.Lock:
    with _locks_lock:
        if path not in _loop_state_locks:
            _loop_state_locks[path] = threading.Lock()
        return _loop_state_locks[path]


def _state_dir() -> Path:
    root = Path(os.environ.get("WORKSPACE_ROOT", os.getcwd()))
    d = root / "data" / "loop_states"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_loop_state(
    session_id: str,
    state: dict[str, Any],
    max_iterations: int | None = None,
) -> str:
    """Save loop state to file. Returns the file path."""
    if max_iterations is not None:
        state["max_iterations"] = int(max_iterations)
    if state.get("_awaiting_clarification") and "_clarification_saved_at" not in state:
        state["_clarification_saved_at"] = datetime.now(timezone.utc).isoformat()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    filename = f"{session_id}_{ts}.json"
    path = _state_dir() / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, default=str)
    return str(path)


def _validate_state_path(path: str) -> Path:
    """Validate that path resolves inside _state_dir() to prevent traversal."""
    resolved = Path(path).resolve()
    state_root = _state_dir().resolve()
    try:
        resolved.relative_to(state_root)
    except ValueError:
        raise FileNotFoundError(
            f"loop state path escapes state dir: {path} -> {resolved} "
            f"(allowed root: {state_root})"
        )
    if not resolved.is_file():
        raise FileNotFoundError(f"loop state not found: {path}")
    return resolved


def load_loop_state(path: str) -> dict[str, Any]:
    """Load loop state from file (path-traversal safe + schema validated)."""
    resolved = _validate_state_path(path)
    with open(resolved, "r", encoding="utf-8") as f:
        state = json.load(f)
    _validate_state_schema(state)
    return state


_MAX_MESSAGES = 500
_MAX_ITERATIONS = 200
_ALLOWED_ROLES = frozenset({"system", "user", "assistant", "tool"})


def _validate_state_schema(state: dict[str, Any]) -> None:
    """Validate critical fields of loaded loop state to prevent injection.

    Guards against tampered state files that could inject forged system
    messages or corrupt iteration counters.
    """
    if not isinstance(state, dict):
        raise ValueError("loop state must be a JSON object")

    messages = state.get("messages")
    if messages is not None:
        if not isinstance(messages, list):
            raise ValueError("loop state 'messages' must be a list")
        if len(messages) > _MAX_MESSAGES:
            raise ValueError(
                f"loop state has {len(messages)} messages, max allowed: {_MAX_MESSAGES}"
            )
        for i, msg in enumerate(messages):
            if not isinstance(msg, dict):
                raise ValueError(f"message[{i}] must be a dict")
            role = msg.get("role", "")
            if role not in _ALLOWED_ROLES:
                raise ValueError(f"message[{i}] has invalid role: {role!r}")

    iteration = state.get("iteration")
    if iteration is not None:
        if not isinstance(iteration, int) or iteration < 0 or iteration > _MAX_ITERATIONS:
            raise ValueError(
                f"loop state 'iteration' out of range: {iteration}"
            )

    max_iter = state.get("max_iterations")
    if max_iter is not None:
        if not isinstance(max_iter, int) or max_iter < 1 or max_iter > _MAX_ITERATIONS:
            raise ValueError(
                f"loop state 'max_iterations' out of range: {max_iter}"
            )


def cleanup_loop_state(path: str) -> None:
    """Delete a loop state file (path-traversal safe)."""
    try:
        resolved = _validate_state_path(path)
        os.remove(resolved)
    except (OSError, FileNotFoundError):
        pass


def check_clarification_timeout(state: dict[str, Any]) -> str | None:
    """检查澄清是否超时（§5.3）。

    Returns:
        None: 未超时
        "expired": 已超时，应自动 skip
        "grace": 已超时但在宽限期内，仍可提交
    """
    if not state.get("_awaiting_clarification"):
        return None
    saved_at_str = state.get("_clarification_saved_at")
    if not saved_at_str:
        return None
    try:
        saved_at = datetime.fromisoformat(saved_at_str)
        if saved_at.tzinfo is None:
            saved_at = saved_at.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - saved_at).total_seconds()
        if elapsed > _CLARIFICATION_TIMEOUT_SECONDS + _CLARIFICATION_EXPIRED_GRACE_SECONDS:
            return "expired"
        if elapsed > _CLARIFICATION_TIMEOUT_SECONDS:
            return "grace"
        return None
    except (ValueError, TypeError):
        return None


def mark_loop_state_expired(path: str) -> None:
    """标记 loop_state 为 expired（§5.3 v2.2 超时清理竞争修复，path-traversal safe）。"""
    try:
        resolved = _validate_state_path(path)
        with open(resolved, "r", encoding="utf-8") as f:
            state = json.load(f)
        state["_clarification_expired"] = True
        with open(resolved, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, default=str)
    except (OSError, json.JSONDecodeError, FileNotFoundError):
        pass