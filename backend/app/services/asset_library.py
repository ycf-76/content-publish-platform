"""User image asset library.

Phase 4 backend foundation:
- Validate uploaded image content with Pillow.
- Strip EXIF metadata.
- Save original and thumbnail files.
- Persist asset metadata per user.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

from app.db.models import ImageAsset, generate_ulid
from app.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
THUMBNAIL_MAX_SIZE = (400, 400)

_BASE_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"


def _ext_for_format(image_format: str) -> str:
    return {
        "JPEG": ".jpg",
        "PNG": ".png",
        "WEBP": ".webp",
        "GIF": ".gif",
    }.get((image_format or "").upper(), ".png")


def _process_image(content_type: str, data: bytes) -> tuple[bytes, str, int, int]:
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise ValueError("不支持的图片类型")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("图片不能超过 10MB")

    try:
        image = Image.open(io.BytesIO(data))
        image = ImageOps.exif_transpose(image)
        # Explicitly drop EXIF before re-encoding; do not rely on save() alone.
        image.info.pop("exif", None)
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGBA")

        output = io.BytesIO()
        save_kwargs: dict[str, Any] = {}
        if image.format == "JPEG":
            save_kwargs["quality"] = 90
        elif image.format == "WEBP":
            save_kwargs["quality"] = 88
        image.save(output, format=image.format or "PNG", **save_kwargs)
        processed = output.getvalue()
        return processed, image.format or "PNG", image.width, image.height
    except Exception as exc:
        raise ValueError(f"图片内容无效: {exc}") from exc


def _make_thumbnail(data: bytes, image_format: str) -> bytes:
    image = Image.open(io.BytesIO(data))
    image.thumbnail(THUMBNAIL_MAX_SIZE)
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA")
    output = io.BytesIO()
    save_kwargs: dict[str, Any] = {}
    if image_format == "JPEG":
        save_kwargs["quality"] = 82
    elif image_format == "WEBP":
        save_kwargs["quality"] = 82
    image.save(output, format=image_format or "PNG", **save_kwargs)
    return output.getvalue()


def _asset_to_dict(asset: ImageAsset) -> dict[str, Any]:
    return {
        "asset_id": asset.id,
        "filename": asset.filename,
        "content_type": asset.content_type,
        "file_size": asset.file_size,
        "width": asset.width,
        "height": asset.height,
        "original_url": asset.original_url,
        "thumbnail_url": asset.thumbnail_url,
        "source": asset.source,
    }


def _path_from_url(url: str) -> Path | None:
    if not url or not url.startswith("/uploads/"):
        return None
    return _BASE_DIR / url.removeprefix("/uploads/")


async def save_asset(
    user_id: str,
    filename: str,
    content_type: str,
    data: bytes,
) -> dict[str, Any]:
    """Validate, process, store, and persist one user image asset."""
    processed, image_format, width, height = _process_image(content_type, data)
    thumbnail = _make_thumbnail(processed, image_format)
    asset_id = generate_ulid()
    ext = _ext_for_format(image_format)
    user_dir = _BASE_DIR / "assets" / user_id
    user_dir.mkdir(parents=True, exist_ok=True)

    original_name = f"{asset_id}{ext}"
    thumbnail_name = f"{asset_id}_thumb{ext}"
    (user_dir / original_name).write_bytes(processed)
    (user_dir / thumbnail_name).write_bytes(thumbnail)

    async with AsyncSessionLocal() as session:
        asset = ImageAsset(
            id=asset_id,
            user_id=user_id,
            filename=filename,
            content_type=content_type,
            file_size=len(processed),
            width=width,
            height=height,
            original_url=f"/uploads/assets/{user_id}/{original_name}",
            thumbnail_url=f"/uploads/assets/{user_id}/{thumbnail_name}",
            source="upload",
        )
        session.add(asset)
        await session.commit()
        await session.refresh(asset)
        return _asset_to_dict(asset)


async def list_assets(user_id: str) -> list[dict[str, Any]]:
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        stmt = (
            select(ImageAsset)
            .where(ImageAsset.user_id == user_id)
            .order_by(ImageAsset.created_at.desc())
        )
        result = await session.execute(stmt)
        return [_asset_to_dict(asset) for asset in result.scalars().all()]


async def delete_asset(user_id: str, asset_id: str) -> bool:
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        stmt = select(ImageAsset).where(
            ImageAsset.user_id == user_id,
            ImageAsset.id == asset_id,
        )
        result = await session.execute(stmt)
        asset = result.scalar_one_or_none()
        if asset is None:
            return False
        original_path = _path_from_url(asset.original_url)
        thumbnail_path = _path_from_url(asset.thumbnail_url)
        await session.delete(asset)
        await session.commit()

    for path in (original_path, thumbnail_path):
        if path is not None:
            path.unlink(missing_ok=True)
    return True
