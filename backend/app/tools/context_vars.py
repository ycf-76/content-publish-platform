"""Context variables for cross-cutting concerns (db session, etc.).

Uses Python ContextVar for coroutine-safe context passing.
Mirrors the pattern used by PermissionGate.current_permissions.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

current_db_session: ContextVar["AsyncSession | None"] = ContextVar(
    "current_db_session", default=None
)
