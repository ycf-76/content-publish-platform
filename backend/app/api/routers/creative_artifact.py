"""CreativeArtifact API：统一创作对象的读写与构建。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.api.schemas.common import StandardResponse
from app.services.creative_artifact import (
    CreativeArtifact,
    build_artifact,
    build_storyboard,
    delete_artifact,
    list_artifacts,
    load_artifact,
    save_artifact,
    to_card_draft,
)

router = APIRouter(prefix="/api/creative-artifacts", tags=["creative-artifacts"])


class BuildRequest(BaseModel):
    artifact_id: str = ""
    card_draft: dict[str, Any] = Field(default_factory=dict)
    brief: dict[str, Any] = Field(default_factory=dict)
    analysis: dict[str, Any] = Field(default_factory=dict)
    source: dict[str, Any] = Field(default_factory=dict)
    persist: bool = True


class StoryboardRequest(BaseModel):
    card_draft: dict[str, Any] = Field(default_factory=dict)


@router.get("")
async def list_items(
    limit: int = 50,
    _user_id: str = Depends(get_current_user),
) -> StandardResponse[list[dict[str, Any]]]:
    return StandardResponse(data=list_artifacts(limit=limit))


@router.post("/build")
async def build(
    payload: BuildRequest,
    _user_id: str = Depends(get_current_user),
) -> StandardResponse[dict[str, Any]]:
    """从 card_draft / brief / analysis 构建统一创作对象。"""
    artifact = build_artifact(
        artifact_id=payload.artifact_id,
        card_draft=payload.card_draft,
        brief=payload.brief,
        analysis=payload.analysis,
        source=payload.source,
    )
    if payload.persist:
        save_artifact(artifact)
    return StandardResponse(data=artifact.model_dump())


@router.post("/storyboard")
async def storyboard(
    payload: StoryboardRequest,
    _user_id: str = Depends(get_current_user),
) -> StandardResponse[list[dict[str, Any]]]:
    """只做分镜提升，不持久化，便于前端预览。"""
    draft = payload.card_draft or {}
    pages = build_storyboard(
        draft.get("pages") or [],
        template_id=draft.get("suggested_template") or "",
    )
    return StandardResponse(data=[p.model_dump() for p in pages])


@router.get("/{artifact_id}")
async def get_item(
    artifact_id: str,
    _user_id: str = Depends(get_current_user),
) -> StandardResponse[dict[str, Any]]:
    artifact = load_artifact(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    return StandardResponse(data=artifact.model_dump())


@router.get("/{artifact_id}/card-draft")
async def get_card_draft(
    artifact_id: str,
    _user_id: str = Depends(get_current_user),
) -> StandardResponse[dict[str, Any]]:
    artifact = load_artifact(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    return StandardResponse(data=to_card_draft(artifact))


@router.put("/{artifact_id}")
async def put_item(
    artifact_id: str,
    artifact: CreativeArtifact,
    _user_id: str = Depends(get_current_user),
) -> StandardResponse[dict[str, Any]]:
    artifact.artifact_id = artifact_id
    saved = save_artifact(artifact)
    return StandardResponse(data=saved.model_dump())


@router.patch("/{artifact_id}")
async def patch_item(
    artifact_id: str,
    updates: dict[str, Any],
    _user_id: str = Depends(get_current_user),
) -> StandardResponse[dict[str, Any]]:
    current = load_artifact(artifact_id)
    if current is None:
        current = CreativeArtifact(artifact_id=artifact_id)

    data = current.model_dump()
    for key, value in updates.items():
        if key in ("artifact_id", "version"):
            continue
        if isinstance(value, dict) and isinstance(data.get(key), dict):
            data[key].update(value)
        else:
            data[key] = value

    updated = CreativeArtifact(**data)
    saved = save_artifact(updated)
    return StandardResponse(data=saved.model_dump())


@router.delete("/{artifact_id}")
async def delete_item(
    artifact_id: str,
    _user_id: str = Depends(get_current_user),
) -> StandardResponse[dict[str, Any]]:
    ok = delete_artifact(artifact_id)
    if not ok:
        raise HTTPException(status_code=404, detail="artifact not found")
    return StandardResponse(data={"deleted": True})