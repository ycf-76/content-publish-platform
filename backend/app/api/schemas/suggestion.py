"""Suggestion API schemas."""

from pydantic import BaseModel, Field


class SuggestionConfirmRequest(BaseModel):
    """Request to confirm or reject a suggestion."""

    decision: str = Field(..., description="confirm/reject")
