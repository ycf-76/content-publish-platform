"""Config routers (optional)."""

from fastapi import APIRouter

from app.api.schemas.common import StandardResponse

router = APIRouter(prefix="/api/agents", tags=["config"])


@router.get("/configs")
async def list_agent_configs() -> StandardResponse[list[dict]]:
    """List all agent configurations."""
    return StandardResponse(data=[])


@router.put("/configs/{agent_id}")
async def update_agent_config(
    agent_id: str,
    config: dict,
) -> StandardResponse[dict]:
    """Update agent configuration."""
    return StandardResponse(data={}, message="Config updated")
