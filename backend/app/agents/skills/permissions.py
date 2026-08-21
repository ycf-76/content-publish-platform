"""权限门控系统。

红线（来自项目记忆）：
- Skill 在 execute() 之前必须经过权限门控。
- BASH/FILE_WRITE 等高危权限默认拒绝，必须显式开启。
- 权限决策来源优先级：环境变量 > 全局默认 > 节点上下文。

设计：
- Permission 枚举：列出所有可授予的权限。
- PermissionGate：单例。is_allowed / require 接口。
- PermissionDeniedError：被门控拒绝时抛出，由上层（Harness / Executor）捕获并转 NodeExecutionError。
- ContextVar current_permissions：在 workflow 执行链路里临时注入额外许可（例如某节点授予 BASH_EXEC）。
"""

from __future__ import annotations

import logging
import os
from contextvars import ContextVar
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.agents.core.schemas import WorkflowContext

logger = logging.getLogger(__name__)


class Permission(str, Enum):
    """所有可授予的权限。

    高危权限（BASH_EXEC / FILE_WRITE / NET_HTTP_POST / XHS_PUBLISH）
    在 settings 里必须显式 allow 才会被放行。
    """

    # 文件/命令
    FILE_READ = "file:read"
    FILE_WRITE = "file:write"
    BASH_EXEC = "bash:exec"

    # 网络
    NET_HTTP_GET = "net:http_get"
    NET_HTTP_POST = "net:http_post"

    # 小红书
    XHS_SEARCH = "xhs:search"
    XHS_PUBLISH = "xhs:publish"
    XHS_ACCOUNT_READ = "xhs:account_read"


# 默认低危权限：任何节点都自动具备
_DEFAULT_LOW_RISK: frozenset[Permission] = frozenset(
    {
        Permission.FILE_READ,
        Permission.NET_HTTP_GET,
        Permission.XHS_SEARCH,
        Permission.XHS_ACCOUNT_READ,
    }
)

# 高危权限白名单（来自环境变量 PERMISSIONS_ALLOW）
_HIGH_RISK_ALL: frozenset[Permission] = frozenset(
    {
        Permission.FILE_WRITE,
        Permission.BASH_EXEC,
        Permission.NET_HTTP_POST,
        Permission.XHS_PUBLISH,
    }
)


def resolve_execution_policy(execution_policy: str) -> tuple[bool, bool]:
    """把 Skill.execution_policy 收敛为「是否可信 + 是否沙箱」的单一决策。

    这是信任/沙箱决策的唯一入口，替代 sandbox_workflow_bridge 里分散的
    is_trusted_plugin / should_use_sandbox 判断。

    Returns:
        (is_trusted, use_sandbox)
        - direct / mcp：可信，直接/内置执行
        - sandbox：不可信，Docker 沙箱隔离执行
    """
    if execution_policy == "sandbox":
        return (False, True)
    return (True, False)


class PermissionDeniedError(Exception):
    """权限被拒绝。"""

    def __init__(self, permission: Permission, reason: str = "") -> None:
        self.permission = permission
        self.reason = reason
        super().__init__(
            f"Permission denied: {permission.value}" + (f" ({reason})" if reason else "")
        )


# 节点级临时许可：在 workflow 执行链路里通过 set/tmp setter 注入
current_permissions: ContextVar[frozenset[Permission] | None] = ContextVar(
    "current_permissions", default=None
)


class _PermissionGate:
    """权限门控单例。

    决策逻辑：
    1. 低危权限（FILE_READ / NET_HTTP_GET / XHS_SEARCH / XHS_ACCOUNT_READ）：始终允许。
    2. 高危权限：必须出现在 allowed_high_risk 集合里。
       allowed_high_risk 来源：env `PERMISSIONS_ALLOW`（逗号分隔）+ 节点级 ContextVar 临时授予。
    """

    def __init__(self) -> None:
        self._env_allowed = self._load_env_allowed()

    @staticmethod
    def _load_env_allowed() -> frozenset[Permission]:
        raw = os.environ.get("PERMISSIONS_ALLOW", "") or ""
        out: set[Permission] = set()
        for tok in raw.split(","):
            tok = tok.strip().lower()
            if not tok:
                continue
            try:
                out.add(Permission(tok))
            except ValueError:
                logger.warning(f"Unknown permission in PERMISSIONS_ALLOW: {tok!r}")
        # 只接受高危权限白名单里的项
        return frozenset(out & _HIGH_RISK_ALL)

    def is_allowed(
        self,
        permission: Permission,
        context: WorkflowContext | None = None,
    ) -> bool:
        """是否放行。"""
        if permission in _DEFAULT_LOW_RISK:
            return True
        if permission in self._env_allowed:
            return True
        # 节点级临时许可
        extra = current_permissions.get(None)
        if extra and permission in extra:
            return True
        return False

    async def require(
        self,
        permissions: list[Permission] | tuple[Permission, ...] | set[Permission],
        context: WorkflowContext | None = None,
    ) -> None:
        """校验一组权限，任一被拒即抛 PermissionDeniedError。"""
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
        """测试用：env 改了之后重新加载。"""
        self._env_allowed = self._load_env_allowed()


# 单例
permission_gate = _PermissionGate()


class permission_scope:
    """节点级临时授权上下文管理器。

    用法：
        with permission_scope({Permission.BASH_EXEC}):
            await skill.execute(...)
    """

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
