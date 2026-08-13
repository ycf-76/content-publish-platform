"""Task-internal context Memory (D7).

Only task-internal context, flows with WorkflowState, no persistence.
"""

from __future__ import annotations

from typing import Any


class AgentMemory:
    """In-memory task context (D7).

    Not persisted. Not cross-task. Just a dict wrapper.
    """

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)

    def clear(self) -> None:
        self._data.clear()
