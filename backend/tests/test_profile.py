"""用户画像（D18）单元测试：Schema + ProfileService + Router。

覆盖手册 Step 2 自检清单：
1. GET 未设置画像返回 data=null（不报错）
2. PUT 创建画像（upsert，1:1 不重复建行）
3. PUT 更新画像
4. PUT 缺 primary_domain → 422
5. /validate 画像完整 → valid=true
6. /validate 无画像 → valid=false, reason=profile_not_found
7. get_or_validate 无画像 → ProfileValidationError

测试不依赖真实数据库（AsyncMock + FastAPI 依赖覆盖）。
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.routers.profile import router as profile_router
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
from app.services.profile_service import ProfileService


# ----------------------------------------------------------------------
# Mock 基础设施
# ----------------------------------------------------------------------

def _make_orm_profile(
    user_id: str = "user_1",
    primary_domain: PrimaryDomain = PrimaryDomain.TECH,
) -> UserProfileORM:
    """构造一条内存 ORM 画像行（不落库）。"""
    return UserProfileORM(
        id="prof_001",
        user_id=user_id,
        primary_domain=primary_domain,
        sub_domain="AI编程",
        tone=CreatorTone.PROFESSIONAL,
        visual_style=VisualStyle.WARM,
        taboo_topics=["政治"],
        taboo_words=["绝对", "最好"],
        created_at=None,
        updated_at=None,
    )


def _mock_db_with_profile(orm_profile: UserProfileORM | None):
    """构造 mock session：execute(...).scalar_one_or_none() 返回给定画像。"""
    db = MagicMock()
    db.execute = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = orm_profile
    db.execute.return_value = result
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    return db


# ----------------------------------------------------------------------
# Schema 测试
# ----------------------------------------------------------------------

def test_to_prompt_context_full():
    profile = UserProfile(
        primary_domain=PrimaryDomain.TECH,
        sub_domain="AI编程",
        tone=CreatorTone.PROFESSIONAL,
        visual_style=VisualStyle.WARM,
        taboo_topics=["政治"],
        taboo_words=["绝对"],
    )
    text = profile.to_prompt_context()
    assert "【创作者画像】" in text
    assert "科技" in text and "AI编程" in text
    assert "调性: 专业" in text
    assert "视觉风格: 暖色调" in text
    assert "禁忌话题: 政治" in text
    assert "禁忌用词: 绝对" in text


def test_to_prompt_context_minimal():
    """画像只有必填项时，禁忌清单行消失（结尾写作要求句保留）。"""
    profile = UserProfile(primary_domain=PrimaryDomain.FOOD)
    text = profile.to_prompt_context()
    assert "美食" in text
    assert "禁忌话题:" not in text
    assert "禁忌用词:" not in text


def test_update_request_missing_domain_rejected():
    with pytest.raises(ValidationError):
        UpdateProfileRequest(primary_domain=None)  # type: ignore[arg-type]


def test_update_request_cleans_taboo_lists():
    req = UpdateProfileRequest(
        primary_domain=PrimaryDomain.TECH,
        taboo_topics=["  政治 ", "", "政治", "  "],
        taboo_words=["绝对", " 绝对 "],
    )
    assert req.taboo_topics == ["政治"]
    assert req.taboo_words == ["绝对"]


def test_update_request_invalid_domain_rejected():
    with pytest.raises(ValidationError):
        UpdateProfileRequest(primary_domain="nonexistent_domain")


# ----------------------------------------------------------------------
# ProfileService 测试
# ----------------------------------------------------------------------

def test_get_profile_not_found():
    db = _mock_db_with_profile(None)
    svc = ProfileService(db)
    profile = asyncio.run(svc.get_profile("user_1"))
    assert profile is None


def test_get_profile_found():
    db = _mock_db_with_profile(_make_orm_profile())
    svc = ProfileService(db)
    profile = asyncio.run(svc.get_profile("user_1"))
    assert profile is not None
    assert profile.primary_domain == PrimaryDomain.TECH
    assert profile.sub_domain == "AI编程"
    assert profile.taboo_words == ["绝对", "最好"]


def test_get_or_validate_raises_when_missing():
    db = _mock_db_with_profile(None)
    svc = ProfileService(db)
    with pytest.raises(ProfileValidationError) as exc_info:
        asyncio.run(svc.get_or_validate("user_1"))
    assert exc_info.value.reason == "profile_not_found"


def test_get_or_validate_returns_profile():
    db = _mock_db_with_profile(_make_orm_profile())
    svc = ProfileService(db)
    profile = asyncio.run(svc.get_or_validate("user_1"))
    assert profile.primary_domain == PrimaryDomain.TECH


def test_upsert_creates_when_absent():
    db = _mock_db_with_profile(None)
    svc = ProfileService(db)
    req = UpdateProfileRequest(
        primary_domain=PrimaryDomain.TECH,
        sub_domain="AI编程",
        taboo_words=["绝对"],
    )
    profile = asyncio.run(svc.upsert_profile("user_1", req))
    assert db.add.called  # insert 路径
    assert db.commit.awaited
    assert profile.primary_domain == PrimaryDomain.TECH
    assert profile.taboo_words == ["绝对"]


def test_upsert_updates_existing_no_duplicate_row():
    """已存在画像时走 update 路径，不重复 add 新行（1:1）。"""
    existing = _make_orm_profile()
    db = _mock_db_with_profile(existing)
    svc = ProfileService(db)
    req = UpdateProfileRequest(
        primary_domain=PrimaryDomain.FOOD,
        sub_domain=None,
        tone=CreatorTone.LIVELY,
    )
    profile = asyncio.run(svc.upsert_profile("user_1", req))
    assert not db.add.called  # update 路径不 add
    assert db.commit.awaited
    assert profile.primary_domain == PrimaryDomain.FOOD
    assert existing.primary_domain == PrimaryDomain.FOOD
    assert existing.tone == CreatorTone.LIVELY


# ----------------------------------------------------------------------
# Router 测试（轻量 app + 依赖覆盖，不起完整后端）
# ----------------------------------------------------------------------

def _make_client(db) -> TestClient:
    from app.api.deps import get_current_user
    from app.db.session import get_db

    app = FastAPI()
    app.include_router(profile_router)
    app.dependency_overrides[get_current_user] = lambda: "user_1"
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def test_router_get_returns_null_when_unset():
    db = _mock_db_with_profile(None)
    client = _make_client(db)
    resp = client.get("/api/profile")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"] is None


def test_router_get_returns_profile_when_set():
    db = _mock_db_with_profile(_make_orm_profile())
    client = _make_client(db)
    resp = client.get("/api/profile")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["primary_domain"] == "tech"
    assert body["data"]["sub_domain"] == "AI编程"


def test_router_put_missing_domain_returns_422():
    db = _mock_db_with_profile(None)
    client = _make_client(db)
    resp = client.put("/api/profile", json={"sub_domain": "AI编程"})
    assert resp.status_code == 422


def test_router_put_invalid_domain_returns_422():
    db = _mock_db_with_profile(None)
    client = _make_client(db)
    resp = client.put("/api/profile", json={"primary_domain": "not_a_domain"})
    assert resp.status_code == 422


def test_router_put_success():
    db = _mock_db_with_profile(None)
    client = _make_client(db)
    resp = client.put("/api/profile", json={
        "primary_domain": "tech",
        "sub_domain": "AI编程",
        "tone": "professional",
        "visual_style": "warm",
        "taboo_topics": ["政治"],
        "taboo_words": ["绝对"],
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["primary_domain"] == "tech"


def test_router_validate_ok():
    db = _mock_db_with_profile(_make_orm_profile())
    client = _make_client(db)
    resp = client.post("/api/profile/validate")
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is True
    assert body["reason"] is None
    assert body["profile"]["primary_domain"] == "tech"


def test_router_validate_not_found():
    db = _mock_db_with_profile(None)
    client = _make_client(db)
    resp = client.post("/api/profile/validate")
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is False
    assert body["reason"] == "profile_not_found"
    assert body["profile"] is None
