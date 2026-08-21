"""
微信机器人核心引擎（基于 iLink 协议）

职责:
- 机器人生命周期管理（启动/停止/重启）
- 状态维护和查询
- 二维码获取和管理
- 消息收发控制（手动模式）
- 对接后端业务逻辑

设计原则:
- 注册表模式，按平台用户ID隔离，支持多用户并发
- 混合架构：Client处理底层通信 + Engine管理生命周期
- 异步设计，支持并发操作
- 错误恢复机制

基于: SiverKing/weixin-ClawBot-API 项目核心思路
"""

import asyncio
import base64
import json
import logging
import os
import time
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, Callable, Awaitable
from dataclasses import dataclass, field

from .wechat_ilink_client import WeChatILinkClient, LoginCredentials, BASE_URL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_CREDENTIALS_DIR = os.path.dirname(__file__)


class BotStatus(Enum):
    """机器人状态枚举"""
    STOPPED = "stopped"              # 已停止
    STARTING = "starting"            # 启动中
    WAITING_QR = "waiting_qr"        # 等待扫码
    SCANNED = "scanned"              # 已扫描，等待确认
    CONFIRMING = "confirming"        # 登录确认中
    LOGGED_IN = "logged_in"          # 已登录
    ERROR = "error"                  # 错误状态


@dataclass
class BotState:
    """机器人当前状态"""
    status: BotStatus = BotStatus.STOPPED
    wxid: str = ""                   # 微信ID (ilink_user_id)
    nickname: str = ""               # 微信昵称 (ilink_bot_id)
    qr_code_base64: str = ""         # Base64 编码的二维码图片
    login_time: Optional[datetime] = None  # 登录时间
    start_time: Optional[datetime] = None  # 启动时间
    error_message: str = ""          # 错误信息
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于API响应）"""
        qr_data = ""
        if self.qr_code_base64:
            qr_data = f"data:image/png;base64,{self.qr_code_base64}"
        
        return {
            "status": self.status.value,
            "wxid": self.wxid,
            "nickname": self.nickname,
            "login_time": self.login_time.isoformat() if self.login_time else None,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "uptime": str(datetime.now() - self.start_time) if self.start_time else None,
            "error": self.error_message,
            "has_qrcode": bool(self.qr_code_base64),
            "qr_code_base64": qr_data,
        }


class WeChatBotEngine:
    """
    微信机器人引擎（每个平台用户一个实例）
    
    核心功能:
    - 生命周期管理（启动/停止）
    - 状态查询和维护
    - 二维码管理
    - 消息发送接口（手动模式）
    - 凭证持久化（按用户隔离）
    
    使用示例:
        engine = get_wechat_engine(user_id)
        
        await engine.start()           # 启动服务
        status = engine.state          # 查询状态
        qr = await engine.get_qrcode() # 获取二维码
        
        await engine.send_message("filehelper", "Hello")  # 发送消息
        await engine.stop()            # 停止服务
    """
    
    def __init__(self, platform_user_id: str):
        self._platform_user_id = platform_user_id
        self._credentials_file = os.path.join(
            _CREDENTIALS_DIR, f".wechat_credentials_{platform_user_id}.json"
        )
        self._client: Optional[WeChatILinkClient] = None
        self._state: BotState = BotState()
        self._running: bool = False
        self._background_task: Optional[asyncio.Task] = None
        self._message_handler: Optional[Callable] = None
        self._status_callbacks: list = []
        self._message_callbacks: list = []
        self._recent_messages: list = []
        self._MAX_RECENT_MESSAGES = 50
        
        logger.info(f"[WeChatBotEngine] 引擎实例已创建 (user={platform_user_id})")
    
    @property
    def state(self) -> BotState:
        """获取当前状态"""
        return self._state
    
    @property
    def is_running(self) -> bool:
        """是否正在运行"""
        return self._running
    
    @property
    def is_logged_in(self) -> bool:
        """是否已登录"""
        return self._state.status == BotStatus.LOGGED_IN and self._client and self._client.is_logged_in
    
    async def start(self):
        """
        启动服务
        
        流程:
        1. 尝试复用已保存的凭证（免扫码）
        2. 如果凭证无效或不存在，走二维码扫码流程
        """
        if self._running:
            logger.warning("[WeChatBotEngine] 服务已在运行中")
            return
        
        logger.info("[WeChatBotEngine] 正在启动服务...")
        
        try:
            self._update_status(BotStatus.STARTING)
            
            # 创建客户端
            self._client = WeChatILinkClient()
            
            # ===== 优先尝试复用已保存的凭证 =====
            saved_creds = self._load_credentials()
            if saved_creds and saved_creds.is_valid:
                logger.info(f"[WeChatBotEngine] 发现已保存的凭证，尝试复用...")
                self._client._credentials = saved_creds
                
                # 验证凭证是否仍然有效（尝试 getconfig）
                try:
                    config = await self._client._api_post(
                        "ilink/bot/getconfig",
                        {
                            "ilink_user_id": "",
                            "context_token": "",
                            "base_info": self._client._base_info(),
                        },
                        token=saved_creds.bot_token,
                        base_url=saved_creds.base_url
                    )
                    # 如果没报错，说明凭证有效
                    logger.info(f"[WeChatBotEngine] ✅ 凭证有效，直接复用! 无需扫码!")
                    
                    self._state.wxid = saved_creds.ilink_user_id
                    self._state.nickname = saved_creds.ilink_bot_id
                    self._state.login_time = datetime.now()
                    self._state.start_time = datetime.now()
                    self._update_status(BotStatus.LOGGED_IN)
                    
                    # 启动后台任务监听消息
                    self._running = True
                    self._background_task = asyncio.create_task(self._background_loop())
                    
                    logger.info(f"[WeChatBotEngine] ✅ 服务已启动! 直接进入已登录状态，无需扫码")
                    return
                    
                except Exception as e:
                    logger.warning(f"[WeChatBotEngine] 已保存凭证无效: {e}，走二维码流程")
                    self._client._credentials = None
            
            # ===== 二维码扫码流程 =====
            logger.info("[WeChatBotEngine] 正在获取登录二维码...")
            qr_result = await self._client.get_qrcode()
            
            # 缓存二维码结果（供后台轮询使用）
            self._client._last_qr_result = qr_result
            logger.debug(f"[WeChatBotEngine] 二维码已缓存: {qr_result.qrcode[:30]}...")
            
            # 处理二维码图片
            logger.info(f"[WeChatBotEngine] 正在处理二维码图片 (qrcode_image_content长度: {len(qr_result.qrcode_image_content) if qr_result.qrcode_image_content else 0})")
            qr_image_data = await self._process_qr_image(qr_result)
            
            # 更新状态
            self._state.qr_code_base64 = qr_image_data
            self._state.start_time = datetime.now()
            logger.info(f"[WeChatBotEngine] 二维码图片处理完成 (长度: {len(qr_image_data) if qr_image_data else 0})")
            self._update_status(BotStatus.WAITING_QR)
            
            # 启动后台任务监听扫码和消息
            self._running = True
            self._background_task = asyncio.create_task(self._background_loop())
            
            logger.info(f"[WeChatBotEngine] ✅ 服务已启动! 等待扫码... QR={qr_result.qrcode[:20]}...")
            
        except Exception as e:
            error_msg = f"启动失败: {str(e)}"
            logger.error(f"[WeChatBotEngine] ❌ {error_msg}")
            self._state.error_message = error_msg
            self._update_status(BotStatus.ERROR)
            raise
    
    async def stop(self):
        """
        停止服务
        
        流程:
        1. 设置停止标志
        2. 取消后台任务
        3. 关闭客户端连接
        4. 清理运行状态（保留凭证以便下次复用）
        """
        if not self._running:
            logger.warning("[WeChatBotEngine] 服务未运行")
            return
        
        logger.info("[WeChatBotEngine] 正在停止服务...")
        
        try:
            self._running = False
            
            # 取消后台任务
            if self._background_task and not self._background_task.done():
                self._background_task.cancel()
                try:
                    await self._background_task
                except asyncio.CancelledError:
                    pass
            
            # 关闭客户端
            if self._client:
                await self._client.close()
                self._client = None
            
            # 清理运行状态，但保留凭证
            self._state.status = BotStatus.STOPPED
            self._state.qr_code_base64 = ""
            self._state.error_message = ""
            # wxid/nickname/login_time 保留，方便前端显示"上次连接"
            
            self._update_status(BotStatus.STOPPED)
            
            logger.info("[WeChatBotEngine] ✅ 服务已停止（凭证已保留，下次可免扫码）")
            
        except Exception as e:
            logger.error(f"[WeChatBotEngine] ❌ 停止时出错: {e}")
    
    async def get_qrcode(self) -> Dict[str, Any]:
        """
        获取二维码信息（用于API返回）
        
        Returns:
            dict: {
                "qrcode": "data:image/png;base64,...",  // 或空字符串
                "status": "waiting_qr",
                "expires_in": 120
            }
        """
        logger.debug(f"[WeChatBotEngine] get_qrcode called - running={self._running}, status={self._state.status.value}, has_qr={bool(self._state.qr_code_base64)}")
        
        if not self._running or self._state.status != BotStatus.WAITING_QR:
            return {
                "success": False,
                "qrcode": "",
                "status": self._state.status.value,
                "message": "暂无二维码"
            }
        
        qrcode_data = f"data:image/png;base64,{self._state.qr_code_base64}" if self._state.qr_code_base64 else ""
        logger.info(f"[WeChatBotEngine] 返回二维码数据 (长度: {len(qrcode_data)})")
        
        return {
            "success": True,
            "qrcode": qrcode_data,
            "status": self._state.status.value,
            "expires_in": 120
        }
    
    async def send_message(self, to_wxid: str, content: str) -> Dict[str, Any]:
        """
        主动发送消息（手动模式）
        
        Args:
            to_wxid: 目标微信ID（如 "filehelper"）
            content: 消息内容
            
        Returns:
            dict: {"success": bool, "message": str}
        """
        if not self._client or not self._client.is_logged_in:
            error_msg = f"机器人未登录，无法发送消息 (running={self._running}, status={self._state.status.value})"
            logger.error(f"[WeChatBotEngine] {error_msg}")
            raise Exception(error_msg)
        
        if not to_wxid or not content:
            raise Exception("参数错误: to_wxid 和 content 不能为空")
        
        logger.info(f"[WeChatBotEngine] 📤 发送消息 → {to_wxid}: {content[:50]}...")
        
        # 尝试从缓存获取 context_token
        context_token = self._client.get_context_token(to_wxid)
        
        if not context_token:
            # 如果没有缓存的 token，尝试使用默认值或报错
            logger.warning(f"[WeChatBotEngine] ⚠️ 未找到 {to_wxid} 的 context_token")
            # 对于 filehelper 等特殊ID，可能需要特殊处理
            # 这里先尝试发送，让底层API处理错误
        
        success = await self._client.send_text(to_wxid, context_token or "", content)
        
        if success:
            result = {"success": True, "message": "消息发送成功"}
            logger.info(f"[WeChatBotEngine] ✅ 发送成功! to={to_wxid}")
        else:
            result = {"success": False, "message": "消息发送失败"}
            logger.error(f"[WeChatBotEngine] ❌ 发送失败! to={to_wxid}")
        
        return result
    
    def on_status_change(self, callback: Callable[[BotState], Awaitable[None]]):
        """注册状态变化回调"""
        self._status_callbacks.append(callback)
    
    async def _notify_status_change(self):
        """通知所有注册的状态变化回调"""
        for callback in self._status_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(self._state)
                else:
                    callback(self._state)
            except Exception as e:
                logger.error(f"[WeChatBotEngine] 状态回调执行出错: {e}")
    
    # ==================== 凭证持久化 ====================
    
    def _save_credentials(self, creds: LoginCredentials):
        """保存凭证到文件（下次免扫码）"""
        try:
            data = {
                "bot_token": creds.bot_token,
                "base_url": creds.base_url,
                "ilink_bot_id": creds.ilink_bot_id,
                "ilink_user_id": creds.ilink_user_id,
                "saved_at": datetime.now().isoformat(),
            }
            with open(self._credentials_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            logger.info(f"[WeChatBotEngine] 凭证已保存到 {self._credentials_file}")
        except Exception as e:
            logger.warning(f"[WeChatBotEngine] 保存凭证失败: {e}")
    
    def _load_credentials(self) -> Optional[LoginCredentials]:
        """从文件加载已保存的凭证"""
        try:
            if not os.path.exists(self._credentials_file):
                return None
            with open(self._credentials_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            if not data.get("bot_token"):
                return None
            
            creds = LoginCredentials(
                bot_token=data["bot_token"],
                base_url=data.get("base_url", BASE_URL),
                ilink_bot_id=data.get("ilink_bot_id", ""),
                ilink_user_id=data.get("ilink_user_id", ""),
            )
            
            saved_at = data.get("saved_at", "")
            logger.info(f"[WeChatBotEngine] 已加载保存的凭证 (保存时间: {saved_at})")
            return creds
            
        except Exception as e:
            logger.warning(f"[WeChatBotEngine] 加载凭证失败: {e}")
            return None
    
    def _clear_credentials(self):
        """清除已保存的凭证"""
        try:
            if os.path.exists(self._credentials_file):
                os.remove(self._credentials_file)
                logger.info(f"[WeChatBotEngine] 凭证文件已删除")
        except Exception as e:
            logger.warning(f"[WeChatBotEngine] 删除凭证失败: {e}")
    
    def _update_status(self, new_status: BotStatus):
        """更新状态并通知回调"""
        old_status = self._state.status
        self._state.status = new_status
        
        if old_status != new_status:
            logger.info(f"[WeChatBotEngine] 状态变更: {old_status.value} → {new_status.value}")
            # 异步通知（避免阻塞）
            asyncio.create_task(self._notify_status_change())
    
    async def _try_reuse_saved_credentials(self) -> bool:
        """
        尝试复用已保存的凭证
        
        在以下场景调用:
        - 二维码过期时
        - already_connected 无凭证时
        - 需要刷新二维码前
        
        Returns:
            bool: True=凭证有效并已成功复用, False=凭证无效或不存在
        """
        saved_creds = self._load_credentials()
        if not saved_creds or not saved_creds.is_valid:
            logger.info("[WeChatBotEngine] 无已保存的凭证可复用")
            return False
        
        logger.info("[WeChatBotEngine] 发现已保存凭证，尝试验证...")
        
        if not self._client:
            self._client = WeChatILinkClient()
        
        self._client._credentials = saved_creds
        
        try:
            config = await self._client._api_post(
                "ilink/bot/getconfig",
                {
                    "ilink_user_id": "",
                    "context_token": "",
                    "base_info": self._client._base_info(),
                },
                token=saved_creds.bot_token,
                base_url=saved_creds.base_url
            )
            
            logger.info("[WeChatBotEngine] ✅ 已保存凭证验证通过，直接复用!")
            
            self._state.wxid = saved_creds.ilink_user_id
            self._state.nickname = saved_creds.ilink_bot_id
            self._state.login_time = datetime.now()
            self._state.qr_code_base64 = ""
            self._update_status(BotStatus.LOGGED_IN)
            
            self._save_credentials(saved_creds)
            
            return True
            
        except Exception as e:
            logger.warning(f"[WeChatBotEngine] 已保存凭证验证失败: {e}")
            self._client._credentials = None
            self._clear_credentials()
            return False

    async def _process_qr_image(self, qr_result) -> str:
        """
        处理二维码图片数据
        
        Args:
            qr_result: QRCodeResult 对象
            
        Returns:
            str: Base64编码的图片数据（不含前缀）
        """
        content = qr_result.qrcode_image_content
        
        if not content:
            # 如果服务器没返回图片，使用QR字符串自行生成
            logger.info("[WeChatBotEngine] 服务器未返回图片，自行生成二维码...")
            return await self._generate_qr_from_string(qr_result.qrcode)
        
        # 处理不同格式
        if content.startswith("data:image/"):
            # Data URL格式: data:image/png;base64,xxxxx
            try:
                _, b64_data = content.split(",", 1)
                return b64_data
            except Exception as e:
                logger.warning(f"[WeChatBotEngine] Data URL解析失败: {e}，降级到自行生成")
                return await self._generate_qr_from_string(qr_result.qrcode)
        
        elif content.startswith("http"):
            # URL格式 - 使用URL生成二维码（这是微信登录链接！）
            logger.info(f"[WeChatBotEngine] 收到URL格式的二维码，使用URL生成: {content[:60]}...")
            return await self._generate_qr_from_string(content)
        
        elif content.startswith("<svg"):
            # SVG格式 - 需要转换（暂不实现，降级）
            logger.warning(f"[WeChatBotEngine] 收到SVG格式的二维码，降级到自行生成")
            return await self._generate_qr_from_string(qr_result.qrcode)
        
        else:
            # 纯Base64格式
            return content
    
    async def _generate_qr_from_string(self, qr_string: str) -> str:
        """
        从字符串生成二维码图片
        
        Args:
            qr_string: 二维码内容
            
        Returns:
            str: Base64编码的PNG图片
        """
        try:
            import qrcode
            from PIL import Image
            import io
            
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(qr_string)
            qr.make(fit=True)
            
            img = qr.make_image(fill_color="black", back_color="white")
            
            # 转换为Base64
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
            
            logger.debug(f"[WeChatBotEngine] 二维码自行生成成功 ({len(img_base64)} chars)")
            return img_base64
            
        except ImportError:
            logger.error("[WeChatBotEngine] 缺少 qrcode/Pillow 库，无法生成二维码")
            return ""
        except Exception as e:
            logger.error(f"[WeChatBotEngine] 二维码生成失败: {e}")
            return ""
    
    async def _background_loop(self):
        """
        后台主循环
        
        功能:
        1. 监听扫码状态变化
        2. 扫码成功后自动完成登录
        3. 开始监听消息（如果配置了handler）
        """
        logger.info("[WeChatBotEngine-Background] 🔄 后台循环已启动")
        
        try:
            if self._state.status == BotStatus.WAITING_QR:
                # 阶段1: 等待扫码登录
                await self._wait_for_login()
            
            if self._state.status == BotStatus.LOGGED_IN:
                # 阶段2: 已登录，开始监听消息
                logger.info("[WeChatBotEngine-Background] ✅ 进入消息监听模式")
                await self._listen_messages()
                    
        except asyncio.CancelledError:
            logger.info("[WeChatBotEngine-Background] 后台循环被取消")
        except Exception as e:
            logger.error(f"[WeChatBotEngine-Background] ❌ 后台循环出错: {e}")
            self._state.error_message = str(e)
            self._update_status(BotStatus.ERROR)
        finally:
            logger.info("[WeChatBotEngine-Background] 后台循环已结束")
    
    async def _wait_for_login(self):
        """
        等待扫码登录
        
        关键修复: 直接轮询已获取的二维码状态，
        不再重新调用 login_with_qrcode()（它会生成新二维码导致冲突）
        """
        logger.info("[WeChatBotEngine-Background] ⏳ 等待扫码登录...")
        
        deadline = time.time() + 180  # 3分钟超时
        scanned_printed = False
        already_connected_retries = 0
        MAX_ALREADY_CONNECTED_RETRIES = 10
        
        try:
            # 从客户端获取当前二维码token（start()时已获取）
            if not hasattr(self._client, '_last_qr_result') or not self._client._last_qr_result:
                # 如果没有缓存，尝试从状态中的base64反推（不推荐，但作为后备方案）
                logger.warning("[WeChatBotEngine-Background] ⚠️ 未找到缓存的二维码信息")
                # 这种情况应该不会发生，因为start()一定会先获取二维码
                raise Exception("内部错误: 缺少二维码信息")
            
            qrcode_token = self._client._last_qr_result.qrcode
            base_url = getattr(self._client._last_qr_result, 'base_url', None) or BASE_URL
            
            logger.info(f"[WeChatBotEngine-Background] 开始轮询二维码状态: {qrcode_token[:30]}...")
            
            while True:
                if time.time() >= deadline:
                    raise TimeoutError("登录超时")
                
                if not self._running:
                    logger.info("[WeChatBotEngine-Background] 服务已停止")
                    return
                
                # 轮询状态
                result = await self._client.poll_login_status(qrcode_token, base_url=base_url)
                state = result.get("status", "unknown") if isinstance(result, dict) else str(result)
                
                now = datetime.now().strftime('%H:%M:%S')
                logger.info(f"[{now}] [WeChatBotEngine-Background] 轮询结果: success={result.get('success')}, has_creds={bool(result.get('credentials'))}, already_connected={result.get('already_connected')}, scanned={result.get('scanned')}, expired={result.get('expired')}, status={state}")
                
                if result.get("success") and result.get("credentials"):
                    creds = result["credentials"]
                    
                    # 更新客户端凭证
                    self._client._credentials = creds
                    
                    # 登录成功
                    self._state.wxid = creds.ilink_user_id
                    self._state.nickname = creds.ilink_bot_id
                    self._state.login_time = datetime.now()
                    self._update_status(BotStatus.LOGGED_IN)
                    
                    # 保存凭证到文件（下次免扫码）
                    self._save_credentials(creds)
                    
                    logger.info(f"[{now}] [WeChatBotEngine-Background] ✅✅✅ 登录成功!")
                    logger.info(f"[{now}] [WeChatBotEngine-Background]   wxid: {self._state.wxid[:30]}...")
                    logger.info(f"[{now}] [WeChatBotEngine-Background]   nickname: {self._state.nickname}")
                    logger.info(f"[{now}] [WeChatBotEngine-Background]   token: {creds.bot_token[:30]}...")
                    return
                    
                elif result.get("already_connected"):
                    raw = result.get("raw_response", {})
                    raw_token = raw.get("bot_token", "")
                    
                    if raw_token:
                        logger.info(f"[{now}] [WeChatBotEngine-Background] ✅ already_connected 携带 bot_token，提取凭证")
                        creds = LoginCredentials(
                            bot_token=raw_token,
                            base_url=raw.get("baseurl") or raw.get("base_url") or base_url or BASE_URL,
                            ilink_bot_id=raw.get("ilink_bot_id", ""),
                            ilink_user_id=raw.get("ilink_user_id", ""),
                        )
                        self._client._credentials = creds
                        self._state.wxid = creds.ilink_user_id
                        self._state.nickname = creds.ilink_bot_id
                        self._state.login_time = datetime.now()
                        self._update_status(BotStatus.LOGGED_IN)
                        self._save_credentials(creds)
                        logger.info(f"[{now}] [WeChatBotEngine-Background] ✅✅✅ 登录成功 (from already_connected)!")
                        return
                    elif self._client._credentials and self._client._credentials.is_valid:
                        self._state.wxid = self._client._credentials.ilink_user_id
                        self._state.nickname = self._client._credentials.ilink_bot_id
                        self._state.login_time = datetime.now()
                        self._update_status(BotStatus.LOGGED_IN)
                        self._save_credentials(self._client._credentials)
                        logger.info(f"[{now}] [WeChatBotEngine-Background] 已连接状态，复用Token")
                        return
                    else:
                        already_connected_retries += 1
                        if already_connected_retries >= MAX_ALREADY_CONNECTED_RETRIES:
                            logger.warning(f"[{now}] [WeChatBotEngine-Background] binded_redirect 多次无凭证，尝试复用已保存凭证...")
                            reused = await self._try_reuse_saved_credentials()
                            if reused:
                                logger.info(f"[{now}] [WeChatBotEngine-Background] ✅ 复用已保存凭证成功! 无需重新扫码")
                                return
                            logger.warning(f"[{now}] [WeChatBotEngine-Background] 凭证也无效，刷新二维码重试")
                            break
                        logger.info(f"[{now}] [WeChatBotEngine-Background] binded_redirect 无凭证，继续轮询 ({already_connected_retries}/{MAX_ALREADY_CONNECTED_RETRIES})...")
                        self._update_status(BotStatus.SCANNED)
                        await asyncio.sleep(2)
                        continue
                        
                elif result.get("expired"):
                    logger.warning(f"[{now}] [WeChatBotEngine-Background] ⏰ 二维码过期，尝试复用已保存凭证...")
                    reused = await self._try_reuse_saved_credentials()
                    if reused:
                        logger.info(f"[{now}] [WeChatBotEngine-Background] ✅ 二维码过期但凭证有效，直接复用! 无需重新扫码")
                        return
                    logger.warning(f"[{now}] [WeChatBotEngine-Background] 凭证也无效，需要刷新二维码重新扫码")
                    break
                    
                elif result.get("scanned"):
                    if not scanned_printed:
                        logger.info(f"[{now}] [WeChatBotEngine-Background] ✅ 已扫码，等待确认...")
                        scanned_printed = True
                        self._update_status(BotStatus.SCANNED)
                        
                elif result.get("need_verifycode"):
                    logger.warning(f"[{now}] [WeChatBotEngine-Background] 需要验证码")
                    break
                
                await asyncio.sleep(1)
            
            # 如果到这里说明需要刷新二维码，但先尝试复用已保存凭证
            reused = await self._try_reuse_saved_credentials()
            if reused:
                logger.info("[WeChatBotEngine-Background] ✅ 复用已保存凭证成功! 无需重新扫码")
                return
            
            logger.warning("[WeChatBotEngine-Background] 凭证无效，尝试刷新二维码...")
            new_qr = await self._client.get_qrcode(base_url=base_url)
            self._client._last_qr_result = new_qr
            
            # 重新处理图片并更新状态
            qr_image_data = await self._process_qr_image(new_qr)
            self._state.qr_code_base64 = qr_image_data
            self._update_status(BotStatus.WAITING_QR)
            
            # 继续等待（递归调用自己，但只允许一次刷新）
            await self._wait_for_login()
            
        except TimeoutError:
            logger.warning("[WeChatBotEngine-Background] ⏰ 登录超时")
            self._state.error_message = "登录超时，请重启服务"
            self._update_status(BotStatus.ERROR)
        except Exception as e:
            logger.error(f"[WeChatBotEngine-Background] ❌ 登录失败: {e}")
            self._state.error_message = f"登录失败: {str(e)}"
            self._update_status(BotStatus.ERROR)

    async def _listen_messages(self):
        """
        登录成功后持续监听微信消息
        
        流程:
        1. 通过 client.poll_messages() 长轮询获取消息
        2. 收到消息后:
           - 存入最近消息列表
           - 触发消息回调
           - 如果设置了 message_handler 则调用
        3. 停止时退出循环
        """
        if not self._client or not self._client._credentials:
            logger.error("[WeChatBotEngine-Background] ❌ 无凭证，无法监听消息")
            self._state.error_message = "无凭证，无法监听消息"
            self._update_status(BotStatus.ERROR)
            return
        
        logger.info("[WeChatBotEngine-Background] 📡 开始监听微信消息...")
        
        try:
            async for message in self._client.poll_messages():
                if not self._running:
                    break
                
                now = datetime.now().strftime('%H:%M:%S')
                logger.info(f"[{now}] [WeChatBotEngine] 📩 收到消息: from={message.from_user_id}, text={message.text[:50]}")
                
                msg_dict = {
                    "from_user_id": message.from_user_id,
                    "to_user_id": message.to_user_id,
                    "text": message.text,
                    "context_token": message.context_token,
                    "message_type": message.message_type,
                    "timestamp": message.timestamp,
                    "client_id": message.client_id,
                    "received_at": datetime.now().isoformat(),
                }
                
                self._recent_messages.append(msg_dict)
                if len(self._recent_messages) > self._MAX_RECENT_MESSAGES:
                    self._recent_messages = self._recent_messages[-self._MAX_RECENT_MESSAGES:]
                
                for cb in self._message_callbacks:
                    try:
                        if asyncio.iscoroutinefunction(cb):
                            await cb(msg_dict)
                        else:
                            cb(msg_dict)
                    except Exception as e:
                        logger.error(f"[WeChatBotEngine] 消息回调出错: {e}")
                
                if self._message_handler:
                    try:
                        reply = self._message_handler(message)
                        if asyncio.iscoroutinefunction(self._message_handler):
                            reply = await self._message_handler(message)
                        
                        if reply and isinstance(reply, str):
                            context_token = message.context_token or self._client.get_context_token(message.from_user_id)
                            if context_token:
                                await self.send_text(message.from_user_id, context_token, reply)
                            else:
                                logger.warning(f"[WeChatBotEngine] 无法回复 {message.from_user_id}: 无context_token")
                    except Exception as e:
                        logger.error(f"[WeChatBotEngine] 消息处理器出错: {e}")
                        
        except asyncio.CancelledError:
            logger.info("[WeChatBotEngine-Background] 消息监听被取消")
        except Exception as e:
            err_str = str(e)
            logger.error(f"[WeChatBotEngine-Background] ❌ 消息监听出错: {e}")
            
            if "timeout" in err_str.lower() or "session" in err_str.lower():
                logger.info("[WeChatBotEngine-Background] 检测到会话/超时错误，尝试自动重连...")
                reused = await self._try_reuse_saved_credentials()
                if reused:
                    logger.info("[WeChatBotEngine-Background] ✅ 自动重连成功，继续监听消息")
                    await self._listen_messages()
                    return
            
            self._state.error_message = f"消息监听出错: {err_str}"
            self._update_status(BotStatus.ERROR)
        finally:
            logger.info("[WeChatBotEngine-Background] 消息监听已结束")

    async def send_text(self, to_user_id: str, context_token: str, text: str) -> bool:
        """
        发送文本消息到微信用户
        
        Args:
            to_user_id: 目标用户ID
            context_token: 会话令牌
            text: 消息文本
            
        Returns:
            bool: 是否发送成功
        """
        if not self._client or not self._client._credentials:
            logger.error("[WeChatBotEngine] 未登录，无法发送消息")
            return False
        
        try:
            success = await self._client.send_text(to_user_id, context_token, text, show_typing=False)
            if success:
                now = datetime.now().strftime('%H:%M:%S')
                logger.info(f"[{now}] [WeChatBotEngine] ✅ 消息发送成功: to={to_user_id}, text={text[:30]}")
                
                sent_msg = {
                    "from_user_id": "bot",
                    "to_user_id": to_user_id,
                    "text": text,
                    "timestamp": int(time.time()),
                    "sent_at": datetime.now().isoformat(),
                    "direction": "sent",
                }
                self._recent_messages.append(sent_msg)
                if len(self._recent_messages) > self._MAX_RECENT_MESSAGES:
                    self._recent_messages = self._recent_messages[-self._MAX_RECENT_MESSAGES:]
            return success
        except Exception as e:
            logger.error(f"[WeChatBotEngine] ❌ 发送消息失败: {e}")
            return False

    async def send_image(self, to_user_id: str, context_token: str,
                         image_data: bytes, file_ext: str = "png") -> bool:
        """
        发送图片消息到微信用户
        
        Args:
            to_user_id: 目标用户ID
            context_token: 会话令牌
            image_data: 图片二进制数据
            file_ext: 文件扩展名
            
        Returns:
            bool: 是否发送成功
        """
        if not self._client or not self._client._credentials:
            logger.error("[WeChatBotEngine] 未登录，无法发送图片")
            return False
        
        try:
            success = await self._client.send_image(
                to_user_id, context_token, image_data, file_ext, show_typing=False
            )
            if success:
                now = datetime.now().strftime('%H:%M:%S')
                logger.info(f"[{now}] [WeChatBotEngine] ✅ 图片发送成功: to={to_user_id}, size={len(image_data)}")
                
                sent_msg = {
                    "from_user_id": "bot",
                    "to_user_id": to_user_id,
                    "text": f"[图片 {len(image_data)//1024}KB]",
                    "timestamp": int(time.time()),
                    "sent_at": datetime.now().isoformat(),
                    "direction": "sent",
                    "message_type": "image",
                }
                self._recent_messages.append(sent_msg)
                if len(self._recent_messages) > self._MAX_RECENT_MESSAGES:
                    self._recent_messages = self._recent_messages[-self._MAX_RECENT_MESSAGES:]
            return success
        except Exception as e:
            logger.error(f"[WeChatBotEngine] ❌ 发送图片失败: {e}")
            return False

    def get_recent_messages(self, limit: int = 20) -> list:
        """获取最近的消息列表"""
        return self._recent_messages[-limit:]

    def add_message_callback(self, callback: Callable):
        """添加消息回调函数"""
        self._message_callbacks.append(callback)

    def remove_message_callback(self, callback: Callable):
        """移除消息回调函数"""
        if callback in self._message_callbacks:
            self._message_callbacks.remove(callback)


# 全局单例访问器
class WeChatBotRegistry:
    """
    微信机器人引擎注册表
    
    按平台用户ID管理多个引擎实例，支持多用户并发。
    每个平台用户拥有独立的引擎、凭证和消息流。
    """
    
    def __init__(self):
        self._engines: Dict[str, WeChatBotEngine] = {}
        self._lock = asyncio.Lock()
    
    def get(self, platform_user_id: str) -> WeChatBotEngine:
        """获取指定用户的引擎实例（不存在则创建）"""
        if platform_user_id not in self._engines:
            self._engines[platform_user_id] = WeChatBotEngine(platform_user_id)
            logger.info(f"[WeChatBotRegistry] 为用户 {platform_user_id} 创建新引擎实例")
        return self._engines[platform_user_id]
    
    def remove(self, platform_user_id: str):
        """移除指定用户的引擎实例"""
        if platform_user_id in self._engines:
            del self._engines[platform_user_id]
            logger.info(f"[WeChatBotRegistry] 已移除用户 {platform_user_id} 的引擎实例")
    
    def has(self, platform_user_id: str) -> bool:
        """检查指定用户是否有引擎实例"""
        return platform_user_id in self._engines
    
    @property
    def all_user_ids(self) -> list:
        """获取所有已注册的用户ID"""
        return list(self._engines.keys())
    
    @property
    def count(self) -> int:
        """当前注册的引擎数量"""
        return len(self._engines)


_registry = WeChatBotRegistry()


def get_wechat_engine(platform_user_id: str) -> WeChatBotEngine:
    """获取指定平台用户的微信机器人引擎实例"""
    return _registry.get(platform_user_id)


def get_wechat_registry() -> WeChatBotRegistry:
    """获取全局注册表（用于管理/监控）"""
    return _registry


if __name__ == "__main__":
    import sys
    
    async def test_engine():
        """引擎测试入口"""
        print("=" * 60)
        print("🔧 WeChatBotEngine 测试 (多用户)")
        print("=" * 60)
        
        test_user_id = "test_user_001"
        engine = get_wechat_engine(test_user_id)
        
        try:
            print("\n📋 Step 1: 启动服务...")
            await engine.start()
            
            print(f"\n📊 当前状态:")
            print(f"   Status: {engine.state.status.value}")
            print(f"   Running: {engine.is_running}")
            print(f"   Has QR: {bool(engine.state.qr_code_base64)}")
            
            print("\n⏳ 等待扫码 (180秒超时)...")
            
            for i in range(180):
                await asyncio.sleep(1)
                
                if engine.is_logged_in:
                    print("\n✅ 登录成功!")
                    print(f"   wxid: {engine.state.wxid}")
                    break
                    
                if engine.state.status == BotStatus.ERROR:
                    print(f"\n❌ 出错: {engine.state.error_message}")
                    break
                    
                if i % 10 == 0:
                    print(f"   已等待 {i} 秒... (状态: {engine.state.status.value})")
            
            if engine.is_logged_in:
                print("\n📋 Step 2: 测试发送消息...")
                result = await engine.send_message("filehelper", f"测试消息 from Engine! Time: {time.strftime('%H:%M:%S')}")
                print(f"   结果: {result}")
            
        finally:
            print("\n📋 Step 3: 停止服务...")
            await engine.stop()
            print("✅ 完成!")
    
    asyncio.run(test_engine())