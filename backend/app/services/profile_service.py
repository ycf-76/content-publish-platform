"""用户画像服务（D18 创作者画像）。

职责：
- 读取画像（DB 为唯一事实来源，禁止 localStorage / 内存缓存替代）
- 工作流启动前置校验（画像缺失 → ProfileValidationError → 拒绝启动）
- upsert 画像（与 users 表 1:1）

红线（《开发红线手册》7.4）：
- 每次启动工作流前必须从这里读取画像注入 WorkflowState
- 画像缺失/主领域为空时抛 ProfileValidationError（fail-fast）
- primary_domain 应用层防御性校验（DB 层 NOT NULL 之外再查一次）
"""

from __future__ import annotations

import logging
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.profile import (
    ProfileValidationError,
    UpdateProfileRequest,
    UserProfile,
)
from app.db.models import (
    CreatorTone,
    PrimaryDomain,
    UserProfile as UserProfileORM,
    VisualStyle,
)

logger = logging.getLogger(__name__)


def _orm_to_schema(orm_obj: UserProfileORM) -> UserProfile:
    """ORM 行 → Pydantic Schema（str 枚举值安全转换）。"""
    return UserProfile(
        primary_domain=PrimaryDomain(orm_obj.primary_domain),
        sub_domain=orm_obj.sub_domain,
        tone=CreatorTone(orm_obj.tone),
        visual_style=VisualStyle(orm_obj.visual_style),
        taboo_topics=list(orm_obj.taboo_topics or []),
        taboo_words=list(orm_obj.taboo_words or []),
        identity=orm_obj.identity,
        differentiation=orm_obj.differentiation,
        content_direction=orm_obj.content_direction,
        target_audience=orm_obj.target_audience,
        audience_pain_points=orm_obj.audience_pain_points,
        opening_style=orm_obj.opening_style,
        content_rhythm=orm_obj.content_rhythm,
        signature_elements=orm_obj.signature_elements,
    )


class ProfileService:
    """画像读取 / 校验 / upsert 服务。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_profile(self, user_id: str) -> UserProfile | None:
        """读取画像，不存在返回 None。

        user_profiles.user_id 唯一（1:1），scalar_one_or_none 语义安全。
        """
        if not user_id:
            return None
        try:
            result = await self.db.execute(
                select(UserProfileORM).where(UserProfileORM.user_id == user_id)
            )
            orm_obj = result.scalar_one_or_none()
        except Exception as e:
            # 表可能尚未迁移：按"无画像"处理，让 get_or_validate 拒绝启动
            logger.warning(f"[profile] get_profile query failed: {e}")
            return None
        if orm_obj is None:
            return None
        return _orm_to_schema(orm_obj)

    async def get_or_validate(self, user_id: str) -> UserProfile:
        """读取并校验画像，用于工作流启动前置检查。

        Raises:
            ProfileValidationError:
                - profile_not_found: 画像不存在（或表不可读）
                - primary_domain_empty: 主领域为空（防御性，DB NOT NULL 兜底）
        """
        profile = await self.get_profile(user_id)
        if profile is None:
            raise ProfileValidationError(reason="profile_not_found")
        if not profile.primary_domain or not str(profile.primary_domain.value).strip():
            raise ProfileValidationError(reason="primary_domain_empty")
        return profile

    async def upsert_profile(
        self,
        user_id: str,
        req: UpdateProfileRequest,
    ) -> UserProfile:
        """创建或更新画像（PUT 语义，1:1 不重复建行）。

        primary_domain 必填由 pydantic 校验，这里再防御性检查一次。
        """
        if not user_id:
            raise ProfileValidationError(reason="profile_not_found")
        # 防御性检查：空值在类型层已被拦截，这里兜底
        if not req.primary_domain or not str(req.primary_domain.value).strip():
            raise ProfileValidationError(reason="primary_domain_empty")

        result = await self.db.execute(
            select(UserProfileORM).where(UserProfileORM.user_id == user_id)
        )
        orm_obj = result.scalar_one_or_none()

        if orm_obj is None:
            orm_obj = UserProfileORM(
                user_id=user_id,
                primary_domain=PrimaryDomain(req.primary_domain),
                sub_domain=req.sub_domain,
                tone=CreatorTone(req.tone),
                visual_style=VisualStyle(req.visual_style),
                taboo_topics=list(req.taboo_topics),
                taboo_words=list(req.taboo_words),
                identity=req.identity,
                differentiation=req.differentiation,
                content_direction=req.content_direction,
                target_audience=req.target_audience,
                audience_pain_points=req.audience_pain_points,
                opening_style=req.opening_style,
                content_rhythm=req.content_rhythm,
                signature_elements=req.signature_elements,
            )
            self.db.add(orm_obj)
            logger.info(f"[profile] created for user {user_id}: domain={req.primary_domain}")
        else:
            orm_obj.primary_domain = PrimaryDomain(req.primary_domain)
            orm_obj.sub_domain = req.sub_domain
            orm_obj.tone = CreatorTone(req.tone)
            orm_obj.visual_style = VisualStyle(req.visual_style)
            orm_obj.taboo_topics = list(req.taboo_topics)
            orm_obj.taboo_words = list(req.taboo_words)
            orm_obj.identity = req.identity
            orm_obj.differentiation = req.differentiation
            orm_obj.content_direction = req.content_direction
            orm_obj.target_audience = req.target_audience
            orm_obj.audience_pain_points = req.audience_pain_points
            orm_obj.opening_style = req.opening_style
            orm_obj.content_rhythm = req.content_rhythm
            orm_obj.signature_elements = req.signature_elements
            logger.info(f"[profile] updated for user {user_id}: domain={req.primary_domain}")

        await self.db.commit()
        await self.db.refresh(orm_obj)
        # 写入后立即失效读缓存，保证 chat 软注入读到最新画像
        invalidate_profile_cache(user_id)
        return _orm_to_schema(orm_obj)


def get_profile_service(db: AsyncSession) -> ProfileService:
    """工厂函数（与其他 service 的 get_xxx_service 模式一致）。"""
    return ProfileService(db)


# ============================================================================
# Chat 链路软注入专用 TTL 缓存
# ============================================================================

_PROFILE_CACHE_TTL = 60.0
_profile_cache: dict[str, tuple[UserProfile | None, float]] = {}


async def get_profile_cached(db: AsyncSession, user_id: str) -> UserProfile | None:
    """Chat 链路（ReAct Loop）软注入用的 TTL 缓存读取。

    红线说明：DB 仍是唯一事实来源，本缓存仅为读性能优化——
    LoopExecutor 每轮可能有多次 skill 调用，避免每次都打 DB。
    TTL 到期或 upsert 后自动失效。
    fail-fast 校验路径（get_or_validate）不走缓存，直读 DB。
    """
    if not user_id:
        return None
    now = time.monotonic()
    hit = _profile_cache.get(user_id)
    if hit is not None and now - hit[1] < _PROFILE_CACHE_TTL:
        return hit[0]
    profile = await ProfileService(db).get_profile(user_id)
    _profile_cache[user_id] = (profile, now)
    return profile


def invalidate_profile_cache(user_id: str) -> None:
    """画像更新后清除缓存（写入路径必调，保证读一致）。"""
    _profile_cache.pop(user_id, None)