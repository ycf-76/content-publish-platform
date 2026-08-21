"""Esther Factory API schemas."""

from typing import Any

from pydantic import BaseModel, Field


class BrandConfig(BaseModel):
    brand_name: str = Field(default="", description="品牌/IP 名称（可选，留空使用默认样式）")
    avatar_url: str = Field(default="", description="头像 URL（可选，通过上传接口设置）")
    primary: str = Field(default="#2B7FD8", description="主色")
    accent: str = Field(default="#F4D758", description="强调色")
    spot: str = Field(default="#E84A5F", description="点缀色")


class ProduceRequest(BaseModel):
    scene: str = Field(..., description="Scene: cards/wechat/tutorial/landing/app")
    description: str = Field(..., description="What kind of template you want")
    template_id: str = Field(..., description="Unique template ID to save as")
    brand_overrides: dict[str, str] | None = Field(
        default=None, description='Brand color overrides'
    )
    extra_instructions: str = Field(default="", description="Extra instructions for LLM")


class ProduceResponse(BaseModel):
    success: bool
    template_id: str
    issues: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None


class RenderRequest(BaseModel):
    template_id: str
    data: dict[str, Any] = Field(default_factory=dict)
    brand: dict[str, str] | None = Field(default=None, description="Brand color overrides")


class RenderResponse(BaseModel):
    html: str


class TemplateInfo(BaseModel):
    id: str
    name: str
    scene: str
    fields_count: int = 0


class SceneInfo(BaseModel):
    id: str
    name: str


class SchemaResponse(BaseModel):
    template_schema: dict[str, Any]


class MetaResponse(BaseModel):
    template_meta: dict[str, Any]


class ImportRequest(BaseModel):
    """Import a template package into the library."""

    template_id: str = Field(..., description="Unique template ID")
    template_schema: dict[str, Any] = Field(..., description="Template schema (JSON)")
    template_html: str = Field(..., description="Jinja2 template HTML")
    meta: dict[str, Any] = Field(default_factory=dict, description="Template metadata")
    overwrite: bool = Field(default=False, description="Overwrite if template_id already exists")


class ImportResponse(BaseModel):
    success: bool
    template_id: str
    issues: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None


class ExportResponse(BaseModel):
    template_id: str
    template_schema: dict[str, Any]
    template_html: str
    meta: dict[str, Any]