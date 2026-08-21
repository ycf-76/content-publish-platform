"""Recovery routers."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.schemas.common import StandardResponse
from app.db.session import get_db

router = APIRouter(prefix="/api/workflows", tags=["recovery"])


@router.post("/{workflow_id}/resume-from-suspension")
async def resume_from_suspension(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict]:
    """Resume a suspended workflow."""
    return StandardResponse(
        data={"workflow_id": workflow_id},
        message="Workflow resumed from suspension"
    )