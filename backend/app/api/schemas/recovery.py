"""Recovery API schemas."""

from pydantic import BaseModel, Field


class ManualResumeRequest(BaseModel):
    """Request to manually resume a suspended workflow."""

    workflow_id: str = Field(..., description="Workflow ID")
