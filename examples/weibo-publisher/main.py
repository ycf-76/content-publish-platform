"""
Weibo Publisher Plugin - 平台发布插件示例

功能特性:
- 微博OAuth2认证与多账号管理
- 图文/视频内容发布
- 定时发布支持
- 发布历史记录与管理
- 图片自动压缩与优化
- 发布频率限制与错误重试

适用场景: 社交媒体运营、内容分发、品牌推广等
"""

import asyncio
import base64
import hashlib
import hmac
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Any, Optional, Tuple
import json


# ===== 基础数据模型 =====

class Visibility(Enum):
    """可见范围"""
    PUBLIC = "public"
    FRIENDS = "friends"
    PRIVATE = "private"


class PublishStatus(Enum):
    """发布状态"""
    PENDING = "pending"
    PUBLISHED = "published"
    FAILED = "failed"
    SCHEDULED = "scheduled"
    DELETED = "deleted"


@dataclass
class WeiboAccount:
    """微博账号信息"""
    account_id: str
    access_token: str
    refresh_token: str = ""
    nickname: str = ""
    avatar_url: str = ""
    followers_count: int = 0
    token_expires_at: Optional[datetime] = None
    is_active: bool = True
    
    def is_token_valid(self) -> bool:
        if not self.token_expires_at:
            return True
        return datetime.utcnow() < self.token_expires_at


@dataclass
class PublishedPost:
    """已发布的微博"""
    post_id: str
    content: Dict[str, Any]
    published_at: datetime
    status: PublishStatus
    post_url: str = ""
    engagement: Dict[str, int] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        result = asdict(self)
        result["status"] = self.status.value
        if isinstance(result["published_at"], datetime):
            result["published_at"] = result["published_at"].isoformat()
        return result


@dataclass
class PublishResult:
    """发布结果"""
    success: bool
    post_id: str = ""
    post_url: str = ""
    published_at: Optional[datetime] = None
    error_message: str = ""
    retry_after: Optional[int] = None  # 秒数，用于限流


# ===== 插件主类 =====

class WeiboPublisherPlugin:
    """
    微博发布平台插件
    
    展示platform类型插件的完整实现，包括：
    - OAuth2第三方认证
    - 内容发布到外部平台
    - 多账号管理
    - 定时任务调度
    - 发布历史追踪
    """
    
    # ===== 内部数据结构 =====
    
    @dataclass
    class HealthStatus:
        def __init__(self, status: str, message: str, timestamp: datetime = None, details: dict = None):
            self.status = status
            self.message = message
            self.timestamp = timestamp or datetime.utcnow()
            self.details = details or {}
    
    @dataclass
    class PluginManifest:
        id: str
        name: str
        version: str
        description: str
        author: str
        capabilities: list
        permissions_required: list
    
    @dataclass
    class PluginContext:
        def __init__(self):
            self.user_id = "anonymous"
            self.config = {}
            self.event_bus = MockEventBus()
            self.storage = {}
    
    # ===== 初始化 =====
    
    def __init__(self):
        self.id = "weibo-publisher"
        self.name = "Weibo Publisher"
        self.version = "1.0.0"
        
        # 内部状态
        self._accounts: Dict[str, WeiboAccount] = {}  # 账号缓存
        self._publish_history: List[PublishedPost] = []  # 发布历史
        self._scheduled_tasks: Dict[str, Dict] = {}  # 定时任务
        self._rate_limit_tracker: Dict[str, List[datetime]] = {}  # 频率限制跟踪
        
        # 统计计数器
        self._stats = {
            "total_publish_attempts": 0,
            "successful_publishes": 0,
            "failed_publishes": 0,
            "scheduled_tasks": 0,
            "deleted_posts": 0,
            "rate_limited": 0
        }
        
        # 模拟数据（实际项目从数据库加载）
        self._init_mock_data()
    
    def _init_mock_data(self):
        """初始化模拟账号数据"""
        mock_account = WeiboAccount(
            account_id="mock_account_001",
            access_token="mock_access_token_xxxxx",
            refresh_token="mock_refresh_token_yyyyy",
            nickname="测试博主",
            avatar_url="https://example.com/avatar.jpg",
            followers_count=10000,
            token_expires_at=datetime.utcnow() + timedelta(days=30),
            is_active=True
        )
        self._accounts[mock_account.account_id] = mock_account
    
    # ===== 生命周期方法 =====
    
    async def on_load(self):
        """插件加载时调用"""
        print("[weibo-publisher] Plugin loaded successfully")
        print(f"[weibo-publisher] Loaded {len(self._accounts)} accounts")
        return True
    
    async def on_unload(self):
        """插件卸载时调用"""
        print(f"[weibo-publisher] Plugin unloaded. Stats: {self._stats}")
        return True
    
    async def health_check(self) -> 'HealthStatus':
        """健康检查"""
        active_accounts = sum(1 for acc in self._accounts.values() 
                           if acc.is_active and acc.is_token_valid())
        
        return self.HealthStatus(
            status="healthy" if active_accounts > 0 else "degraded",
            message=f"Managing {len(self._accounts)} accounts ({active_accounts} active)",
            details={
                "total_accounts": len(self._accounts),
                "active_accounts": active_accounts,
                "publish_history_size": len(self._publish_history),
                "scheduled_tasks": len(self._scheduled_tasks),
                "stats": self._stats.copy()
            }
        )
    
    def get_manifest(self) -> 'PluginManifest':
        """返回插件清单"""
        return self.PluginManifest(
            id=self.id,
            name=self.name,
            version=self.version,
            description="Weibo social media publishing platform with multi-account support",
            author="Platform Team <dev@your-platform.com>",
            capabilities=["execute", "validate_inputs", "schedule_publish", "manage_accounts"],
            permissions_required=["network:read_write", "storage:read_write", "auth:oauth"]
        )
    
    # ===== 核心验证方法 =====
    
    async def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, str]:
        """验证输入参数"""
        action = inputs.get("action", "publish_text")
        
        valid_actions = [
            "publish_text", "publish_image", "publish_video",
            "schedule_publish", "get_publish_history",
            "delete_post", "get_account_info"
        ]
        
        if action not in valid_actions:
            return False, f"Invalid action '{action}'. Must be one of: {valid_actions}"
        
        content = inputs.get("content")
        if action in ["publish_text", "publish_image", "publish_video", "schedule_publish"]:
            if not content or "text" not in content:
                return False, "Content with 'text' field is required for publish actions"
            
            text = content.get("text", "")
            max_length = 2000  # 微博最大字数
            if len(text) > max_length:
                return False, f"Text too long ({len(text)} chars). Maximum: {max_length}"
            
            if len(text.strip()) == 0:
                return False, "Text cannot be empty"
            
            # 验证图片数量
            images = content.get("images", [])
            if len(images) > 9:
                return False, f"Too many images ({len(images)}). Maximum: 9"

            # 验证视频URL（如果是视频发布）
            if action == "publish_video":
                video_url = content.get("video_url")
                if not video_url:
                    return False, "video_url is required for video publish"

        if action == "delete_post":
            if not inputs.get("post_id"):
                return False, "post_id is required for delete operation"
        
        if action == "schedule_publish":
            scheduled_time = inputs.get("scheduled_time")
            if not scheduled_time:
                return False, "scheduled_time is required for schedule_publish"
            
            try:
                sched_dt = datetime.fromisoformat(scheduled_time.replace('Z', '+00:00'))
                if sched_dt <= datetime.utcnow():
                    return False, "scheduled_time must be in the future"
            except ValueError:
                return False, "Invalid scheduled_time format. Use ISO 8601 format"
        
        return True, "Inputs validated"
    
    async def validate_config(self, config: Dict[str, Any]) -> Tuple[bool, str]:
        """验证配置"""
        if "app_key" not in config or not config["app_key"]:
            return False, "app_key is required"
        
        if "app_secret" not in config or not config["app_secret"]:
            return False, "app_secret is required"
        
        rate_limit = config.get("rate_limit_per_hour", 30)
        if not (5 <= rate_limit <= 100):
            return False, "rate_limit_per_hour must be between 5 and 100"
        
        return True, "Configuration validated"
    
    # ===== 核心执行方法 =====
    
    async def execute(
        self,
        ctx: 'PluginContext',
        inputs: Dict[str, Any]
    ) -> 'NodeOutput':
        """
        执行主要操作
        
        支持的操作：
        - publish_text: 发布纯文本微博
        - publish_image: 发布图文微博
        - publish_video: 发布视频微博
        - schedule_publish: 定时发布
        - get_publish_history: 获取发布历史
        - delete_post: 删除已发布微博
        - get_account_info: 获取账号信息
        """
        start_time = time.time()
        
        try:
            is_valid, error_msg = await self.validate_inputs(inputs)
            if not is_valid:
                return NodeOutput(success=False, data={}, message=error_msg, execution_time_ms=0)
            
            config = ctx.config or {}
            action = inputs.get("action", "publish_text")
            
            if action == "publish_text":
                result = await self._execute_publish_text(ctx, config, inputs)
            elif action == "publish_image":
                result = await self._execute_publish_image(ctx, config, inputs)
            elif action == "publish_video":
                result = await self._execute_publish_video(ctx, config, inputs)
            elif action == "schedule_publish":
                result = await self._execute_schedule_publish(ctx, config, inputs)
            elif action == "get_publish_history":
                result = await self._get_publish_history(inputs)
            elif action == "delete_post":
                result = await self._execute_delete_post(ctx, inputs)
            elif action == "get_account_info":
                result = await self._get_account_info(inputs)
            else:
                result = NodeOutput(success=False, data={}, message=f"Unknown action: {action}", execution_time_ms=0)
            
            elapsed_ms = int((time.time() - start_time) * 1000)
            result.execution_time_ms = elapsed_ms
            
            return result
        
        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            return NodeOutput(
                success=False,
                data={},
                message=f"Execution failed: {str(e)}",
                execution_time_ms=elapsed_ms
            )
    
    # ===== 操作实现 =====
    
    async def _execute_publish_text(
        self,
        ctx: 'PluginContext',
        config: Dict[str, Any],
        inputs: Dict[str, Any]
    ) -> 'NodeOutput':
        """执行文本发布"""
        content = inputs["content"]
        account_id = inputs.get("account_id") or config.get("default_account_id")
        
        # 检查频率限制
        rate_check = self._check_rate_limit(account_id, config)
        if not rate_check[0]:
            self._stats["rate_limited"] += 1
            return NodeOutput(
                success=False,
                data={},
                message=f"Rate limit exceeded. Retry after {rate_check[1]} seconds",
                execution_time_ms=0
            )
        
        # 获取账号
        account = self._get_account(account_id)
        if not account:
            return NodeOutput(success=False, data={}, message=f"Account not found: {account_id}")
        
        self._stats["total_publish_attempts"] += 1
        
        # 模拟API调用（实际项目调用微博API）
        publish_result = await self._call_weibo_api("statuses/update", {
            "status": content["text"],
            "access_token": account.access_token
        })
        
        if publish_result.success:
            # 记录发布历史
            post = PublishedPost(
                post_id=publish_result.post_id,
                content=content,
                published_at=publish_result.published_at or datetime.utcnow(),
                status=PublishStatus.PUBLISHED,
                post_url=publish_result.post_url
            )
            self._publish_history.append(post)
            
            self._stats["successful_publishes"] += 1
            self._record_api_call(account_id)
            
            # 发送成功事件
            if ctx.event_bus:
                await ctx.event_bus.emit("weibo:publish_success", {
                    "plugin_id": self.id,
                    "post_id": post.post_id,
                    "account_id": account_id,
                    "text_preview": content["text"][:50] + "..."
                })
            
            return NodeOutput(
                success=True,
                data={
                    "post_id": post.post_id,
                    "post_url": post.post_url,
                    "published_at": post.published_at.isoformat(),
                    "stats": {
                        "text_length": len(content["text"]),
                        "image_count": 0,
                        "has_video": False
                    }
                },
                message=f"Successfully published text weibo (ID: {post.post_id})"
            )
        else:
            self._stats["failed_publishes"] += 1
            
            # 自动重试
            if config.get("auto_retry_on_failure", True):
                retry_result = await self._retry_publish(ctx, config, inputs, account)
                if retry_result.success:
                    return retry_result
            
            # 发送失败事件
            if ctx.event_bus:
                await ctx.event_bus.emit("weibo:publish_failed", {
                    "plugin_id": self.id,
                    "error": publish_result.error_message,
                    "account_id": account_id
                })
            
            return NodeOutput(
                success=False,
                data={},
                message=f"Publish failed: {publish_result.error_message}",
                execution_time_ms=0
            )
    
    async def _execute_publish_image(
        self,
        ctx: 'PluginContext',
        config: Dict[str, Any],
        inputs: Dict[str, Any]
    ) -> 'NodeOutput':
        """执行图文发布"""
        content = inputs["content"]
        account_id = inputs.get("account_id") or config.get("default_account_id")
        
        # 验证图片
        images = content.get("images", [])
        if not images:
            return NodeOutput(success=False, data={}, message="At least one image is required for image publish")
        
        if len(images) > 9:
            return NodeOutput(success=False, data={}, message=f"Too many images: {len(images)}. Maximum: 9")
        
        # 检查频率限制
        rate_check = self._check_rate_limit(account_id, config)
        if not rate_check[0]:
            return NodeOutput(
                success=False,
                data={},
                message=f"Rate limit exceeded. Retry after {rate_check[1]} seconds"
            )
        
        account = self._get_account(account_id)
        if not account:
            return NodeOutput(success=False, data={}, message=f"Account not found: {account_id}")
        
        self._stats["total_publish_attempts"] += 1
        
        # 模拟图片上传+发布
        publish_result = await self._call_weibo_api("statuses/upload", {
            "status": content["text"],
            "pic": images[0],  # 实际项目会上传所有图片
            "access_token": account.access_token
        })
        
        if publish_result.success:
            post = PublishedPost(
                post_id=publish_result.post_id,
                content={**content, "images_uploaded": len(images)},
                published_at=publish_result.published_at or datetime.utcnow(),
                status=PublishStatus.PUBLISHED,
                post_url=publish_result.post_url
            )
            self._publish_history.append(post)
            
            self._stats["successful_publishes"] += 1
            self._record_api_call(account_id)
            
            if ctx.event_bus:
                await ctx.event_bus.emit("weibo:publish_success", {
                    "plugin_id": self.id,
                    "post_id": post.post_id,
                    "account_id": account_id,
                    "type": "image",
                    "image_count": len(images)
                })
            
            return NodeOutput(
                success=True,
                data={
                    "post_id": post.post_id,
                    "post_url": post.post_url,
                    "published_at": post.published_at.isoformat() if post.published_at else None,
                    "stats": {
                        "text_length": len(content.get("text", "")),
                        "image_count": len(images),
                        "has_video": False
                    }
                },
                message=f"Published image weibo with {len(images)} images"
            )
        else:
            self._stats["failed_publishes"] += 1
            return NodeOutput(success=False, data={}, message=f"Publish failed: {publish_result.error_message}")
    
    async def _execute_publish_video(
        self,
        ctx: 'PluginContext',
        config: Dict[str, Any],
        inputs: Dict[str, Any]
    ) -> 'NodeOutput':
        """执行视频发布"""
        content = inputs["content"]
        video_url = content.get("video_url")
        
        if not video_url:
            return NodeOutput(success=False, data={}, message="video_url is required for video publish")
        
        account_id = inputs.get("account_id") or config.get("default_account_id")
        account = self._get_account(account_id)
        
        if not account:
            return NodeOutput(success=False, data={}, message=f"Account not found: {account_id}")
        
        self._stats["total_publish_attempts"] += 1
        
        # 模拟视频发布（通常需要先上传视频再发微博）
        publish_result = await self._call_weibo_api("statuses/upload_url_video", {
            "status": content["text"],
            "video_url": video_url,
            "access_token": account.access_token
        })
        
        if publish_result.success:
            post = PublishedPost(
                post_id=publish_result.post_id,
                content=content,
                published_at=publish_result.published_at or datetime.utcnow(),
                status=PublishStatus.PUBLISHED,
                post_url=publish_result.post_url
            )
            self._publish_history.append(post)
            
            self._stats["successful_publishes"] += 1
            
            if ctx.event_bus:
                await ctx.event_bus.emit("weibo:publish_success", {
                    "plugin_id": self.id,
                    "post_id": post.post_id,
                    "type": "video"
                })
            
            return NodeOutput(
                success=True,
                data={
                    "post_id": post.post_id,
                    "post_url": post.post_url,
                    "published_at": post.published_at.isoformat() if post.published_at else None,
                    "stats": {
                        "text_length": len(content.get("text", "")),
                        "image_count": 0,
                        "has_video": True
                    }
                },
                message="Video weibo published successfully"
            )
        else:
            self._stats["failed_publishes"] += 1
            return NodeOutput(success=False, data={}, message=f"Video publish failed: {publish_result.error_message}")
    
    async def _execute_schedule_publish(
        self,
        ctx: 'PluginContext',
        config: Dict[str, Any],
        inputs: Dict[str, Any]
    ) -> 'NodeOutput':
        """定时发布"""
        scheduled_time_str = inputs.get("scheduled_time")
        content = inputs.get("content", {})
        
        try:
            scheduled_time = datetime.fromisoformat(scheduled_time_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            return NodeOutput(success=False, data={}, message="Invalid scheduled_time format")
        
        if scheduled_time <= datetime.utcnow():
            return NodeOutput(success=False, data={}, message="scheduled_time must be in the future")
        
        # 创建定时任务
        task_id = str(uuid.uuid4())[:8]
        self._scheduled_tasks[task_id] = {
            "task_id": task_id,
            "content": content,
            "scheduled_time": scheduled_time,
            "created_at": datetime.utcnow(),
            "status": "pending",
            "inputs": inputs
        }
        
        self._stats["scheduled_tasks"] += 1
        
        if ctx.event_bus:
            await ctx.event_bus.emit("weibo:scheduled", {
                "plugin_id": self.id,
                "task_id": task_id,
                "scheduled_time": scheduled_time.isoformat(),
                "text_preview": content.get("text", "")[:50]
            })
        
        return NodeOutput(
            success=True,
            data={
                "task_id": task_id,
                "scheduled_time": scheduled_time.isoformat(),
                "status": "scheduled"
            },
            message=f"Weibo scheduled for {scheduled_time.strftime('%Y-%m-%d %H:%M:%S')}"
        )
    
    async def _get_publish_history(self, inputs: Dict[str, Any]) -> 'NodeOutput':
        """获取发布历史"""
        limit = min(inputs.get("limit", 20), 100)
        offset = inputs.get("offset", 0)
        
        history_slice = self._publish_history[offset:offset + limit]
        
        return NodeOutput(
            success=True,
            data={
                "posts": [post.to_dict() for post in history_slice],
                "total": len(self._publish_history),
                "limit": limit,
                "offset": offset
            },
            message=f"Retrieved {len(history_slice)} posts from history"
        )
    
    async def _execute_delete_post(
        self,
        ctx: 'PluginContext',
        inputs: Dict[str, Any]
    ) -> 'NodeOutput':
        """删除微博"""
        post_id = inputs.get("post_id")
        
        # 查找帖子
        post_to_delete = None
        for i, post in enumerate(self._publish_history):
            if post.post_id == post_id:
                post_to_delete = (i, post)
                break
        
        if not post_to_delete:
            return NodeOutput(success=False, data={}, message=f"Post not found: {post_id}")
        
        idx, post = post_to_delete
        
        # 模拟删除API调用
        delete_result = await self._call_weibo_api("statuses/destroy", {"id": post_id})
        
        if delete_result.success:
            post.status = PublishStatus.DELETED
            self._publish_history[idx] = post
            self._stats["deleted_posts"] += 1
            
            if ctx.event_bus:
                await ctx.event_bus.emit("weibo:deleted", {
                    "plugin_id": self.id,
                    "post_id": post_id
                })
            
            return NodeOutput(
                success=True,
                data={"deleted_post_id": post_id},
                message=f"Successfully deleted post {post_id}"
            )
        else:
            return NodeOutput(success=False, data={}, message=f"Delete failed: {delete_result.error_message}")
    
    async def _get_account_info(self, inputs: Dict[str, Any]) -> 'NodeOutput':
        """获取账号信息"""
        account_id = inputs.get("account_id")
        
        if account_id and account_id in self._accounts:
            account = self._accounts[account_id]
        elif not account_id and self._accounts:
            # 返回第一个可用账号
            account = list(self._accounts.values())[0]
        else:
            return NodeOutput(success=False, data={}, message="No accounts available")
        
        return NodeOutput(
            success=True,
            data={
                "account_id": account.account_id,
                "nickname": account.nickname,
                "avatar_url": account.avatar_url,
                "followers_count": account.followers_count,
                "is_active": account.is_active,
                "is_token_valid": account.is_token_valid(),
                "token_expires_at": account.token_expires_at.isoformat() if account.token_expires_at else None
            },
            message=f"Account info retrieved for {account.nickname}"
        )
    
    # ===== 辅助方法 =====
    
    def _get_account(self, account_id: Optional[str]) -> Optional[WeiboAccount]:
        """获取账号"""
        if not account_id:
            return next(iter(self._accounts.values()), None)
        return self._accounts.get(account_id)
    
    def _check_rate_limit(self, account_id: str, config: Dict[str, Any]) -> Tuple[bool, int]:
        """检查频率限制"""
        now = datetime.utcnow()
        hour_ago = now - timedelta(hours=1)
        max_requests = config.get("rate_limit_per_hour", 30)
        
        if account_id not in self._rate_limit_tracker:
            self._rate_limit_tracker[account_id] = []
        
        # 清理过期记录
        self._rate_limit_tracker[account_id] = [
            t for t in self._rate_limit_tracker[account_id]
            if t > hour_ago
        ]
        
        current_count = len(self._rate_limit_tracker[account_id])
        
        if current_count >= max_requests:
            # 计算最早请求的剩余时间
            if self._rate_limit_tracker[account_id]:
                earliest = min(self._rate_limit_tracker[account_id])
                wait_seconds = int((earliest + timedelta(hours=1) - now).total_seconds())
                return False, max(wait_seconds, 60)
            return False, 3600
        
        return True, 0
    
    def _record_api_call(self, account_id: str):
        """记录API调用"""
        if account_id not in self._rate_limit_tracker:
            self._rate_limit_tracker[account_id] = []
        self._rate_limit_tracker[account_id].append(datetime.utcnow())
    
    async def _retry_publish(
        self,
        ctx: 'PluginContext',
        config: Dict[str, Any],
        inputs: Dict[str, Any],
        account: WeiboAccount
    ) -> Optional['NodeOutput']:
        """自动重试发布"""
        max_retries = config.get("retry_count", 3)
        
        for attempt in range(max_retries):
            await asyncio.sleep(1 * (attempt + 1))  # 递增延迟
            
            # 重新尝试发布
            action = inputs.get("action", "publish_text")
            if action == "publish_text":
                result = await self._call_weibo_api("statuses/update", {
                    "status": inputs["content"]["text"],
                    "access_token": account.access_token
                })
                
                if result.success:
                    return NodeOutput(
                        success=True,
                        data={"post_id": result.post_id, "retry_attempt": attempt + 1},
                        message=f"Succeeded on retry #{attempt + 1}"
                    )
        
        return None
    
    async def _call_weibo_api(
        self,
        endpoint: str,
        params: Dict[str, Any]
    ) -> PublishResult:
        """
        调用微博API（模拟）

        实际项目中应该使用requests/httpx调用真实API
        """
        await asyncio.sleep(0.05)  # 模拟网络延迟

        # 模拟API调用 - 默认成功（测试稳定性）
        import random
        post_id = f"{int(time.time())}{random.randint(1000, 9999)}"
        return PublishResult(
            success=True,
            post_id=post_id,
            post_url=f"https://weibo.com/{params.get('uid', 'me')}/{post_id}",
            published_at=datetime.utcnow()
        )


# ===== 辅助类 =====

class MockEventBus:
    """模拟事件总线"""
    
    def __init__(self):
        self.emitted_events = []
    
    async def emit(self, event_type: str, data: dict):
        """发出事件"""
        self.emitted_events.append({
            "type": event_type,
            "data": data,
            "timestamp": datetime.utcnow().isoformat()
        })


@dataclass
class NodeOutput:
    """标准输出格式"""
    success: bool
    data: Dict[str, Any]
    message: str = ""
    execution_time_ms: int = 0


# ===== 本地测试入口 =====

if __name__ == "__main__":
    import asyncio
    
    async def test():
        print("=" * 70)
        print("  Weibo Publisher Plugin - Local Test Mode")
        print("=" * 70)
        
        plugin = WeiboPublisherPlugin()
        
        # Test 1: Plugin info
        print("\n[Test 1] Plugin manifest:")
        manifest = plugin.get_manifest()
        print(f"  ID: {manifest.id}")
        print(f"  Capabilities: {manifest.capabilities}")
        
        # Test 2: Input validation
        print("\n[Test 2] Input validation:")
        valid, msg = await plugin.validate_inputs({
            "action": "publish_text",
            "content": {"text": "Hello Weibo!"}
        })
        print(f"  Valid input: {valid}, Message: {msg}")
        
        valid, msg = await plugin.validate_inputs({
            "action": "invalid_action",
            "content": {"text": "test"}
        })
        print(f"  Invalid action: {valid}, Message: {msg}")
        
        # Test 3: Config validation
        print("\n[Test 3] Config validation:")
        config = {"app_key": "test_key", "app_secret": "test_secret"}
        valid, msg = await plugin.validate_config(config)
        print(f"  Valid config: {valid}, Message: {msg}")
        
        # Test 4: Health check
        print("\n[Test 4] Health check:")
        health = await plugin.health_check()
        print(f"  Status: {health.status}")
        print(f"  Active accounts: {health.details['active_accounts']}")
        
        # Test 5: Publish text
        print("\n[Test 5] Publish text weibo:")
        ctx = plugin.PluginContext()
        ctx.config = {
            **config,
            "default_account_id": "mock_account_001",
            "auto_retry_on_failure": True,
            "retry_count": 2
        }
        
        result = await plugin.execute(ctx, {
            "action": "publish_text",
            "content": {
                "text": "这是我的第一条测试微博！Hello World! #测试 #PluginDevelopment",
                "visibility": "public",
                "topics": ["测试", "PluginDevelopment"]
            }
        })
        print(f"  Success: {result.success}")
        print(f"  Post ID: {result.data.get('post_id', 'N/A')}")
        print(f"  Message: {result.message}")
        
        # Test 6: Publish image
        print("\n[Test 6] Publish image weibo:")
        result = await plugin.execute(ctx, {
            "action": "publish_image",
            "content": {
                "text": "分享一张美图 📸",
                "images": [
                    "https://example.com/image1.jpg",
                    "https://example.com/image2.jpg"
                ],
                "topics": ["摄影", "分享"]
            }
        })
        print(f"  Success: {result.success}")
        print(f"  Image count: {result.data.get('stats', {}).get('image_count', 0)}")
        
        # Test 7: Schedule publish
        print("\n[Test 7] Schedule publish:")
        future_time = (datetime.utcnow() + timedelta(hours=2)).isoformat()
        result = await plugin.execute(ctx, {
            "action": "schedule_publish",
            "content": {"text": "这条微博将在2小时后自动发布"},
            "scheduled_time": future_time
        })
        print(f"  Success: {result.success}")
        print(f"  Task ID: {result.data.get('task_id', 'N/A')}")
        
        # Test 8: Get publish history
        print("\n[Test 8] Get publish history:")
        result = await plugin.execute(ctx, {"action": "get_publish_history"})
        print(f"  Total posts: {result.data.get('total', 0)}")
        print(f"  Retrieved: {len(result.data.get('posts', []))} posts")
        
        # Test 9: Get account info
        print("\n[Test 9] Get account info:")
        result = await plugin.execute(ctx, {"action": "get_account_info"})
        print(f"  Nickname: {result.data.get('nickname', 'N/A')}")
        print(f"  Followers: {result.data.get('followers_count', 0)}")
        
        # Test 10: Delete post
        print("\n[Test 10] Delete post:")
        if plugin._publish_history:
            post_id = plugin._publish_history[0].post_id
            result = await plugin.execute(ctx, {
                "action": "delete_post",
                "post_id": post_id
            })
            print(f"  Success: {result.success}")
            print(f"  Message: {result.message}")
        
        print("\n" + "=" * 70)
        print("  All tests completed!")
        print("=" * 70)
        print("\nNote: This plugin uses mock API calls for demonstration.")
        print("      In production, install dependencies:")
        print("      pip install requests Pillow")
    
    asyncio.run(test())