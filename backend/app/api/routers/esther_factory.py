"""Esther Factory API router."""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response

from app.api.deps import get_current_user
from app.api.schemas.common import StandardResponse
from app.api.schemas.esther_factory import (
    ProduceRequest,
    ProduceResponse,
    RenderRequest,
    RenderResponse,
    TemplateInfo,
    SceneInfo,
    SchemaResponse,
    MetaResponse,
    ImportRequest,
    ImportResponse,
    ExportResponse,
    BrandConfig,
)
from app.services.esther_factory import factory

router = APIRouter(prefix="/api/esther-factory", tags=["esther-factory"])


@router.get("/scenes")
async def list_scenes(
    _user_id: str = Depends(get_current_user),
) -> StandardResponse[list[SceneInfo]]:
    scenes = factory.list_scenes()
    return StandardResponse(data=[SceneInfo(**s) for s in scenes])


@router.get("/templates")
async def list_templates(
    user_id: str = Depends(get_current_user),
) -> StandardResponse[list[TemplateInfo]]:
    templates = await factory.list_templates(user_id)
    return StandardResponse(data=[TemplateInfo(**t) for t in templates])


@router.get("/templates/{template_id}/schema")
async def get_template_schema(
    template_id: str,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[SchemaResponse]:
    schema = await factory.get_schema(user_id, template_id)
    if not schema:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")
    return StandardResponse(data=SchemaResponse(template_schema=schema))


@router.get("/templates/{template_id}/meta")
async def get_template_meta(
    template_id: str,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[MetaResponse]:
    meta = await factory.get_meta(user_id, template_id)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")
    return StandardResponse(data=MetaResponse(template_meta=meta))


@router.post("/produce")
async def produce_template(
    request: ProduceRequest,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[ProduceResponse]:
    result = await factory.produce(
        scene=request.scene,
        description=request.description,
        template_id=request.template_id,
        user_id=user_id,
        brand_overrides=request.brand_overrides,
        extra_instructions=request.extra_instructions,
    )
    return StandardResponse(data=ProduceResponse(**result))


@router.post("/render")
async def render_template(
    request: RenderRequest,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[RenderResponse]:
    try:
        html = await factory.render(
            template_id=request.template_id,
            data=request.data,
            brand=request.brand,
            user_id=user_id,
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    return StandardResponse(data=RenderResponse(html=html))


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: str,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict]:
    deleted = await factory._delete_template_db(user_id, template_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")
    return StandardResponse(data={"deleted": template_id})


@router.post("/import")
async def import_template(
    request: ImportRequest,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[ImportResponse]:
    result = await factory.import_template(
        user_id=user_id,
        template_id=request.template_id,
        schema_json=request.template_schema,
        template_html=request.template_html,
        meta_json=request.meta,
        overwrite=request.overwrite,
    )
    return StandardResponse(data=ImportResponse(**result))


@router.get("/templates/{template_id}/export")
async def export_template(
    template_id: str,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[ExportResponse]:
    result = await factory.export_template(user_id, template_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")
    return StandardResponse(data=ExportResponse(
        template_id=result["template_id"],
        template_schema=result["schema"],
        template_html=result["template_html"],
        meta=result["meta"],
    ))


@router.get("/brand-config")
async def get_brand_config(
    user_id: str = Depends(get_current_user),
) -> StandardResponse[BrandConfig]:
    config = await factory.get_brand_config(user_id)
    return StandardResponse(data=BrandConfig(**config))


@router.put("/brand-config")
async def save_brand_config(
    request: BrandConfig,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[BrandConfig]:
    config = await factory.save_brand_config(user_id, request.model_dump())
    return StandardResponse(data=BrandConfig(**config))


@router.post("/brand-config/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict]:
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="只支持图片文件")

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="头像文件不能超过 5MB")

    avatar_url = await factory.save_avatar(user_id, content, file.content_type)
    return StandardResponse(data={"avatar_url": avatar_url})


@router.get("/brand-config/avatar/{user_id}")
async def get_avatar(
    user_id: str,
) -> Response:
    result = await factory.get_avatar(user_id)
    if not result:
        raise HTTPException(status_code=404, detail="Avatar not found")
    data, content_type = result
    return Response(content=data, media_type=content_type)