"""FastAPI 公共依赖。

提供基于 JWT 的用户身份解析依赖 get_current_user，供所有需要登录的路由使用。

用法：
    from app.api.deps import get_current_user

    @router.get(...)
    async def handler(user_id: str = Depends(get_current_user)):
        ...
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.security import decode_user_id

# Bearer token scheme，auto_error=False 让我们在依赖里返回统一错误格式
_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> str:
    """从 Authorization: Bearer <jwt> 或 ?token=<jwt> 解析当前用户 ID。

    优先读取 Authorization header，若不存在则尝试 query 参数 token
    （供 EventSource 等不支持自定义 header 的场景使用）。

    Returns:
        user_id（JWT sub claim）

    Raises:
        HTTPException 401: 未提供 token / scheme 非 Bearer / token 无效或过期
    """
    jwt_token: str | None = None

    if credentials is not None and (credentials.scheme or "").lower() == "bearer":
        jwt_token = credentials.credentials
    else:
        jwt_token = request.query_params.get("token")

    if not jwt_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供登录凭证",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return decode_user_id(jwt_token)