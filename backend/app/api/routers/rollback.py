"""Rollback/suggestion routers."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.schemas.common import StandardResponse
from app.api.schemas.suggestion import SuggestionConfirmRequest
from app.db.session import get_db

router = APIRouter(prefix="/api/workflows", tags=["rollback"])


@router.post("/{workflow_id}/suggestions/{suggestion_id}/confirm")
async def confirm_suggestion(
    workflow_id: str,
    suggestion_id: str,
    request: SuggestionConfirmRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict]:
    """Confirm a supervisor suggestion."""
    return StandardResponse(
        data={"suggestion_id": suggestion_id},
        message="Suggestion confirmed"
    )


@router.post("/{workflow_id}/suggestions/{suggestion_id}/reject")
async def reject_suggestion(
    workflow_id: str,
    suggestion_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict]:
    """Reject a supervisor suggestion."""
    return StandardResponse(
        data={"suggestion_id": suggestion_id},
        message="Suggestion rejected"
    )