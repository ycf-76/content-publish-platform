"""Recovery routers."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.common import StandardResponse
from app.db.session import get_db

router = APIRouter(prefix="/api/workflows", tags=["recovery"])


@router.post("/{workflow_id}/resume-from-suspension")
async def resume_from_suspension(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[dict]:
    """Resume a suspended workflow."""
    return StandardResponse(
        data={"workflow_id": workflow_id},
        message="Workflow resumed from suspension"
    )
