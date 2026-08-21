"""
Plugin API Schemas (Pydantic v2)
插件系统的请求/响应模型定义
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class PluginBase(BaseModel):
    """插件基础字段"""
    name: str = Field(..., min_length=1, max_length=128)
    description: Optional[str] = Field(None, max_length=2000)
    category: str  # PluginCategory enum value
    author_name: str = Field(..., min_length=1, max_length=64)
    author_email: Optional[str] = Field(None, pattern=r'^[^@]+@[^@]+\.[^@]+$')
    display_icon: Optional[str] = "📦"
    display_color: Optional[str] = "#6366f1"
    pricing_model: str = "free"  # PricingModel enum value
    price_monthly: float = Field(0.0, ge=0)


class PluginCreate(PluginBase):
    """创建插件请求"""
    id: str = Field(..., min_length=1, max_length=64, pattern=r'^[a-z0-9][a-z0-9_-]*$')
    version: str = Field(..., pattern=r'^\d+\.\d+\.\d+$')
    entry_point: str = "main.py"
    capabilities: List[str] = []
    permissions: List[str] = []
    config_schema: Optional[Dict[str, Any]] = None
    events_publishes: List[str] = []
    events_subscribes: List[str] = []
    dependencies: Optional[Dict[str, str]] = None


class PluginUpdate(BaseModel):
    """更新插件请求（部分更新）"""
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    description: Optional[str] = Field(None, max_length=2000)
    version: Optional[str] = Field(None, pattern=r'^\d+\.\d+\.\d+$')
    status: Optional[str] = None  # PluginStatus enum value
    pricing_model: Optional[str] = None
    price_monthly: Optional[float] = Field(None, ge=0)
    display_icon: Optional[str] = None
    display_color: Optional[str] = None
    capabilities: Optional[List[str]] = None
    permissions: Optional[List[str]] = None
    config_schema: Optional[Dict[str, Any]] = None


class PluginResponse(PluginBase):
    """插件响应（完整信息）"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    version: str
    status: str
    entry_point: str
    is_builtin: bool
    is_active: bool = False
    install_count: int = 0
    average_rating: float = 0.0
    total_reviews: int = 0
    review_count: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    capabilities: List[str] = []
    permissions: List[str] = []
    config_schema: Optional[Dict[str, Any]] = None
    events_publishes: List[str] = []
    events_subscribes: List[str] = []
    dependencies: Optional[Any] = None
    
    stats: Optional['PluginStatsResponse'] = None


class PluginListResponse(BaseModel):
    """插件列表响应"""
    total: int
    page: int
    page_size: int
    items: List[PluginResponse]


class PluginStatsResponse(BaseModel):
    """插件统计响应"""
    model_config = ConfigDict(from_attributes=True)

    total_executions: int
    successful_executions: int
    failed_executions: int
    success_rate: float
    avg_execution_time_ms: Optional[float]
    health_status: str
    last_execution_at: Optional[datetime]


class PluginVersionCreate(BaseModel):
    """创建版本请求"""
    version: str = Field(..., pattern=r'^\d+\.\d+\.\d+$')
    changelog: Optional[str] = None
    release_notes: Optional[str] = None
    package_url: Optional[str] = None
    package_checksum: Optional[str] = None
    package_size_bytes: Optional[int] = Field(None, ge=0)
    min_platform_version: Optional[str] = None
    is_latest: bool = False


class PluginVersionResponse(BaseModel):
    """版本响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    plugin_id: str
    version: str
    changelog: Optional[str]
    release_notes: Optional[str]
    package_url: Optional[str]
    package_checksum: Optional[str]
    package_size_bytes: Optional[int]
    download_count: int
    min_platform_version: Optional[str]
    is_latest: bool
    released_at: datetime
    created_at: datetime


class PluginConfigRequest(BaseModel):
    """配置写入请求"""
    config_json: Dict[str, Any] = {}
    encrypted_fields: Optional[Dict[str, str]] = None
    is_enabled: bool = True


class PluginConfigResponse(BaseModel):
    """配置响应"""
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    plugin_id: str
    config_json: Dict[str, Any]
    encrypted_fields: Optional[Dict[str, str]]
    is_enabled: bool
    created_at: datetime
    updated_at: datetime


class PluginReviewCreate(BaseModel):
    """创建评价请求"""
    rating: int = Field(..., ge=1, le=5)
    title: Optional[str] = Field(None, max_length=100)
    content: Optional[str] = Field(None, max_length=2000)


class PluginReviewResponse(BaseModel):
    """评价响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    plugin_id: str
    user_id: str
    rating: int
    title: Optional[str]
    content: Optional[str]
    is_verified_purchase: bool
    helpful_count: int
    moderation_status: str
    created_at: datetime


class PluginInstallRequest(BaseModel):
    """安装插件请求"""
    version: Optional[str] = None  # 指定版本，默认最新
    config: Optional[Dict[str, Any]] = None  # 初始配置


class PluginActionResponse(BaseModel):
    """操作响应（安装/卸载/启用/禁用）"""
    success: bool
    message: str
    plugin_id: str
    action: str  # install/uninstall/enable/disable/reload
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PluginSearchQuery(BaseModel):
    """搜索查询参数"""
    q: Optional[str] = None  # 关键词搜索
    category: Optional[str] = None  # 分类过滤
    status: Optional[str] = None  # 状态过滤
    pricing_model: Optional[str] = None  # 定价过滤
    author: Optional[str] = None  # 作者过滤
    sort_by: str = "created_at"  # 排序字段
    sort_order: str = "desc"  # asc/desc
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)


class BulkActionRequest(BaseModel):
    """批量操作请求"""
    plugin_ids: List[str] = Field(..., min_length=1, max_length=50)
    action: str  # enable/disable/uninstall


class BulkActionResponse(BaseModel):
    """批量操作响应"""
    total_requested: int
    succeeded: int
    failed: int
    results: List[dict]


class MarketplaceQuery(BaseModel):
    """插件市场查询"""
    featured: bool = False  # 精选推荐
    trending: bool = False  # 热门趋势
    new_releases: bool = False  # 最新发布
    category: Optional[str] = None
    min_rating: Optional[float] = Field(None, ge=0, le=5)
    free_only: bool = False
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=50)


# Update forward references
PluginResponse.model_rebuild()