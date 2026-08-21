"""User image asset API."""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.api.deps import get_current_user
from app.api.schemas.common import StandardResponse
from app.services.asset_library import MAX_UPLOAD_BYTES, delete_asset, list_assets, save_asset

router = APIRouter(prefix="/api/assets", tags=["assets"])


@router.post("")
async def upload_assets(
    files: list[UploadFile] = File(...),
    user_id: str = Depends(get_current_user),
) -> StandardResponse[list[dict]]:
    if not files:
        raise HTTPException(status_code=400, detail="请至少上传一张图片")
    if len(files) > 20:
        raise HTTPException(status_code=400, detail="单次最多上传 20 张图片")

    saved: list[dict] = []
    for file in files:
        data = await file.read()
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=400, detail=f"{file.filename} 不能超过 10MB")
        try:
            asset = await save_asset(
                user_id=user_id,
                filename=file.filename or "",
                content_type=file.content_type or "",
                data=data,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        saved.append(asset)

    return StandardResponse(data=saved, message=f"已上传 {len(saved)} 张图片")


@router.get("")
async def get_assets(
    user_id: str = Depends(get_current_user),
) -> StandardResponse[list[dict]]:
    return StandardResponse(data=await list_assets(user_id))


@router.delete("/{asset_id}")
async def remove_asset(
    asset_id: str,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict]:
    deleted = await delete_asset(user_id, asset_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="图片资产不存在")
    return StandardResponse(data={"deleted": asset_id})
