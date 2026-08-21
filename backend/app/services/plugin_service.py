"""
Plugin Service Layer
插件业务逻辑层 - 处理CRUD操作、安装卸载、配置管理等
"""

import sys
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy import select, func, desc, and_, or_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

sys.path.insert(0, "D:/My_Project/多智能体小红书发布平台/backend")

from app.db.plugin_models import (
    Plugin,
    PluginVersion,
    PluginConfig,
    PluginReview,
    PluginStats,
    PluginCategory,
    PluginStatus,
    PricingModel,
)
from app.api.schemas.plugin_schemas import (
    PluginCreate,
    PluginUpdate,
    PluginSearchQuery,
    PluginInstallRequest,
    PluginConfigRequest,
    PluginReviewCreate,
)


class PluginService:
    """插件服务类 - 封装所有业务逻辑"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_plugin(self, plugin_id: str) -> Optional[Plugin]:
        """
        获取单个插件详情（包含统计信息）
        """
        result = await self.session.execute(
            select(Plugin)
            .options(
                selectinload(Plugin.stats),
                selectinload(Plugin.versions),
                selectinload(Plugin.reviews),
                selectinload(Plugin.configs),
            )
            .where(Plugin.id == plugin_id)
        )
        plugin = result.scalar_one_or_none()
        return plugin

    async def list_plugins(
        self,
        query: PluginSearchQuery = None,
    ) -> Tuple[List[Plugin], int]:
        """
        获取插件列表（支持搜索、过滤、排序、分页）
        返回 (items, total_count)
        """
        if query is None:
            query = PluginSearchQuery()

        # 构建基础查询
        base_query = select(Plugin)

        # 关键词搜索
        if query.q:
            search_filter = or_(
                Plugin.name.ilike(f"%{query.q}%"),
                Plugin.description.ilike(f"%{query.q}%"),
                Plugin.author_name.ilike(f"%{query.q}%"),
                Plugin.id.ilike(f"%{query.q}%"),
            )
            base_query = base_query.where(search_filter)

        # 分类过滤
        if query.category:
            try:
                category = PluginCategory(query.category.upper()).value
                base_query = base_query.where(Plugin.category == category)
            except ValueError:
                pass

        if query.status:
            try:
                status = PluginStatus(query.status.upper()).value
                base_query = base_query.where(Plugin.status == status)
            except ValueError:
                pass

        if query.pricing_model:
            try:
                pricing = PricingModel(query.pricing_model.upper()).value
                base_query = base_query.where(Plugin.pricing_model == pricing)
            except ValueError:
                pass

        # 作者过滤
        if query.author:
            base_query = base_query.where(Plugin.author_name.ilike(f"%{query.author}%"))

        # 计算总数
        count_query = select(func.count()).select_from(base_query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar()

        # 排序
        sort_column = getattr(Plugin, query.sort_by, None)
        if sort_column is None:
            sort_column = Plugin.created_at
            
        if query.sort_order.lower() == "asc":
            base_query = base_query.order_by(sort_column.asc())
        else:
            base_query = base_query.order_by(desc(sort_column))

        # 分页
        offset = (query.page - 1) * query.page_size
        base_query = base_query.offset(offset).limit(query.page_size)

        # 执行查询并加载关联数据
        result = await self.session.execute(
            base_query.options(selectinload(Plugin.stats))
        )
        plugins = result.scalars().all()

        return list(plugins), total

    async def create_plugin(self, data: PluginCreate) -> Plugin:
        """
        创建新插件
        """
        # 检查是否已存在
        existing = await self.get_plugin(data.id)
        if existing:
            raise ValueError(f"Plugin with ID '{data.id}' already exists")

        # 创建插件实例
        plugin = Plugin(
            id=data.id,
            name=data.name,
            version=data.version,
            description=data.description,
            category=PluginCategory(data.category).value,
            author_name=data.author_name,
            author_email=data.author_email,
            entry_point=data.entry_point,
            display_icon=data.display_icon,
            display_color=data.display_color,
            pricing_model=PricingModel(data.pricing_model.upper()).value,
            price_monthly=data.price_monthly,
            capabilities=data.capabilities,
            permissions=data.permissions,
            config_schema=data.config_schema,
            events_publishes=data.events_publishes,
            events_subscribes=data.events_subscribes,
            dependencies=data.dependencies,
            status=PluginStatus.ACTIVE.value,
            is_builtin=False,
            is_active=True,
        )

        self.session.add(plugin)
        await self.session.flush()  # 获取ID但不提交

        # 创建初始版本记录
        version_record = PluginVersion(
            plugin_id=plugin.id,
            version=data.version,
            is_latest=True,
            released_at=datetime.utcnow(),
        )
        self.session.add(version_record)

        # 创建初始统计记录
        stats = await self._create_initial_stats(plugin.id)
        self.session.add(stats)

        await self.session.commit()
        await self.session.refresh(plugin)

        return plugin

    async def update_plugin(
        self,
        plugin_id: str,
        data: PluginUpdate,
    ) -> Plugin:
        """
        更新插件信息（部分更新）
        """
        plugin = await self.get_plugin(plugin_id)
        if not plugin:
            raise ValueError(f"Plugin '{plugin_id}' not found")

        # 更新非空字段
        update_data = data.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            if field == "category" and value:
                value = PluginCategory(value.upper()).value
            elif field == "status" and value:
                value = PluginStatus(value.upper()).value
            elif field == "pricing_model" and value:
                value = PricingModel(value.upper()).value
            
            setattr(plugin, field, value)

        plugin.updated_at = datetime.utcnow()
        
        await self.session.commit()
        await self.session.refresh(plugin)

        return plugin

    async def delete_plugin(self, plugin_id: str) -> bool:
        """
        删除插件（级联删除所有相关数据）
        """
        plugin = await self.get_plugin(plugin_id)
        if not plugin:
            raise ValueError(f"Plugin '{plugin_id}' not found")

        if plugin.is_builtin:
            raise ValueError("Cannot delete built-in plugin")

        await self.session.delete(plugin)
        await self.session.commit()

        return True

    async def install_plugin(
        self,
        user_id: str,
        plugin_id: str,
        request: PluginInstallRequest = None,
    ) -> Dict[str, Any]:
        """
        为用户安装插件
        """
        plugin = await self.get_plugin(plugin_id)
        if not plugin:
            raise ValueError(f"Plugin '{plugin_id}' not found")

        if plugin.status != PluginStatus.ACTIVE:
            raise ValueError(f"Plugin '{plugin_id}' is not available")

        # 检查是否已安装
        existing_config = await self._get_user_config(user_id, plugin_id)
        if existing_config:
            # 已安装，更新配置
            if request and request.config:
                existing_config.config_json = request.config
                existing_config.is_enabled = True
                await self.session.commit()
                
                return {
                    "success": True,
                    "message": f"Plugin '{plugin_id}' reconfigured",
                    "action": "reconfigure",
                    "plugin_id": plugin_id,
                }
            else:
                return {
                    "success": False,
                    "message": f"Plugin '{plugin_id}' already installed",
                    "action": "none",
                    "plugin_id": plugin_id,
                }

        # 确定安装版本
        version_to_install = plugin.version  # 默认当前版本
        if request and request.version:
            # 验证请求的版本是否存在
            version_exists = await self._version_exists(plugin_id, request.version)
            if version_exists:
                version_to_install = request.version

        # 创建用户配置
        config_data = {}
        if request and request.config:
            config_data = request.config

        new_config = PluginConfig(
            user_id=user_id,
            plugin_id=plugin_id,
            config_json=config_data,
            is_enabled=True,
        )
        self.session.add(new_config)

        # 更新安装计数
        plugin.install_count += 1
        
        await self.session.commit()

        return {
            "success": True,
            "message": f"Plugin '{plugin_id}' v{version_to_install} installed successfully",
            "action": "install",
            "plugin_id": plugin_id,
            "installed_version": version_to_install,
        }

    async def uninstall_plugin(
        self,
        user_id: str,
        plugin_id: str,
    ) -> Dict[str, Any]:
        """
        卸载用户的插件
        """
        config = await self._get_user_config(user_id, plugin_id)
        if not config:
            # idempotent: not installed counts as already uninstalled
            return {
                "success": True,
                "message": f"Plugin '{plugin_id}' is not installed, nothing to uninstall",
                "action": "uninstall",
                "plugin_id": plugin_id,
            }

        await self.session.delete(config)
        
        # 更新安装计数（确保不小于0）
        plugin = await self.get_plugin(plugin_id)
        if plugin and plugin.install_count > 0:
            plugin.install_count -= 1

        await self.session.commit()

        return {
            "success": True,
            "message": f"Plugin '{plugin_id}' uninstalled successfully",
            "action": "uninstall",
            "plugin_id": plugin_id,
        }

    async def enable_plugin(
        self,
        user_id: str,
        plugin_id: str,
    ) -> Dict[str, Any]:
        """
        启用用户的插件
        """
        config = await self._get_user_config(user_id, plugin_id)
        if not config:
            raise ValueError(f"Plugin '{plugin_id}' is not installed")

        if config.is_enabled:
            return {
                "success": False,
                "message": f"Plugin '{plugin_id}' is already enabled",
                "action": "none",
                "plugin_id": plugin_id,
            }

        config.is_enabled = True
        await self.session.commit()

        return {
            "success": True,
            "message": f"Plugin '{plugin_id}' enabled",
            "action": "enable",
            "plugin_id": plugin_id,
        }

    async def disable_plugin(
        self,
        user_id: str,
        plugin_id: str,
    ) -> Dict[str, Any]:
        """
        禁用用户的插件
        """
        config = await self._get_user_config(user_id, plugin_id)
        if not config:
            raise ValueError(f"Plugin '{plugin_id}' is not installed")

        if not config.is_enabled:
            return {
                "success": False,
                "message": f"Plugin '{plugin_id}' is already disabled",
                "action": "none",
                "plugin_id": plugin_id,
            }

        config.is_enabled = False
        await self.session.commit()

        return {
            "success": True,
            "message": f"Plugin '{plugin_id}' disabled",
            "action": "disable",
            "plugin_id": plugin_id,
        }

    async def get_user_plugins(
        self,
        user_id: str,
        only_enabled: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        获取用户已安装的所有插件列表
        """
        query = select(PluginConfig).where(PluginConfig.user_id == user_id)
        
        if only_enabled:
            query = query.where(PluginConfig.is_enabled == True)

        result = await self.session.execute(
            query.options(selectinload(PluginConfig.plugin))
        )
        configs = result.scalars().all()

        user_plugins = []
        for config in configs:
            if config.plugin:
                plugin_info = {
                    "id": config.plugin_id,
                    "plugin_id": config.plugin_id,
                    "name": config.plugin.name,
                    "version": config.plugin.version,
                    "is_enabled": config.is_enabled,
                    "config": config.config_json,
                    "installed_at": config.created_at.isoformat(),
                    "category": config.plugin.category,
                    "display_icon": config.plugin.display_icon,
                    "status": config.plugin.status,
                    "is_builtin": config.plugin.is_builtin,
                    "is_active": config.plugin.is_active,
                }
                user_plugins.append(plugin_info)

        return user_plugins

    async def update_plugin_config(
        self,
        user_id: str,
        plugin_id: str,
        data: PluginConfigRequest,
    ) -> PluginConfig:
        """
        更新用户插件配置
        """
        config = await self._get_user_config(user_id, plugin_id)
        if not config:
            raise ValueError(f"Plugin '{plugin_id}' is not installed for user '{user_id}'")

        config.config_json = data.config_json
        if data.encrypted_fields:
            config.encrypted_fields = data.encrypted_fields
        config.is_enabled = data.is_enabled
        config.updated_at = datetime.utcnow()

        await self.session.commit()
        await self.session.refresh(config)

        return config

    async def create_review(
        self,
        user_id: str,
        plugin_id: str,
        data: PluginReviewCreate,
    ) -> PluginReview:
        """
        创建插件评价
        """
        plugin = await self.get_plugin(plugin_id)
        if not plugin:
            raise ValueError(f"Plugin '{plugin_id}' not found")

        # 检查是否已评价
        existing_review = await self._get_user_review(user_id, plugin_id)
        if existing_review:
            raise ValueError("You have already reviewed this plugin")

        # 验证是否已购买/安装（可选）
        is_verified = await self._is_installed(user_id, plugin_id)

        review = PluginReview(
            plugin_id=plugin_id,
            user_id=user_id,
            rating=data.rating,
            title=data.title,
            content=data.content,
            is_verified_purchase=is_verified,
            moderation_status="pending",  # 待审核
        )

        self.session.add(review)
        await self.session.flush()  # 获取ID

        # 更新插件的平均评分
        await self._update_average_rating(plugin_id)

        await self.session.commit()
        await self.session.refresh(review)

        return review

    async def get_plugin_reviews(
        self,
        plugin_id: str,
        page: int = 1,
        page_size: int = 10,
        sort_by: str = "newest",
        rating_filter: Optional[int] = None,
    ) -> Tuple[List[PluginReview], int, Optional[float]]:
        """
        获取插件评价列表（支持分页、排序和筛选）

        Args:
            plugin_id: 插件ID
            page: 页码
            page_size: 每页数量
            sort_by: 排序方式 (newest/oldest/rating_high/rating_low/helpful)
            rating_filter: 星级筛选 (1-5)

        Returns:
            (评价列表, 总数, 平均评分)
        """
        base_query = select(PluginReview).where(
            PluginReview.plugin_id == plugin_id,
            PluginReview.moderation_status == "approved",  # 只显示已通过审核的评价
        )

        # 星级筛选
        if rating_filter:
            base_query = base_query.where(PluginReview.rating == rating_filter)

        # 排序
        if sort_by == "newest":
            base_query = base_query.order_by(desc(PluginReview.created_at))
        elif sort_by == "oldest":
            base_query = base_query.order_by(asc(PluginReview.created_at))
        elif sort_by == "rating_high":
            base_query = base_query.order_by(desc(PluginReview.rating), desc(PluginReview.created_at))
        elif sort_by == "rating_low":
            base_query = base_query.order_by(asc(PluginReview.rating), asc(PluginReview.created_at))
        elif sort_by == "helpful":
            base_query = base_query.order_by(desc(PluginReview.helpful_count), desc(PluginReview.created_at))
        else:
            base_query = base_query.order_by(desc(PluginReview.created_at))

        # 计算总数
        count_query = select(func.count()).select_from(PluginReview).where(
            PluginReview.plugin_id == plugin_id,
            PluginReview.moderation_status == "approved",
        )
        if rating_filter:
            count_query = count_query.where(PluginReview.rating == rating_filter)

        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        # 分页
        offset = (page - 1) * page_size
        paginated_query = base_query.offset(offset).limit(page_size)

        result = await self.session.execute(paginated_query)
        reviews = result.scalars().all()

        # 获取平均评分
        avg_query = select(func.avg(PluginReview.rating)).where(
            PluginReview.plugin_id == plugin_id,
            PluginReview.moderation_status == "approved",
        )
        avg_result = await self.session.execute(avg_query)
        avg_rating = avg_result.scalar()

        return list(reviews), total, avg_rating

    async def get_user_review(
        self,
        user_id: str,
        plugin_id: str,
    ) -> Optional[PluginReview]:
        """获取用户对指定插件的评价"""
        return await self._get_user_review(user_id, plugin_id)

    async def update_review(
        self,
        user_id: str,
        plugin_id: str,
        review_id: int,
        data: PluginReviewCreate,
    ) -> Optional[PluginReview]:
        """
        更新用户评价

        Returns:
            更新后的评价对象，如果不存在或无权限则返回None
        """
        # 查找评价并验证权限
        query = select(PluginReview).where(
            PluginReview.id == review_id,
            PluginReview.plugin_id == plugin_id,
            PluginReview.user_id == user_id,  # 验证是作者本人
        )

        result = await self.session.execute(query)
        review = result.scalar_one_or_none()

        if not review:
            return None

        # 更新字段
        review.rating = data.rating
        review.title = data.title
        review.content = data.content
        review.updated_at = datetime.utcnow()

        # 重新设置为待审核（如果开启了审核机制）
        review.moderation_status = "pending"

        await self.session.flush()

        # 更新插件的平均评分
        await self._update_average_rating(plugin_id)

        await self.session.commit()
        await self.session.refresh(review)

        return review

    async def delete_review(
        self,
        user_id: str,
        plugin_id: str,
        review_id: int,
    ) -> bool:
        """
        删除用户评价

        Returns:
            是否删除成功
        """
        # 查找评价并验证权限
        query = select(PluginReview).where(
            PluginReview.id == review_id,
            PluginReview.plugin_id == plugin_id,
            PluginReview.user_id == user_id,  # 验证是作者本人
        )

        result = await self.session.execute(query)
        review = result.scalar_one_or_none()

        if not review:
            return False

        # 删除评价
        await self.session.delete(review)

        # 更新插件的平均评分
        await self._update_average_rating(plugin_id)

        await self.session.commit()

        return True

    async def mark_review_helpful(
        self,
        user_id: str,
        review_id: int,
    ) -> Optional[dict]:
        """
        标记评价为有用（每个用户只能标记一次）

        Returns:
            包含helpful_count的字典，如果已标记或评价不存在则返回None
        """
        # 查找评价
        query = select(PluginReview).where(PluginReview.id == review_id)
        result = await self.session.execute(query)
        review = result.scalar_one_or_none()

        if not review:
            return None

        # TODO: 实现去重逻辑（可以用单独的表记录哪些用户标记过）
        # 简化实现：直接增加计数（生产环境需要IP/User限制）

        review.helpful_count += 1
        review.updated_at = datetime.utcnow()

        await self.session.commit()

        return {
            "review_id": review_id,
            "helpful_count": review.helpful_count,
        }

    async def _update_average_rating(self, plugin_id: str):
        """更新插件的平均评分（内部方法）"""
        avg_query = select(func.avg(PluginReview.rating)).where(
            PluginReview.plugin_id == plugin_id,
            PluginReview.moderation_status.in_(["approved", "pending"]),
        )
        count_query = select(func.count()).select_from(PluginReview).where(
            PluginReview.plugin_id == plugin_id,
            PluginReview.moderation_status.in_(["approved", "pending"]),
        )

        avg_result = await self.session.execute(avg_query)
        count_result = await self.session.execute(count_query)

        avg_rating = avg_result.scalar()
        review_count = count_result.scalar() or 0

        # 更新插件表中的统计数据
        update_stmt = (
            update(Plugin)
            .where(Plugin.id == plugin_id)
            .values(
                average_rating=avg_rating,
                review_count=review_count,
                updated_at=datetime.utcnow(),
            )
        )

        await self.session.execute(update_stmt)

    async def list_versions(
        self,
        plugin_id: str,
        include_deprecated: bool = False,
    ) -> List[PluginVersion]:
        """
        获取插件的所有版本
        """
        query = select(PluginVersion).where(PluginVersion.plugin_id == plugin_id)
        
        if not include_deprecated:
            # 可以添加版本状态字段来过滤废弃版本
            pass

        query = query.order_by(desc(PluginVersion.version))
        
        result = await self.session.execute(query)
        versions = result.scalars().all()

        return list(versions)

    async def get_marketplace_plugins(
        self,
        featured: bool = False,
        trending: bool = False,
        new_releases: bool = False,
        category: Optional[str] = None,
        min_rating: float = 0.0,
        free_only: bool = False,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Plugin], int]:
        """
        获取插件市场列表（支持多种展示模式）
        """
        base_query = select(Plugin).where(
            Plugin.status == PluginStatus.ACTIVE,
            Plugin.is_active == True,
        )

        # 精选推荐
        if featured:
            base_query = base_query.where(Plugin.is_featured == True)

        # 新发布（最近7天）
        if new_releases:
            week_ago = datetime.utcnow() - timedelta(days=7)
            base_query = base_query.where(Plugin.created_at >= week_ago)

        # 分类过滤
        if category:
            try:
                cat = PluginCategory(category.upper()).value
                base_query = base_query.where(Plugin.category == cat)
            except ValueError:
                pass

        # 最低评分
        if min_rating > 0:
            base_query = base_query.where(Plugin.average_rating >= min_rating)

        # 仅免费
        if free_only:
            base_query = base_query.where(Plugin.pricing_model == PricingModel.FREE.value)

        # 计数
        count_query = select(func.count()).select_from(base_query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar()

        # 排序
        if trending:
            # 按下载量或评分排序
            base_query = base_query.order_by(desc(Plugin.install_count))
        else:
            base_query = base_query.order_by(desc(Plugin.created_at))

        # 分页
        offset = (page - 1) * page_size
        base_query = base_query.offset(offset).limit(page_size)

        # 执行
        result = await self.session.execute(
            base_query.options(
                selectinload(Plugin.stats),
                selectinload(Plugin.reviews),
            )
        )
        plugins = result.scalars().all()

        return list(plugins), total

    async def bulk_action(
        self,
        user_id: str,
        plugin_ids: List[str],
        action: str,
    ) -> Dict[str, Any]:
        """
        批量操作（启用/禁用/卸载）
        """
        results = []
        succeeded = 0
        failed = 0

        for plugin_id in plugin_ids:
            try:
                if action == "enable":
                    result = await self.enable_plugin(user_id, plugin_id)
                elif action == "disable":
                    result = await self.disable_plugin(user_id, plugin_id)
                elif action == "uninstall":
                    result = await self.uninstall_plugin(user_id, plugin_id)
                else:
                    raise ValueError(f"Invalid action: {action}")

                results.append({
                    "plugin_id": plugin_id,
                    "success": result["success"],
                    "message": result["message"],
                })

                if result["success"]:
                    succeeded += 1
                else:
                    failed += 1

            except Exception as e:
                failed += 1
                results.append({
                    "plugin_id": plugin_id,
                    "success": False,
                    "message": str(e),
                })

        return {
            "total_requested": len(plugin_ids),
            "succeeded": succeeded,
            "failed": failed,
            "results": results,
        }

    # ==================== 私有辅助方法 ====================

    async def _get_user_config(
        self,
        user_id: str,
        plugin_id: str,
    ) -> Optional[PluginConfig]:
        """获取用户插件配置"""
        result = await self.session.execute(
            select(PluginConfig).where(
                PluginConfig.user_id == user_id,
                PluginConfig.plugin_id == plugin_id,
            )
        )
        return result.scalar_one_or_none()

    async def _get_user_review(
        self,
        user_id: str,
        plugin_id: str,
    ) -> Optional[PluginReview]:
        """获取用户评价"""
        result = await self.session.execute(
            select(PluginReview).where(
                PluginReview.user_id == user_id,
                PluginReview.plugin_id == plugin_id,
            )
        )
        return result.scalar_one_or_none()

    async def _is_installed(
        self,
        user_id: str,
        plugin_id: str,
    ) -> bool:
        """检查用户是否已安装该插件"""
        config = await self._get_user_config(user_id, plugin_id)
        return config is not None

    async def _version_exists(
        self,
        plugin_id: str,
        version: str,
    ) -> bool:
        """检查版本是否存在"""
        result = await self.session.execute(
            select(func.count())
            .select_from(PluginVersion)
            .where(
                PluginVersion.plugin_id == plugin_id,
                PluginVersion.version == version,
            )
        )
        count = result.scalar()
        return count > 0

    async def _create_initial_stats(
        self,
        plugin_id: str,
    ) -> PluginStats:
        """创建初始统计记录"""
        from app.db.plugin_models import create_initial_stats
        return create_initial_stats(plugin_id)

    async def _update_average_rating(self, plugin_id: str):
        """更新插件平均评分"""
        # 计算新的平均分
        result = await self.session.execute(
            select(
                func.avg(PluginReview.rating),
                func.count(PluginReview.id),
            ).where(PluginReview.plugin_id == plugin_id)
        )
        avg_rating, total_reviews = result.one()

        # 更新插件表
        plugin = await self.get_plugin(plugin_id)
        if plugin:
            plugin.average_rating = round(avg_rating or 0.0, 2)
            plugin.total_reviews = total_reviews or 0