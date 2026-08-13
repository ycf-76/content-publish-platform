"""Common API schemas."""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class StandardResponse(BaseModel, Generic[T]):
    """Standard API response wrapper."""

    success: bool = True
    data: T | None = None
    message: str = ""


class ErrorResponse(BaseModel):
    """Error response matching protocol Ch.9."""

    code: str  # Enum from protocol Ch.9
    message: str
    detail: dict[str, Any] = Field(default_factory=dict)


class PaginationParams(BaseModel):
    """Pagination parameters."""

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
