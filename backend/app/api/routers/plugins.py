"""
Plugin API Router
插件系统 RESTful API 端点

Endpoints:
- GET    /api/plugins              - 获取插件列表
- POST   /api/plugins              - 创建插件（管理员）
- GET    /api/plugins/{plugin_id}  - 获取插件详情
- PUT    /api/plugins/{plugin_id}  - 更新插件（管理员）
- DELETE /api/plugins/{plugin_id}  - 删除插件（管理员）
- POST   /api/plugins/{plugin_id}/install     - 安装插件
- DELETE /api/plugins/{plugin_id}/uninstall   - 卸载插件
- POST   /api/plugins/{plugin_id}/enable      - 启用插件
- POST   /api/plugins/{plugin_id}/disable     - 禁用插件
- GET    /api/plugins/{plugin_id}/config      - 获取配置
- PUT    /api/plugins/{plugin_id}/config      - 更新配置
- GET    /api/plugins/{plugin_id}/versions    - 版本列表
- POST   /api/plugins/{plugin_id}/reviews     - 创建评价
- GET    /api/plugins/marketplace              - 插件市场
- GET    /api/plugins/my                       - 我的插件
- POST   /api/plugins/bulk                     - 批量操作
- POST   /api/plugins/upload                   - 上传插件包（开发者）
"""

import sys
import os
import json
import zipfile
import tempfile
import shutil
import logging
from datetime import datetime
from typing import List, Optional
from pathlib import Path as FilePath

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status, UploadFile, File, Form
from fastapi import Path as FastPath
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, "D:/My_Project/多智能体小红书发布平台/backend")

from sqlalchemy import select

from app.db.session import get_db
from app.db.plugin_models import Plugin
from app.services.plugin_service import PluginService
from app.api.deps import get_current_user
from app.api.schemas.plugin_schemas import (
    # Request/Response models
    PluginCreate,
    PluginUpdate,
    PluginResponse,
    PluginListResponse,
    PluginSearchQuery,
    PluginInstallRequest,
    PluginActionResponse,
    PluginConfigRequest,
    PluginConfigResponse,
    PluginReviewCreate,
    PluginReviewResponse,
    PluginVersionCreate,
    PluginVersionResponse,
    MarketplaceQuery,
    BulkActionRequest,
    BulkActionResponse,
)


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/plugins",
    tags=["plugins"],
    responses={404: {"description": "Plugin not found"}},
)


# ==================== 依赖注入 ====================

def get_plugin_service(db: AsyncSession = Depends(get_db)) -> PluginService:
    """获取插件服务实例"""
    return PluginService(db)


get_current_user_id = get_current_user


# ==================== 健康检查端点（必须在 /{plugin_id} 之前） ====================

@router.get(
    "/health",
    summary="Health check",
    description="Check plugin system health status",
)
async def health_check(service: PluginService = Depends(get_plugin_service)):
    """插件系统健康检查"""
    try:
        # 统计插件数量
        from sqlalchemy import func
        
        count_result = await service.session.execute(
            select(func.count()).select_from(Plugin)
        )
        total_plugins = count_result.scalar()
        
        active_count_result = await service.session.execute(
            select(func.count())
            .select_from(Plugin)
            .where(Plugin.status == "ACTIVE")
        )
        active_plugins = active_count_result.scalar()
        
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "statistics": {
                "total_plugins": total_plugins,
                "active_plugins": active_plugins,
                "system_status": "operational",
            }
        }
    except Exception as e:
        return {
            "status": "error",
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e),
            "statistics": {
                "total_plugins": 0,
                "active_plugins": 0,
                "system_status": "error",
            }
        }


# ==================== CRUD 端点 ====================

@router.get(
    "",
    response_model=PluginListResponse,
    summary="Get plugin list",
    description="Retrieve paginated plugin list with search and filtering",
)
async def list_plugins(
    q: Optional[str] = Query(None, description="Search keyword"),
    category: Optional[str] = Query(None, description="Filter by category"),
    status: Optional[str] = Query(None, description="Filter by status"),
    pricing_model: Optional[str] = Query(None, description="Filter by pricing model"),
    author: Optional[str] = Query(None, description="Filter by author name"),
    sort_by: str = Query("created_at", description="Sort field"),
    sort_order: str = Query("desc", description="Sort order (asc/desc)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    service: PluginService = Depends(get_plugin_service),
):
    """获取插件列表（支持搜索、过滤、排序、分页）"""
    query = PluginSearchQuery(
        q=q,
        category=category,
        status=status,
        pricing_model=pricing_model,
        author=author,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )
    
    plugins, total = await service.list_plugins(query)
    
    try:
        items = [PluginResponse.model_validate(p) for p in plugins]
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Serialization error: {e}")
    
    return PluginListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=items,
    )


@router.post(
    "",
    response_model=PluginResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create new plugin",
    description="Register a new plugin (admin only)",
)
async def create_plugin(
    data: PluginCreate,
    service: PluginService = Depends(get_plugin_service),
):
    """创建新插件（管理员权限）"""
    try:
        plugin = await service.create_plugin(data)
        return PluginResponse.model_validate(plugin)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create plugin: {str(e)}",
        )


# ==================== 固定路径端点（必须在 /{plugin_id} 之前） ====================

@router.get(
    "/my",
    response_model=List[dict],
    summary="My plugins",
    description="Get list of plugins installed by current user",
)
async def get_my_plugins(
    only_enabled: bool = Query(False, description="Show enabled plugins only"),
    user_id: str = Depends(get_current_user_id),
    service: PluginService = Depends(get_plugin_service),
):
    """获取当前用户安装的插件列表"""
    plugins = await service.get_user_plugins(user_id, only_enabled=only_enabled)
    return plugins


@router.post(
    "/bulk",
    response_model=BulkActionResponse,
    summary="Bulk action",
    description="Perform bulk operations on multiple plugins",
)
async def bulk_action(
    data: BulkActionRequest,
    user_id: str = Depends(get_current_user_id),
    service: PluginService = Depends(get_plugin_service),
):
    """批量操作多个插件"""
    if len(data.plugin_ids) > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 50 plugins per batch operation",
        )
    
    valid_actions = ["enable", "disable", "uninstall"]
    if data.action not in valid_actions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid action. Must be one of: {', '.join(valid_actions)}",
        )
    
    result = await service.bulk_action(user_id, data.plugin_ids, data.action)

    return BulkActionResponse(**result)


@router.post(
    "/upload",
    summary="Upload and install plugin package",
    description="Upload a plugin package (.zip), validate, extract to third_party dir, and sync to DB",
    response_model=dict,
)
async def upload_plugin(
    plugin_package: UploadFile = File(..., description="Plugin package (ZIP format)"),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """上传并安装第三方插件包

    流程：
    1. 验证zip包格式和plugin.json
    2. 安全检查（路径穿越、文件大小等）
    3. 解压到 plugins/third_party/{plugin_id}/
    4. 同步元数据到数据库
    5. 自动为当前用户安装该插件
    """
    logger.info(f"[upload_plugin] Received upload request: filename={plugin_package.filename}, content_type={plugin_package.content_type}")
    try:
        content = await plugin_package.read()
        logger.info(f"[upload_plugin] Read {len(content)} bytes from upload")
    except Exception as read_err:
        logger.error(f"[upload_plugin] Failed to read upload content: {read_err}")
        raise HTTPException(status_code=500, detail=f"Failed to read upload: {read_err}")

    if not plugin_package.filename or not plugin_package.filename.endswith('.zip'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .zip plugin packages are accepted",
        )

    THIRD_PARTY_BASE = Path(__file__).parent.parent.parent.parent / "plugins" / "third_party"
    tmp_dir = None
    try:
        tmp_dir = tempfile.mkdtemp(prefix="plugin_upload_")
        zip_path = os.path.join(tmp_dir, plugin_package.filename)

        if len(content) > 50 * 1024 * 1024:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Plugin package too large (max 50MB)",
            )

        with open(zip_path, "wb") as f:
            f.write(content)

        with zipfile.ZipFile(zip_path, 'r') as zf:
            manifest_path = None
            for name in zf.namelist():
                if name.endswith('plugin.json'):
                    manifest_path = name
                    break

            if not manifest_path:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="plugin.json not found in package",
                )

            for member in zf.namelist():
                member_path = os.path.normpath(member)
                if member_path.startswith('..') or os.path.isabs(member_path):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Unsafe path in zip: {member}",
                    )

            with zf.open(manifest_path) as mf:
                manifest = json.load(mf)

        required_fields = ['id', 'name', 'version', 'category']
        for field in required_fields:
            if field not in manifest:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Missing required field: {field}",
                )

        plugin_id = manifest['id']
        if not plugin_id or not plugin_id.replace('-', '').replace('_', '').isalnum():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid plugin id: {plugin_id}",
            )

        BUILTIN_BASE = Path(__file__).parent.parent.parent.parent / "plugins" / "builtin"
        if (BUILTIN_BASE / plugin_id).exists():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Plugin '{plugin_id}' is a builtin plugin and cannot be replaced",
            )

        target_dir = THIRD_PARTY_BASE / plugin_id
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)

        THIRD_PARTY_BASE.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(target_dir)

        plugin_json_in_target = target_dir / "plugin.json"
        if not plugin_json_in_target.exists():
            for root, dirs, files in os.walk(target_dir):
                if "plugin.json" in files:
                    sub_dir = Path(root)
                    for item in sub_dir.iterdir():
                        dest = target_dir / item.name
                        if dest.exists():
                            if dest.is_dir():
                                shutil.rmtree(dest)
                            else:
                                dest.unlink()
                        shutil.move(str(item), str(dest))
                    for d in dirs:
                        empty_sub = target_dir / d
                        if empty_sub.is_dir() and not any(empty_sub.iterdir()):
                            shutil.rmtree(empty_sub, ignore_errors=True)
                    break

        from app.core.sync_builtin_plugins import sync_single_third_party_plugin
        sync_result = await sync_single_third_party_plugin(plugin_id)

        if sync_result["synced"] == 0 and sync_result["skipped"] == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Plugin extracted but failed to sync to database",
            )

        from app.services.plugin_service import PluginService
        service = PluginService(db)
        try:
            install_result = await service.install_plugin(user_id, plugin_id)
            logger.info(f"[upload_plugin] Auto-install result: {install_result}")
        except ValueError as install_err:
            if "already installed" in str(install_err):
                logger.info(f"[upload_plugin] Plugin already installed for user, skipping auto-install")
            else:
                logger.warning(f"[upload_plugin] Auto-install failed: {install_err}")
        except Exception as install_err:
            logger.warning(f"[upload_plugin] Auto-install after upload failed (non-fatal): {install_err}")

        return {
            "success": True,
            "message": "Plugin installed successfully",
            "plugin_id": plugin_id,
            "name": manifest['name'],
            "version": manifest['version'],
            "category": manifest['category'],
            "install_path": str(target_dir),
            "sync_result": sync_result,
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.error(f"[upload_plugin] Upload failed: {e}\n{tb}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Upload failed: {str(e)}",
        )
    finally:
        if tmp_dir and os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)


@router.get(
    "/{plugin_id}",
    response_model=PluginResponse,
    summary="Get plugin details",
    description="Get detailed information about a specific plugin",
)
async def get_plugin(
    plugin_id: str = FastPath(..., description="Plugin ID"),
    service: PluginService = Depends(get_plugin_service),
):
    """获取单个插件详情"""
    plugin = await service.get_plugin(plugin_id)
    
    if not plugin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plugin '{plugin_id}' not found",
        )
    
    return PluginResponse.model_validate(plugin)


@router.put(
    "/{plugin_id}",
    response_model=PluginResponse,
    summary="Update plugin",
    description="Update plugin information (admin only)",
)
async def update_plugin(
    plugin_id: str = FastPath(..., description="Plugin ID"),
    data: PluginUpdate = None,
    service: PluginService = Depends(get_plugin_service),
):
    """更新插件信息（管理员权限）"""
    if not data or not data.model_dump(exclude_unset=True):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No update data provided",
        )

    try:
        plugin = await service.update_plugin(plugin_id, data)
        return PluginResponse.model_validate(plugin)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update plugin: {str(e)}",
        )


@router.delete(
    "/{plugin_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete plugin",
    description="Delete a plugin and all related data (admin only)",
)
async def delete_plugin(
    plugin_id: str = FastPath(..., description="Plugin ID"),
    service: PluginService = Depends(get_plugin_service),
):
    """删除插件（管理员权限）"""
    try:
        await service.delete_plugin(plugin_id)
    except ValueError as e:
        if "built-in" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(e),
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e),
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete plugin: {str(e)}",
        )


# ==================== 安装管理端点 ====================

@router.post(
    "/{plugin_id}/install",
    response_model=PluginActionResponse,
    summary="Install plugin",
    description="Install a plugin for the current user",
)
async def install_plugin(
    plugin_id: str = FastPath(..., description="Plugin ID"),
    request: Optional[PluginInstallRequest] = None,
    user_id: str = Depends(get_current_user_id),
    service: PluginService = Depends(get_plugin_service),
):
    """为当前用户安装插件"""
    try:
        result = await service.install_plugin(user_id, plugin_id, request)
        
        return PluginActionResponse(
            success=result["success"],
            message=result["message"],
            action=result["action"],
            plugin_id=result["plugin_id"],
            timestamp=datetime.utcnow(),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Installation failed: {str(e)}",
        )


@router.delete(
    "/{plugin_id}/uninstall",
    response_model=PluginActionResponse,
    summary="Uninstall plugin",
    description="Uninstall a plugin for the current user",
)
async def uninstall_plugin(
    plugin_id: str = FastPath(..., description="Plugin ID"),
    user_id: str = Depends(get_current_user_id),
    service: PluginService = Depends(get_plugin_service),
):
    """卸载用户的插件（第三方插件会同时删除其文件目录）"""
    try:
        result = await service.uninstall_plugin(user_id, plugin_id)

        plugin_info = await service.get_plugin(plugin_id)
        if plugin_info and not getattr(plugin_info, 'is_builtin', True):
            tp_dir = Path(__file__).parent.parent.parent.parent / "plugins" / "third_party" / plugin_id
            if tp_dir.exists():
                shutil.rmtree(tp_dir, ignore_errors=True)
                logger.info(f"Removed third-party plugin directory: {tp_dir}")

        return PluginActionResponse(
            success=result["success"],
            message=result["message"],
            action=result["action"],
            plugin_id=result["plugin_id"],
            timestamp=datetime.utcnow(),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Uninstallation failed: {str(e)}",
        )


@router.post(
    "/{plugin_id}/enable",
    response_model=PluginActionResponse,
    summary="Enable plugin",
    description="Enable an installed plugin",
)
async def enable_plugin(
    plugin_id: str = FastPath(..., description="Plugin ID"),
    user_id: str = Depends(get_current_user_id),
    service: PluginService = Depends(get_plugin_service),
):
    """启用已安装的插件"""
    try:
        result = await service.enable_plugin(user_id, plugin_id)
        
        return PluginActionResponse(
            success=result["success"],
            message=result["message"],
            action=result["action"],
            plugin_id=result["plugin_id"],
            timestamp=datetime.utcnow(),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to enable plugin: {str(e)}",
        )


@router.post(
    "/{plugin_id}/disable",
    response_model=PluginActionResponse,
    summary="Disable plugin",
    description="Disable an installed plugin",
)
async def disable_plugin(
    plugin_id: str = FastPath(..., description="Plugin ID"),
    user_id: str = Depends(get_current_user_id),
    service: PluginService = Depends(get_plugin_service),
):
    """禁用已安装的插件"""
    try:
        result = await service.disable_plugin(user_id, plugin_id)
        
        return PluginActionResponse(
            success=result["success"],
            message=result["message"],
            action=result["action"],
            plugin_id=result["plugin_id"],
            timestamp=datetime.utcnow(),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to disable plugin: {str(e)}",
        )


# ==================== 配置管理端点 ====================

@router.get(
    "/{plugin_id}/config",
    response_model=PluginConfigResponse,
    summary="Get plugin config",
    description="Get current user's configuration for a plugin",
)
async def get_plugin_config(
    plugin_id: str = FastPath(..., description="Plugin ID"),
    user_id: str = Depends(get_current_user_id),
    service: PluginService = Depends(get_plugin_service),
):
    """获取用户的插件配置"""
    config = await service._get_user_config(user_id, plugin_id)
    
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No configuration found for plugin '{plugin_id}'",
        )
    
    return PluginConfigResponse.model_validate(config)


@router.put(
    "/{plugin_id}/config",
    response_model=PluginConfigResponse,
    summary="Update plugin config",
    description="Update current user's configuration for a plugin",
)
async def update_plugin_config(
    plugin_id: str = FastPath(..., description="Plugin ID"),
    user_id: str = Depends(get_current_user_id),
    data: PluginConfigRequest = Body(...),
    service: PluginService = Depends(get_plugin_service),
):
    """更新用户的插件配置"""
    try:
        config = await service.update_plugin_config(user_id, plugin_id, data)
        return PluginConfigResponse.model_validate(config)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update config: {str(e)}",
        )


# ==================== 版本管理端点 ====================

@router.get(
    "/{plugin_id}/versions",
    response_model=List[PluginVersionResponse],
    summary="List plugin versions",
    description="Get all available versions for a plugin",
)
async def list_plugin_versions(
    plugin_id: str = FastPath(..., description="Plugin ID"),
    include_deprecated: bool = Query(False, description="Include deprecated versions"),
    service: PluginService = Depends(get_plugin_service),
):
    """获取插件的版本列表"""
    # 先检查插件是否存在
    plugin = await service.get_plugin(plugin_id)
    if not plugin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plugin '{plugin_id}' not found",
        )
    
    versions = await service.list_versions(plugin_id, include_deprecated)
    
    return [PluginVersionResponse.model_validate(v) for v in versions]


# ==================== 评价系统端点 ====================

@router.post(
    "/{plugin_id}/reviews",
    response_model=PluginReviewResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create review",
    description="Submit a review/rating for a plugin",
)
async def create_review(
    plugin_id: str = FastPath(..., description="Plugin ID"),
    user_id: str = Depends(get_current_user_id),
    data: PluginReviewCreate = Body(...),
    service: PluginService = Depends(get_plugin_service),
):
    """创建插件评价"""
    try:
        review = await service.create_review(user_id, plugin_id, data)
        return PluginReviewResponse.model_validate(review)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create review: {str(e)}",
        )


@router.get(
    "/{plugin_id}/reviews",
    response_model=dict,
    summary="Get plugin reviews",
    description="Get paginated reviews for a plugin with sorting options",
)
async def get_plugin_reviews(
    plugin_id: str = FastPath(..., description="Plugin ID"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=50, description="Items per page"),
    sort_by: str = Query("newest", description="Sort order: newest/oldest/rating_high/rating_low/helpful"),
    rating_filter: Optional[int] = Query(None, ge=1, le=5, description="Filter by star rating"),
    service: PluginService = Depends(get_plugin_service),
):
    """
    获取插件评价列表

    支持分页、排序和筛选：
    - sort_by: newest(最新)/oldest(最早)/rating_high(高评分)/rating_low(低评分)/helpful(最有用)
    - rating_filter: 按星级筛选（1-5星）
    """
    try:
        reviews, total, avg_rating = await service.get_plugin_reviews(
            plugin_id=plugin_id,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            rating_filter=rating_filter,
        )

        return {
            "success": True,
            "data": {
                "reviews": [PluginReviewResponse.model_validate(r) for r in reviews],
                "pagination": {
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": (total + page_size - 1) // page_size,
                },
                "summary": {
                    "avg_rating": round(avg_rating, 1) if avg_rating else None,
                    "total_reviews": total,
                },
            },
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get reviews: {str(e)}",
        )


@router.get(
    "/{plugin_id}/my-review",
    response_model=Optional[PluginReviewResponse],
    summary="Get current user's review",
    description="Get the current user's review for a specific plugin",
)
async def get_my_review(
    plugin_id: str = FastPath(..., description="Plugin ID"),
    user_id: str = Depends(get_current_user_id),
    service: PluginService = Depends(get_plugin_service),
):
    """获取当前用户对指定插件的评价"""
    try:
        review = await service.get_user_review(user_id, plugin_id)
        if not review:
            return None
        return PluginReviewResponse.model_validate(review)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get review: {str(e)}",
        )


@router.put(
    "/{plugin_id}/reviews/{review_id}",
    response_model=PluginReviewResponse,
    summary="Update review",
    description="Update an existing review (only by the original author)",
)
async def update_review(
    plugin_id: str = FastPath(..., description="Plugin ID"),
    review_id: int = FastPath(..., description="Review ID"),
    user_id: str = Depends(get_current_user_id),
    data: PluginReviewCreate = Body(...),
    service: PluginService = Depends(get_plugin_service),
):
    """更新用户评价（仅限评价作者）"""
    try:
        review = await service.update_review(user_id, plugin_id, review_id, data)
        if not review:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Review not found or permission denied",
            )
        return PluginReviewResponse.model_validate(review)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update review: {str(e)}",
        )


@router.delete(
    "/{plugin_id}/reviews/{review_id}",
    response_model=dict,
    summary="Delete review",
    description="Delete a review (only by the original author or admin)",
)
async def delete_review(
    plugin_id: str = FastPath(..., description="Plugin ID"),
    review_id: int = FastPath(..., description="Review ID"),
    user_id: str = Depends(get_current_user_id),
    service: PluginService = Depends(get_plugin_service),
):
    """删除用户评价（仅限评价作者或管理员）"""
    try:
        success = await service.delete_review(user_id, plugin_id, review_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Review not found or permission denied",
            )
        return {
            "success": True,
            "message": "Review deleted successfully",
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete review: {str(e)}",
        )


@router.post(
    "/{plugin_id}/reviews/{review_id}/helpful",
    response_model=dict,
    summary="Mark review as helpful",
    description="Vote that a review was helpful",
)
async def mark_review_helpful(
    plugin_id: str = FastPath(..., description="Plugin ID"),
    review_id: int = FastPath(..., description="Review ID"),
    user_id: str = Depends(get_current_user_id),
    service: PluginService = Depends(get_plugin_service),
):
    """标记评价为有用"""
    try:
        result = await service.mark_review_helpful(user_id, review_id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Already marked or review not found",
            )
        return {
            "success": True,
            "message": "Review marked as helpful",
            "helpful_count": result.get("helpful_count", 0),
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to mark helpful: {str(e)}",
        )


# ==================== 插件市场端点 ====================

@router.get(
    "/marketplace",
    response_model=PluginListResponse,
    summary="Plugin marketplace",
    description="Browse marketplace with featured/trending/new filters",
)
async def get_marketplace_plugins(
    featured: bool = Query(False, description="Show featured plugins only"),
    trending: bool = Query(False, description="Sort by popularity/downloads"),
    new_releases: bool = Query(False, description="Show recently released plugins"),
    category: Optional[str] = Query(None, description="Filter by category"),
    min_rating: float = Query(0.0, ge=0.0, le=5.0, description="Minimum rating filter"),
    free_only: bool = Query(False, description="Show free plugins only"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=50, description="Items per page"),
    service: PluginService = Depends(get_plugin_service),
):
    """浏览插件市场"""
    plugins, total = await service.get_marketplace_plugins(
        featured=featured,
        trending=trending,
        new_releases=new_releases,
        category=category,
        min_rating=min_rating,
        free_only=free_only,
        page=page,
        page_size=page_size,
    )
    
    return PluginListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[PluginResponse.model_validate(p) for p in plugins],
    )