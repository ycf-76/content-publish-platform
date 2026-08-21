"""
Xiaohongshu Publish Plugin - 小红书发布器插件
将现有 XhsPublishSkill 包装为标准 Platform Plugin
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from app.core.base_interfaces import (
    BasePlatformPlugin,
    PluginContext,
    PublishResult,
    AuthenticationError,
)
from app.core.plugin_types import PluginCategory, PluginStatus


class XiaohongshuPublishPlugin(BasePlatformPlugin):
    """
    小红书平台发布器插件
    
    功能：
    1. 认证管理（Cookie/Token验证）
    2. 内容发布（图文混排、话题标签）
    3. 数据分析（阅读量/点赞/评论统计）
    4. 内容删除
    5. 半自动模式支持（填好内容等待用户手动确认）
    
    底层实现：
    - MCP Client Manager (plugin primary + local fallback)
    - 浏览器扩展方案（无痕，规避风控）
    - 本地 Playwright 兜底方案
    """

    @property
    def plugin_id(self) -> str:
        return "xiaohongshu-publish"

    @property
    def plugin_name(self) -> str:
        return "小红书发布器"

    async def setup(self, ctx: PluginContext) -> None:
        """初始化插件，加载配置和客户端"""
        await super().setup(ctx)
        
        self._log(logging.INFO, "初始化小红书发布器插件")
        
        # 延迟导入避免循环依赖
        try:
            from app.agents.skills.xhs_publish import XhsPublishSkill
            from app.agents.adapters.llm_base import LLMProtocol
            
            # 创建Skill实例（LLM可选，发布不需要LLM）
            self._skill = XhsPublishSkill(llm=None)
            self._log(logging.INFO, "XhsPublishSkill 初始化成功")
            
        except Exception as e:
            self._log(logging.ERROR, f"初始化失败: {e}")
            raise

    async def authenticate(
        self,
        credentials: Dict[str, Any],
        ctx: PluginContext
    ) -> bool:
        """
        验证小红书账号认证状态
        
        Args:
            credentials: 认证凭据
                - cookie_str: 完整Cookie字符串
                - account_id: 账号ID（可选）
                - token: 访问令牌（可选）
            ctx: 插件上下文
            
        Returns:
            认证是否成功
        """
        self._log(logging.INFO, "开始认证...")
        
        try:
            # 检查必要字段
            if not credentials.get("cookie_str"):
                raise AuthenticationError("缺少 Cookie 凭据", platform="xiaohongshu")
            
            # 尝试获取账号信息以验证有效性
            from app.account.service import AccountService
            
            account_id = credentials.get("account_id", "")
            if account_id:
                service = AccountService()
                is_valid = await service.verify_account(account_id)
                
                if is_valid:
                    self._log(logging.INFO, f"认证成功 (account={account_id})")
                    return True
                else:
                    raise AuthenticationError(
                        "账号已失效或未登录",
                        platform="xiaohongshu"
                    )
            else:
                # 无account_id时，仅验证cookie格式
                cookie = credentials["cookie_str"]
                if "web_session" in cookie and "a1" in cookie:
                    self._log(logging.INFO, "Cookie格式验证通过")
                    return True
                else:
                    raise AuthenticationError(
                        "Cookie格式无效或已过期",
                        platform="xiaohongshu"
                    )
                    
        except AuthenticationError:
            raise
        except Exception as e:
            self._log(logging.ERROR, f"认证异常: {e}")
            raise AuthenticationError(
                f"认证过程出错: {str(e)}",
                platform="xiaohongshu"
            )

    async def publish(
        self,
        content: Dict[str, Any],
        config: Dict[str, Any],
        ctx: PluginContext
    ) -> PublishResult:
        """
        发布内容到小红书
        
        Args:
            content: 发布内容
                - title: 笔记标题
                - content: 正文内容（支持Markdown）
                - images_base64: Base64编码的图片列表
                - tags: 话题标签列表（如 ["#AI工具", "#效率提升"]）
                - topic_pool_item_id: 关联的选题池项ID（可选）
            config: 发布配置
                - publish_mode: auto/semi_auto/manual
                - client_preference: plugin_first/local_only
                - timeout_seconds: 超时时间
                - retry_count: 重试次数
            ctx: 插件上下文
                
        Returns:
            PublishResult:
                - success: 是否成功
                - post_id: 平台笔记ID
                - url: 笔记URL
                - message: 状态消息
                - status: success/failed/awaiting_manual/partial_success
        """
        start_time = time.time()
        publish_mode = config.get("publish_mode", "semi_auto")
        
        self._log(
            logging.INFO,
            f"开始发布 | 标题: {content['title'][:20]}... | 模式: {publish_mode}"
        )
        
        try:
            # 构建Skill输入参数
            skill_inputs = {
                "title": content["title"],
                "content": content["content"],
                "images_base64": content.get("images_base64", []),
                "account_id": content.get("account_id", ""),
            }
            
            # 调用底层Skill执行发布
            result = await self._skill.execute(skill_inputs)
            
            execution_time_ms = int((time.time() - start_time) * 1000)
            
            # 解析结果
            if result.get("status") == "success":
                post_id = result.get("post_id", "")
                message = result.get("message", "")
                
                # 检查半自动模式
                is_awaiting_manual = "手动点击" in message
                
                publish_result = PublishResult(
                    success=True,
                    post_id=post_id,
                    url=f"https://www.xiaohongshu.com/explore/{post_id}" if post_id else "",
                    message=message,
                    status="awaiting_manual" if is_awaiting_manual else "success",
                    metadata={
                        "publish_mode": publish_mode,
                        "execution_time_ms": execution_time_ms,
                        "images_count": len(content.get("images_base64", [])),
                        "tags": content.get("tags", []),
                    }
                )
                
                self._log(
                    logging.INFO,
                    f"发布{'完成' if not is_awaiting_manual else '待确认'} "
                    f"| ID: {post_id} | 耗时: {execution_time_ms}ms"
                )
                
                # 发布事件通知
                event_name = (
                    "content:awaiting_manual_confirm" 
                    if is_awaiting_manual 
                    else "content:published"
                )
                await ctx.event_bus.publish(event_name, {
                    "post_id": post_id,
                    "title": content["title"],
                    "plugin_id": self.plugin_id,
                    "execution_time_ms": execution_time_ms,
                }, source_plugin_id=self.plugin_id)
                
                return publish_result
                
            else:
                error_msg = result.get("message", "未知错误")
                self._log(logging.ERROR, f"发布失败: {error_msg}")
                
                await ctx.event_bus.publish("content:publish_failed", {
                    "title": content["title"],
                    "error": error_msg,
                    "plugin_id": self.plugin_id,
                }, source_plugin_id=self.plugin_id)
                
                return PublishResult(
                    success=False,
                    post_id="",
                    url="",
                    message=error_msg,
                    status="failed",
                    metadata={"execution_time_ms": execution_time_ms}
                )
                
        except Exception as e:
            execution_time_ms = int((time.time() - start_time) * 1000)
            error_msg = f"发布异常: {str(e)}"
            
            self._log(logging.ERROR, error_msg, exc_info=True)
            
            await ctx.event_bus.publish("content:publish_failed", {
                "title": content.get("title", ""),
                "error": str(e),
                "plugin_id": self.plugin_id,
            }, source_plugin_id=self.plugin_id)
            
            return PublishResult(
                success=False,
                post_id="",
                url="",
                message=error_msg,
                status="failed",
                metadata={"execution_time_ms": execution_time_ms}
            )

    async def get_analytics(
        self,
        content_id: str,
        ctx: PluginContext
    ) -> Dict[str, Any]:
        """
        获取已发布笔记的数据分析
        
        Args:
            content_id: 笔记ID
            ctx: 插件上下文
            
        Returns:
            分析数据字典：
            - views: 阅读量
            - likes: 点赞数
            - collects: 收藏数
            - comments: 评论数
            - shares: 分享数
            - published_at: 发布时间
        """
        self._log(logging.INFO, f"获取数据分析 | 笔记ID: {content_id}")
        
        try:
            # TODO: 实现真实API调用（需XHS开放接口或爬虫）
            # 目前返回模拟数据结构
            analytics_data = {
                "views": 0,
                "likes": 0,
                "collects": 0,
                "comments": 0,
                "shares": 0,
                "published_at": None,
                "note_id": content_id,
                "_mock": True,  # 标记为模拟数据
            }
            
            self._log(logging.INFO, f"数据分析返回（模拟模式）")
            return analytics_data
            
        except Exception as e:
            self._log(logging.ERROR, f"获取分析数据失败: {e}")
            raise NotImplementedError(f"暂不支持数据分析: {e}")

    async def delete_content(
        self,
        content_id: str,
        ctx: PluginContext
    ) -> bool:
        """
        删除已发布的笔记
        
        Args:
            content_id: 笔记ID
            ctx: 插件上下文
            
        Returns:
            是否删除成功
        """
        self._log(logging.WARNING, f"删除笔记 | ID: {content_id} | ⚠️ 危险操作")
        
        try:
            # TODO: 实现真实删除逻辑
            # 需要通过MCP Client调用浏览器操作或API
            self._log(logging.INFO, f"笔记删除请求已记录（待实现）")
            return False  # 暂不支持
            
        except Exception as e:
            self._log(logging.ERROR, f"删除失败: {e}")
            raise NotImplementedError(f"暂不支持删除内容: {e}")

    async def health_check(self) -> tuple[bool, str]:
        """
        健康检查：验证MCP客户端可用性
        
        Returns:
            (is_healthy, message)
        """
        try:
            # 检查Skill实例是否存在
            if not hasattr(self, '_skill'):
                return False, "XhsPublishSkill 未初始化"
            
            # 尝试获取客户端（不实际连接）
            client = getattr(self._skill, '_get_xhs_client', lambda: None)
            if not client:
                return False, "无法获取MCP客户端实例"
            
            return True, "小红书发布器运行正常（MCP Client Ready）"
            
        except Exception as e:
            return False, f"健康检查失败: {str(e)}"

    async def teardown(self) -> None:
        """清理资源"""
        self._log(logging.INFO, "释放小红书发布器资源...")
        
        if hasattr(self, '_skill'):
            del self._skill
            
        self._log(logging.INFO, "资源释放完成")


# 导出插件类（供PluginManager动态加载使用）
__all__ = ['XiaohongshuPublishPlugin']