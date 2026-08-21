"""
Notification Bot Plugin - 集成类型插件示例

功能特性:
- 多渠道通知支持（邮件、微信、钉钉、Slack、Webhook等）
- Jinja2模板系统，支持动态内容渲染
- 优先级队列与智能路由
- 频率限制与去重机制
- 发送状态实时追踪
- 失败自动重试
- 通知历史与统计

适用场景: 系统告警、用户通知、营销推送、运维监控等
"""

import asyncio
import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Any, Optional, Tuple, Set
from collections import deque


# ===== 基础数据模型 =====

class Priority(Enum):
    """通知优先级"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class NotificationStatus(Enum):
    """通知状态"""
    PENDING = "pending"      # 待发送
    SENT = "sent"            # 已发送
    DELIVERED = "delivered"  # 已送达
    READ = "read"            # 已读
    FAILED = "failed"        # 发送失败
    EXPIRED = "expired"      # 已过期


class ChannelType(Enum):
    """渠道类型"""
    EMAIL = "email"
    WECHAT = "wechat"
    DINGTALK = "dingtalk"
    SLACK = "slack"
    WEBHOOK = "webhook"
    SMS = "sms"


@dataclass
class ChannelConfig:
    """渠道配置"""
    channel_type: str
    enabled: bool = True
    config: Dict[str, Any] = field(default_factory=dict)
    priority: int = 5


@dataclass
class Notification:
    """通知对象"""
    notification_id: str
    title: str
    content: str
    priority: Priority = Priority.NORMAL
    channels: List[str] = field(default_factory=list)
    recipients: List[str] = field(default_factory=list)
    template_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    status: NotificationStatus = NotificationStatus.PENDING
    expire_at: Optional[datetime] = None
    
    def to_dict(self) -> dict:
        result = asdict(self)
        result["priority"] = self.priority.value if isinstance(self.priority, Priority) else self.priority
        result["status"] = self.status.value if isinstance(self.status, NotificationStatus) else self.status
        if isinstance(result["created_at"], datetime):
            result["created_at"] = result["created_at"].isoformat()
        if isinstance(result["expire_at"], datetime):
            result["expire_at"] = result["expire_at"].isoformat()
        return result


@dataclass
class DeliveryRecord:
    """投递记录"""
    record_id: str
    notification_id: str
    channel_type: str
    recipient: str
    status: str
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_count: int = 0


@dataclass
class Template:
    """通知模板"""
    template_id: str
    name: str
    subject_template: str   # 标题模板
    body_template: str      # 内容模板
    channels: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def render(self, context: Dict[str, Any]) -> Tuple[str, str]:
        """
        渲染模板
        
        使用简单的字符串替换（实际项目使用Jinja2）
        """
        subject = self.subject_template
        body = self.body_template
        
        for key, value in context.items():
            placeholder = "{{" + key + "}}"
            subject = subject.replace(placeholder, str(value))
            body = body.replace(placeholder, str(value))
        
        return subject, body


@dataclass
class NotificationStats:
    """通知统计"""
    total_sent: int = 0
    successful: int = 0
    failed: int = 0
    delivered: int = 0
    read: int = 0
    by_channel: Dict[str, Dict[str, int]] = field(default_factory=dict)
    

# ===== 插件主类 =====

class NotificationBotPlugin:
    """
    多渠道通知机器人插件
    
    展示integration类型插件的完整实现，包括：
    - 多系统集成能力
    - 模板引擎集成
    - 异步任务队列
    - 状态追踪与监控
    - 智能路由策略
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
        self.id = "notification-bot"
        self.name = "Notification Bot"
        self.version = "1.0.0"
        
        # 内部状态
        self._channels: Dict[str, ChannelConfig] = {}       # 渠道配置
        self._templates: Dict[str, Template] = {}           # 模板存储
        self._notifications: Dict[str, Notification] = {}   # 通知记录
        self._delivery_records: List[DeliveryRecord] = []   # 投递记录
        self._pending_queue: deque = deque()                # 待处理队列
        self._seen_hashes: Set[str] = set()                 # 去重hash集合
        self._rate_limiter: Dict[str, List[datetime]] = {}  # 频率限制器
        
        # 统计计数器
        self._stats = NotificationStats()
        
        # 初始化默认配置和模板
        self._init_default_config()
        self._init_default_templates()
    
    def _init_default_config(self):
        """初始化默认渠道配置"""
        default_channels = [
            ChannelConfig(
                channel_type="webhook",
                enabled=True,
                config={"url": "https://hooks.slack.com/services/XXX"},
                priority=1
            ),
            ChannelConfig(
                channel_type="email",
                enabled=True,
                config={
                    "smtp_host": "smtp.example.com",
                    "smtp_port": 587,
                    "sender": "noreply@example.com"
                },
                priority=5
            ),
            ChannelConfig(
                channel_type="dingtalk",
                enabled=False,
                config={"webhook_url": "", "secret": ""},
                priority=8
            )
        ]
        
        for ch in default_channels:
            self._channels[ch.channel_type] = ch
    
    def _init_default_templates(self):
        """初始化默认模板"""
        default_templates = [
            Template(
                template_id="default",
                name="Default Template",
                subject_template="{{title}}",
                body_template="{{content}}",
                channels=["webhook", "email"]
            ),
            Template(
                template_id="alert",
                name="Alert Template",
                subject_template="[ALERT] {{title}}",
                body_template="Alert Level: {{priority}}\n\n{{content}}\n\nTime: {{timestamp}}",
                channels=["webhook", "dingtalk", "email"]
            ),
            Template(
                template_id="welcome",
                name="Welcome Template",
                subject_template="Welcome, {{user_name}}!",
                body_template="Dear {{user_name}},\n\n{{content}}\n\nBest regards,\nThe Team",
                channels=["email", "wechat"]
            )
        ]
        
        for tmpl in default_templates:
            self._templates[tmpl.template_id] = tmpl
    
    # ===== 生命周期方法 =====
    
    async def on_load(self):
        """插件加载时调用"""
        print(f"[notification-bot] Plugin loaded with {len(self._channels)} channels")
        print(f"[notification-bot] Available templates: {list(self._templates.keys())}")
        return True
    
    async def on_unload(self):
        """插件卸载时调用"""
        print(f"[notification-bot] Plugin unloaded. Stats: total={self._stats.total_sent}, success={self._stats.successful}")
        return True
    
    async def health_check(self) -> 'HealthStatus':
        """健康检查"""
        active_channels = sum(1 for ch in self._channels.values() if ch.enabled)
        
        return self.HealthStatus(
            status="healthy" if active_channels > 0 else "degraded",
            message=f"Managing {len(self._channels)} channels ({active_channels} active)",
            details={
                "total_channels": len(self._channels),
                "active_channels": active_channels,
                "pending_notifications": len(self._pending_queue),
                "total_sent": self._stats.total_sent,
                "success_rate": f"{(self._stats.successful / max(self._stats.total_sent, 1)) * 100:.1f}%"
            }
        )
    
    def get_manifest(self) -> 'PluginManifest':
        """返回插件清单"""
        return self.PluginManifest(
            id=self.id,
            name=self.name,
            version=self.version,
            description="Multi-channel notification bot with template system and smart routing",
            author="Platform Team <dev@your-platform.com>",
            capabilities=["execute", "send_notification", "manage_templates", "track_delivery"],
            permissions_required=["network:read_write", "storage:read_write", "notification:send"]
        )
    
    # ===== 核心验证方法 =====
    
    async def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, str]:
        """验证输入参数"""
        action = inputs.get("action", "send")
        
        valid_actions = [
            "send", "batch_send", "get_status", "get_templates",
            "create_template", "delete_template", "get_statistics", "retry_failed"
        ]
        
        if action not in valid_actions:
            return False, f"Invalid action '{action}'. Must be one of: {valid_actions}"
        
        if action in ["send", "batch_send"]:
            notification = inputs.get("notification")
            
            if action == "send":
                if not notification:
                    return False, "'notification' object is required for send action"
                
                if not notification.get("title"):
                    return False, "Notification 'title' is required"
                
                if not notification.get("content"):
                    return False, "Notification 'content' is required"
                
                if len(notification.get("title", "")) > 200:
                    return False, "Title too long (max 200 chars)"
                
                if len(notification.get("content", "")) > 5000:
                    return False, "Content too long (max 5000 chars)"
                
                # 验证优先级
                priority = notification.get("priority", "normal")
                valid_priorities = ["low", "normal", "high", "urgent"]
                if priority not in valid_priorities:
                    return False, f"Invalid priority '{priority}'. Must be one of: {valid_priorities}"
            
            elif action == "batch_send":
                notifications = inputs.get("notifications", [])
                if not notifications or len(notifications) == 0:
                    return False, "'notifications' array is required for batch_send"
                
                if len(notifications) > 100:
                    return False, f"Too many notifications (max 100): {len(notifications)}"
        
        elif action == "get_status":
            if not inputs.get("notification_id"):
                return False, "'notification_id' is required for get_status"
        
        elif action == "create_template":
            template = inputs.get("template")
            if not template or not template.get("id") or not template.get("name"):
                return False, "Template must have 'id' and 'name'"
        
        elif action == "delete_template":
            if not inputs.get("template_id"):
                return False, "'template_id' is required for delete_template"
        
        return True, "Inputs validated"
    
    async def validate_config(self, config: Dict[str, Any]) -> Tuple[bool, str]:
        """验证配置"""
        channels = config.get("channels", [])
        if not channels:
            return False, "At least one channel configuration is required"
        
        rate_limit = config.get("rate_limit_per_minute", 10)
        if not (1 <= rate_limit <= 100):
            return False, "rate_limit_per_minute must be between 1 and 100"
        
        dedup_window = config.get("dedup_window_seconds", 300)
        if not (60 <= dedup_window <= 3600):
            return False, "dedup_window_seconds must be between 60 and 3600"
        
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
        - send: 发送单个通知
        - batch_send: 批量发送通知
        - get_status: 获取通知状态
        - get_templates: 获取模板列表
        - create_template: 创建新模板
        - delete_template: 删除模板
        - get_statistics: 获取统计数据
        - retry_failed: 重试失败的通知
        """
        start_time = time.time()
        
        try:
            is_valid, error_msg = await self.validate_inputs(inputs)
            if not is_valid:
                return NodeOutput(success=False, data={}, message=error_msg, execution_time_ms=0)
            
            config = ctx.config or {}
            action = inputs.get("action", "send")
            
            if action == "send":
                result = await self._execute_send(ctx, config, inputs)
            elif action == "batch_send":
                result = await self._execute_batch_send(ctx, config, inputs)
            elif action == "get_status":
                result = await self._get_notification_status(inputs)
            elif action == "get_templates":
                result = await self._get_templates(inputs)
            elif action == "create_template":
                result = await self._create_template(ctx, inputs)
            elif action == "delete_template":
                result = await self._delete_template(ctx, inputs)
            elif action == "get_statistics":
                result = await self._get_statistics()
            elif action == "retry_failed":
                result = await self._retry_failed(ctx, config)
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
    
    async def _execute_send(
        self,
        ctx: 'PluginContext',
        config: Dict[str, Any],
        inputs: Dict[str, Any]
    ) -> 'NodeOutput':
        """执行单个通知发送"""
        notif_data = inputs["notification"]
        
        # 创建通知对象
        notification = Notification(
            notification_id=str(uuid.uuid4())[:12],
            title=notif_data.get("title"),
            content=notif_data.get("content"),
            priority=Priority(notif_data.get("priority", "normal")),
            channels=notif_data.get("channels", []),
            recipients=notif_data.get("recipients", []),
            template_id=notif_data.get("template_id"),
            metadata=notif_data.get("metadata", {})
        )
        
        # 设置过期时间
        expire_str = notif_data.get("expire_at")
        if expire_str:
            try:
                notification.expire_at = datetime.fromisoformat(expire_str.replace('Z', '+00:00'))
            except ValueError:
                pass
        
        # 应用模板
        if notification.template_id and notification.template_id in self._templates:
            template = self._templates[notification.template_id]
            context = {
                **notif_data,
                "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                "notification_id": notification.notification_id
            }
            rendered_title, rendered_content = template.render(context)
            notification.title = rendered_title
            notification.content = rendered_content
        
        # 去重检查
        if config.get("enable_deduplication", True):
            content_hash = hashlib.md5(
                f"{notification.title}:{notification.content}".encode()
            ).hexdigest()[:16]
            
            if content_hash in self._seen_hashes:
                return NodeOutput(
                    success=True,
                    data={
                        "notification_id": notification.notification_id,
                        "status": "duplicate_skipped",
                        "message": "Duplicate notification skipped (same content sent recently)"
                    },
                    message="Notification skipped (duplicate)",
                    execution_time_ms=0
                )
            
            self._seen_hashes.add(content_hash)
        
        # 存储通知
        self._notifications[notification.notification_id] = notification
        
        # 发送到各渠道
        target_channels = notification.channels if notification.channels else [
            ch.channel_type for ch in self._channels.values() if ch.enabled
        ]
        
        sent_channels = []
        failed_channels = []
        
        for channel_type in target_channels:
            if channel_type not in self._channels:
                failed_channels.append(channel_type)
                continue
            
            channel = self._channels[channel_type]
            if not channel.enabled:
                continue
            
            # 频率限制检查
            if not self._check_rate_limit(channel_type, config):
                failed_channels.append(f"{channel_type}(rate_limited)")
                continue
            
            # 发送通知
            success, error = await self._send_to_channel(
                channel_type, channel.config, notification, ctx
            )
            
            if success:
                sent_channels.append(channel_type)
                self._record_api_call(channel_type)
                self._stats.total_sent += 1
                self._stats.successful += 1
                
                # 更新渠道统计
                if channel_type not in self._stats.by_channel:
                    self._stats.by_channel[channel_type] = {"sent": 0, "success": 0, "failed": 0}
                self._stats.by_channel[channel_type]["sent"] += 1
                self._stats.by_channel[channel_type]["success"] += 1
                
                # 记录投递
                record = DeliveryRecord(
                    record_id=str(uuid.uuid4())[:8],
                    notification_id=notification.notification_id,
                    channel_type=channel_type,
                    recipient=", ".join(notification.recipients) if notification.recipients else "default",
                    status="sent",
                    sent_at=datetime.utcnow()
                )
                self._delivery_records.append(record)
                
                # 发送事件
                if ctx.event_bus:
                    await ctx.event_bus.emit("notification:sent", {
                        "plugin_id": self.id,
                        "notification_id": notification.notification_id,
                        "channel": channel_type,
                        "title": notification.title[:50]
                    })
            else:
                failed_channels.append(channel_type)
                self._stats.failed += 1
                
                if channel_type not in self._stats.by_channel:
                    self._stats.by_channel[channel_type] = {"sent": 0, "success": 0, "failed": 0}
                self._stats.by_channel[channel_type]["failed"] += 1
                
                # 记录失败
                record = DeliveryRecord(
                    record_id=str(uuid.uuid4())[:8],
                    notification_id=notification.notification_id,
                    channel_type=channel_type,
                    recipient=", ".join(notification.recipients) if notification.recipients else "default",
                    status="failed",
                    error_message=error
                )
                self._delivery_records.append(record)
                
                if ctx.event_bus:
                    await ctx.event_bus.emit("notification:failed", {
                        "plugin_id": self.id,
                        "notification_id": notification.notification_id,
                        "channel": channel_type,
                        "error": error
                    })
        
        # 更新通知状态
        if sent_channels:
            notification.status = NotificationStatus.SENT
        elif failed_channels:
            notification.status = NotificationStatus.FAILED
        
        overall_success = len(sent_channels) > 0
        
        return NodeOutput(
            success=overall_success,
            data={
                "notification_id": notification.notification_id,
                "status": notification.status.value,
                "sent_channels": sent_channels,
                "failed_channels": failed_channels,
                "statistics": {
                    "total_targeted": len(target_channels),
                    "successful": len(sent_channels),
                    "failed": len(failed_channels)
                }
            },
            message=f"Notification sent to {len(sent_channels)}/{len(target_channels)} channels"
        )
    
    async def _execute_batch_send(
        self,
        ctx: 'PluginContext',
        config: Dict[str, Any],
        inputs: Dict[str, Any]
    ) -> 'NodeOutput':
        """批量发送通知"""
        notifications = inputs.get("notifications", [])
        
        results = []
        success_count = 0
        fail_count = 0
        
        for notif_data in notifications:
            single_input = {"action": "send", "notification": notif_data}
            result = await self._execute_send(ctx, config, single_input)
            
            results.append({
                "notification_id": result.data.get("notification_id", ""),
                "success": result.success,
                "status": result.data.get("status", "")
            })
            
            if result.success:
                success_count += 1
            else:
                fail_count += 1
        
        return NodeOutput(
            success=(fail_count == 0),
            data={
                "batch_results": results,
                "summary": {
                    "total": len(notifications),
                    "successful": success_count,
                    "failed": fail_count
                }
            },
            message=f"Batch completed: {success_count} succeeded, {fail_count} failed"
        )
    
    async def _get_notification_status(self, inputs: Dict[str, Any]) -> 'NodeOutput':
        """获取通知状态"""
        notif_id = inputs.get("notification_id")
        
        if notif_id not in self._notifications:
            return NodeOutput(success=False, data={}, message=f"Notification not found: {notif_id}")
        
        notification = self._notifications[notif_id]
        records = [r.to_dict() if hasattr(r, 'to_dict') else asdict(r)
                   for r in self._delivery_records
                   if r.notification_id == notif_id]
        
        return NodeOutput(
            success=True,
            data={
                "notification": notification.to_dict(),
                "delivery_records": records,
                "record_count": len(records)
            },
            message=f"Retrieved status for notification {notif_id}"
        )
    
    async def _get_templates(self, inputs: Dict[str, Any]) -> 'NodeOutput':
        """获取模板列表"""
        templates_list = []
        for tmpl in self._templates.values():
            tmpl_dict = asdict(tmpl)
            if isinstance(tmpl_dict["created_at"], datetime):
                tmpl_dict["created_at"] = tmpl_dict["created_at"].isoformat()
            templates_list.append(tmpl_dict)
        
        return NodeOutput(
            success=True,
            data={
                "templates": templates_list,
                "count": len(templates_list)
            },
            message=f"Retrieved {len(templates_list)} templates"
        )
    
    async def _create_template(self, ctx: 'PluginContext', inputs: Dict[str, Any]) -> 'NodeOutput':
        """创建新模板"""
        template_data = inputs.get("template", {})
        
        template_id = template_data.get("id", str(uuid.uuid4())[:8])
        
        if template_id in self._templates:
            return NodeOutput(success=False, data={}, message=f"Template already exists: {template_id}")
        
        template = Template(
            template_id=template_id,
            name=template_data.get("name", "Unnamed Template"),
            subject_template=template_data.get("subject_template", "{{title}}"),
            body_template=template_data.get("body_template", "{{content}}"),
            channels=template_data.get("channels", [])
        )
        
        self._templates[template_id] = template
        
        if ctx.event_bus:
            await ctx.event_bus.emit("notification:template_created", {
                "plugin_id": self.id,
                "template_id": template_id,
                "name": template.name
            })
        
        return NodeOutput(
            success=True,
            data={
                "template_id": template_id,
                "name": template.name
            },
            message=f"Template created successfully: {template_id}"
        )
    
    async def _delete_template(self, ctx: 'PluginContext', inputs: Dict[str, Any]) -> 'NodeOutput':
        """删除模板"""
        template_id = inputs.get("template_id")
        
        if template_id not in self._templates:
            return NodeOutput(success=False, data={}, message=f"Template not found: {template_id}")
        
        deleted_template = self._templates.pop(template_id)
        
        return NodeOutput(
            success=True,
            data={
                "deleted_template_id": template_id,
                "name": deleted_template.name
            },
            message=f"Template deleted: {template_id}"
        )
    
    async def _get_statistics(self) -> 'NodeOutput':
        """获取统计数据"""
        return NodeOutput(
            success=True,
            data={
                "overall": {
                    "total_sent": self._stats.total_sent,
                    "successful": self._stats.successful,
                    "failed": self._stats.failed,
                    "delivered": self._stats.delivered,
                    "read": self._stats.read,
                    "success_rate": f"{(self._stats.successful / max(self._stats.total_sent, 1)) * 100:.1f}%"
                },
                "by_channel": self._stats.by_channel,
                "system": {
                    "active_channels": sum(1 for ch in self._channels.values() if ch.enabled),
                    "total_templates": len(self._templates),
                    "pending_in_queue": len(self._pending_queue),
                    "cached_hashes": len(self._seen_hashes)
                }
            },
            message="Statistics retrieved"
        )
    
    async def _retry_failed(self, ctx: 'PluginContext', config: Dict[str, Any]) -> 'NodeOutput':
        """重试失败的通知"""
        max_retries = config.get("max_retries", 3)
        retried = 0
        successful = 0
        
        failed_records = [
            r for r in self._delivery_records
            if r.status == "failed" and r.retry_count < max_retries
        ]
        
        for record in failed_records[:10]:  # 限制每次最多重试10条
            if record.notification_id not in self._notifications:
                continue
            
            notification = self._notifications[record.notification_id]
            
            # 重新发送
            success, error = await self._send_to_channel(
                record.channel_type,
                self._channels.get(record.channel_type, ChannelConfig(channel_type=record.channel_type)).config,
                notification,
                ctx
            )
            
            record.retry_count += 1
            
            if success:
                record.status = "sent"
                record.sent_at = datetime.utcnow()
                successful += 1
            else:
                record.error_message = error
            
            retried += 1
        
        return NodeOutput(
            success=True,
            data={
                "retried": retried,
                "successful": successful,
                "still_failed": retried - successful
            },
            message=f"Retried {retried} notifications, {successful} succeeded"
        )
    
    # ===== 辅助方法 =====
    
    async def _send_to_channel(
        self,
        channel_type: str,
        channel_config: Dict[str, Any],
        notification: Notification,
        ctx: 'PluginContext'
    ) -> Tuple[bool, Optional[str]]:
        """
        发送通知到指定渠道（模拟）
        
        实际项目中这里会调用真实的API
        """
        await asyncio.sleep(0.02)  # 模拟网络延迟
        
        # 模拟95%成功率
        import random
        if random.random() > 0.05:  # 95%成功
            return True, None
        else:
            error_messages = {
                "email": "SMTP connection timeout",
                "wechat": "WeChat API error: access_token expired",
                "dingtalk": "DingTalk webhook rejected",
                "slack": "Slack API rate limit exceeded",
                "webhook": "Webhook endpoint returned 500",
                "sms": "SMS gateway unavailable"
            }
            return False, error_messages.get(channel_type, "Unknown error")
    
    def _check_rate_limit(self, channel_type: str, config: Dict[str, Any]) -> bool:
        """检查频率限制"""
        now = datetime.utcnow()
        limit = config.get("rate_limit_per_minute", 10)
        window_start = now - timedelta(minutes=1)
        
        if channel_type not in self._rate_limiter:
            self._rate_limiter[channel_type] = []
        
        # 清理过期记录
        self._rate_limiter[channel_type] = [
            t for t in self._rate_limiter[channel_type]
            if t > window_start
        ]
        
        current_count = len(self._rate_limiter[channel_type])
        return current_count < limit
    
    def _record_api_call(self, channel_type: str):
        """记录API调用"""
        if channel_type not in self._rate_limiter:
            self._rate_limiter[channel_type] = []
        self._rate_limiter[channel_type].append(datetime.utcnow())


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
        print("  Notification Bot Plugin - Local Test Mode")
        print("=" * 70)
        
        plugin = NotificationBotPlugin()
        
        # Test 1: Plugin info
        print("\n[Test 1] Plugin manifest:")
        manifest = plugin.get_manifest()
        print(f"  ID: {manifest.id}")
        print(f"  Capabilities: {manifest.capabilities}")
        
        # Test 2: Input validation
        print("\n[Test 2] Input validation:")
        valid, msg = await plugin.validate_inputs({
            "action": "send",
            "notification": {
                "title": "Test Alert",
                "content": "This is a test notification"
            }
        })
        print(f"  Valid input: {valid}, Message: {msg}")
        
        valid, msg = await plugin.validate_inputs({"action": "invalid"})
        print(f"  Invalid action: {valid}, Message: {msg}")
        
        # Test 3: Config validation
        print("\n[Test 3] Config validation:")
        config = {"channels": [{"channel_type": "email"}]}
        valid, msg = await plugin.validate_config(config)
        print(f"  Valid config: {valid}, Message: {msg}")
        
        # Test 4: Health check
        print("\n[Test 4] Health check:")
        health = await plugin.health_check()
        print(f"  Status: {health.status}")
        print(f"  Active channels: {health.details['active_channels']}")
        
        # Test 5: Send notification
        print("\n[Test 5] Send notification:")
        ctx = plugin.PluginContext()
        ctx.config = {
            "channels": [{"channel_type": "webhook"}, {"channel_type": "email"}],
            "enable_deduplication": True,
            "rate_limit_per_minute": 30
        }
        
        result = await plugin.execute(ctx, {
            "action": "send",
            "notification": {
                "title": "System Alert",
                "content": "Server CPU usage exceeded 90% threshold",
                "priority": "high",
                "channels": ["webhook", "email"],
                "recipients": ["admin@example.com", "ops-team@example.com"]
            }
        })
        print(f"  Success: {result.success}")
        print(f"  Notification ID: {result.data.get('notification_id', 'N/A')}")
        print(f"  Sent to: {result.data.get('sent_channels', [])}")
        print(f"  Message: {result.message}")
        
        # Test 6: Send with template
        print("\n[Test 6] Send with template:")
        result = await plugin.execute(ctx, {
            "action": "send",
            "notification": {
                "title": "Welcome Message",
                "content": "Welcome to our platform!",
                "template_id": "welcome",
                "user_name": "John Doe"
            }
        })
        print(f"  Success: {result.success}")
        print(f"  Rendered title: {ctx.storage.get('last_title', 'N/A')}")
        
        # Test 7: Get templates
        print("\n[Test 7] Get templates:")
        result = await plugin.execute(ctx, {"action": "get_templates"})
        print(f"  Templates count: {result.data.get('count', 0)}")
        for t in result.data.get('templates', [])[:3]:
            print(f"    - {t['name']} ({t['template_id']})")
        
        # Test 8: Create custom template
        print("\n[Test 8] Create custom template:")
        result = await plugin.execute(ctx, {
            "action": "create_template",
            "template": {
                "id": "custom_marketing",
                "name": "Marketing Template",
                "subject_template": "[PROMO] {{title}}",
                "body_template": "Special offer just for you!\n\n{{content}}\n\nUse code: {{promo_code}}",
                "channels": ["email", "sms"]
            }
        })
        print(f"  Success: {result.success}")
        print(f"  Template ID: {result.data.get('template_id', 'N/A')}")
        
        # Test 9: Batch send
        print("\n[Test 9] Batch send:")
        batch_notifications = [
            {"title": "Batch Item 1", "content": "First item"},
            {"title": "Batch Item 2", "content": "Second item"},
            {"title": "Batch Item 3", "content": "Third item"}
        ]
        result = await plugin.execute(ctx, {
            "action": "batch_send",
            "notifications": batch_notifications
        })
        summary = result.data.get("summary", {})
        print(f"  Total: {summary.get('total', 0)}, "
              f"Success: {summary.get('successful', 0)}, "
              f"Failed: {summary.get('failed', 0)}")
        
        # Test 10: Get statistics
        print("\n[Test 10] Get statistics:")
        result = await plugin.execute(ctx, {"action": "get_statistics"})
        stats = result.data.get("overall", {})
        print(f"  Total sent: {stats.get('total_sent', 0)}")
        print(f"  Success rate: {stats.get('success_rate', 'N/A')}")
        print(f"  By channel: {list(result.data.get('by_channel', {}).keys())}")
        
        # Test 11: Get notification status
        print("\n[Test 11] Get notification status:")
        if plugin._notifications:
            first_notif_id = list(plugin._notifications.keys())[0]
            result = await plugin.execute(ctx, {
                "action": "get_status",
                "notification_id": first_notif_id
            })
            print(f"  Status: {result.data.get('notification', {}).get('status', 'N/A')}")
            print(f"  Records: {result.data.get('record_count', 0)}")
        
        # Test 12: Retry failed
        print("\n[Test 12] Retry failed notifications:")
        result = await plugin.execute(ctx, {"action": "retry_failed"})
        retry_stats = result.data
        print(f"  Retried: {retry_stats.get('retried', 0)}, "
              f"Success: {retry_stats.get('successful', 0)}")
        
        print("\n" + "=" * 70)
        print("  All tests completed!")
        print("=" * 70)
        print("\nNote: This plugin uses mock API calls for demonstration.")
        print("      In production, install dependencies:")
        print("      pip install aiohttp jinja2")
    
    asyncio.run(test())