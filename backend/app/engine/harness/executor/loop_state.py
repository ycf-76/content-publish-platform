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


def load_loop_state(path: str) -> dict[str, Any]:
    """Load loop state from file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def cleanup_loop_state(path: str) -> None:
    """Delete a loop state file."""
    try:
        os.remove(path)
    except OSError:
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
    """标记 loop_state 为 expired（§5.3 v2.2 超时清理竞争修复）。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
        state["_clarification_expired"] = True
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, default=str)
    except (OSError, json.JSONDecodeError):
        pass