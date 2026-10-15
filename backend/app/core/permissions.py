"""权限门控系统。

红线（来自项目记忆）：
- Skill 在 execute() 之前必须经过权限门控。
- BASH/FILE_WRITE 等高危权限默认拒绝，必须显式开启。
- 权限决策来源优先级：环境变量 > 全局默认 > 节点上下文。

设计：
- Permission 枚举 / PermissionDeniedError：定义在 core/schemas.py（零依赖，供全项目共享）。
- PermissionGate：单例。is_allowed / require 接口。
- ContextVar current_permissions：在 workflow 执行链路里临时注入额外许可（例如某节点授予 BASH_EXEC）。
"""

from __future__ import annotations

import logging
import os
from contextvars import ContextVar
from typing import TYPE_CHECKING

from app.engine.schemas import Permission, PermissionDeniedError

if TYPE_CHECKING:
    from app.engine.schemas import WorkflowContext

logger = logging.getLogger(__name__)


_DEFAULT_LOW_RISK: frozenset[Permission] = frozenset(
    {
        Permission.FILE_READ,
        Permission.NET_HTTP_GET,
        Permission.XHS_SEARCH,
    }
)

_HIGH_RISK_ALL: frozenset[Permission] = frozenset(
    {
        Permission.FILE_WRITE,
        Permission.BASH_EXEC,
        Permission.NET_HTTP_POST,
        Permission.SKILL_IMPORT,
        Permission.BROWSER_AUTOMATE,
    }
)


def resolve_execution_policy(execution_policy: str) -> tuple[bool, bool]:
    if execution_policy == "sandbox":
        return (False, True)
    return (True, False)


current_permissions: ContextVar[frozenset[Permission] | None] = ContextVar(
    "current_permissions", default=None
)


class _PermissionGate:
    def __init__(self) -> None:
        self._env_allowed = self._load_env_allowed()

    @staticmethod
    def _load_env_allowed() -> frozenset[Permission]:
        raw = os.environ.get("PERMISSIONS_ALLOW", "") or ""
        if not raw:
            try:
                from app.config import get_settings
                raw = (get_settings().permissions_allow or "").strip()
            except Exception:
                raw = ""
        out: set[Permission] = set()
        for tok in raw.split(","):
            tok = tok.strip().lower()
            if not tok:
                continue
            try:
                out.add(Permission(tok))
            except ValueError:
                logger.warning(f"Unknown permission in PERMISSIONS_ALLOW: {tok!r}")
        return frozenset(out & _HIGH_RISK_ALL)

    def is_allowed(
        self,
        permission: Permission,
        context: WorkflowContext | None = None,
    ) -> bool:
        if permission in _DEFAULT_LOW_RISK:
            return True
        if permission in self._env_allowed:
            return True
        extra = current_permissions.get(None)
        if extra and permission in extra:
            return True
        return False

    async def require(
        self,
        permissions: list[Permission] | tuple[Permission, ...] | set[Permission],
        context: WorkflowContext | None = None,
    ) -> None:
        for p in permissions:
            if not self.is_allowed(p, context):
                logger.warning(
                    f"Permission gate denied: {p.value} "
                    f"(node={context.node_id if context else '-'})"
                )
                raise PermissionDeniedError(
                    p,
                    reason="not in low-risk defaults nor allowed_high_risk",
                )

    def reset_env_cache(self) -> None:
        self._env_allowed = self._load_env_allowed()


permission_gate = _PermissionGate()


class permission_scope:
    def __init__(self, extra: set[Permission] | frozenset[Permission]) -> None:
        self._extra = frozenset(extra)
        self._token = None

    def __enter__(self) -> permission_scope:
        prev = current_permissions.get(None)
        merged = frozenset(self._extra | (prev or frozenset()))
        self._token = current_permissions.set(merged)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._token is not None:
            current_permissions.reset(self._token)