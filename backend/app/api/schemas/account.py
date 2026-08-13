"""Account API schemas."""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Login request."""

    email: str = Field(..., description="User email")
    password: str = Field(..., description="User password")


class AccountResponse(BaseModel):
    """Account response."""

    account_id: str
    xhs_user_id: str
    xhs_nickname: str
    xhs_avatar_url: str = ""
    status: str
    login_method: str
