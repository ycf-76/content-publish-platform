"""
微信 iLink Bot HTTP 客户端

基于 SiverKing/weixin-ClawBot-API 项目核心逻辑实现
协议: 腾讯官方 iLink Bot API
文档: https://www.wechatbot.dev/zh/protocol

功能:
- 二维码扫码登录
- 长轮询消息接收
- 消息发送
- 会话管理(context_token缓存)

设计原则:
- 纯HTTP调用，无外部SDK依赖
- 异步设计(asyncio + aiohttp)
- 自动重连和错误恢复
- 严格遵循iLink协议规范
"""

import asyncio
import base64
import json
import logging
import random
import time
from typing import Optional, Dict, Any, Callable, Awaitable, AsyncIterator
from dataclasses import dataclass, field
from urllib.parse import quote
import aiohttp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== 常量定义（来自官方项目）====================
BASE_URL = "https://ilinkai.weixin.qq.com"
CHANNEL_VERSION = "2.4.3"
ILINK_APP_ID = "bot"
ILINK_APP_CLIENT_VERSION = str((2 << 16) | (4 << 8) | 3)
BOT_AGENT = "pulse-studio-bot/1.0.0 (python)"


@dataclass
class LoginCredentials:
    """登录凭证"""
    bot_token: str = ""
    base_url: str = BASE_URL
    ilink_bot_id: str = ""
    ilink_user_id: str = ""
    
    @property
    def is_valid(self) -> bool:
        return bool(self.bot_token)


@dataclass
class QRCodeResult:
    """二维码结果"""
    qrcode: str = ""                    # 二维码字符串
    qrcode_image_content: str = ""      # Base64图片内容
    expires_in: int = 120               # 有效期(秒)


@dataclass
class Message:
    """微信消息"""
    from_user_id: str = ""              # 发送者ID
    to_user_id: str = ""                # 接收者ID
    text: str = ""                      # 消息文本
    context_token: str = ""             # 会话令牌(回复时必须带回)
    message_type: int = 1              # 消息类型(1=文本)
    timestamp: int = 0                 # 时间戳
    client_id: str = ""                # 客户端ID


@dataclass  
class UserSession:
    """用户会话(用于缓存context_token)"""
    user_id: str = ""
    context_token: str = ""
    typing_ticket: str = ""
    last_active_time: float = 0.0


class WeChatILinkClient:
    """
    微信 iLink Bot HTTP客户端
    
    核心职责:
    - 封装所有 iLink API 调用
    - 管理登录流程(二维码、Token)
    - 消息收发底层实现
    - 会话管理(context_token缓存)
    
    使用示例:
        client = WeChatILinkClient()
        
        # 登录
        qr = await client.get_qrcode()
        print(f"请扫描: {qr.qrcode}")
        creds = await client.login(qr.qrcode)
        
        # 监听消息
        async for msg in client.poll_messages():
            print(f"收到: {msg.text}")
            await client.send_text(msg.from_user_id, msg.context_token, "Echo!")
    """
    
    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._credentials: Optional[LoginCredentials] = None
        self._user_sessions: Dict[str, UserSession] = {}  # user_id -> session
        self._get_updates_buf: str = ""
        self._running: bool = False
        
    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建HTTP会话"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=60)
            )
        return self._session
    
    def _make_headers(self, token: Optional[str] = None) -> Dict[str, str]:
        """
        构造请求头(严格遵循iLink协议)
        
        关键点:
        - X-WECHAT-UIN: 必须每次不同，用于防重放攻击
        - AuthorizationType: 固定值 "ilink_bot_token"
        - Authorization: Bearer {token} (登录后必带)
        """
        uin = str(random.randint(0, 0xFFFFFFFF))
        headers = {
            "Content-Type": "application/json",
            "AuthorizationType": "ilink_bot_token",
            "X-WECHAT-UIN": base64.b64encode(uin.encode()).decode(),
            "iLink-App-Id": ILINK_APP_ID,
            "iLink-App-ClientVersion": ILINK_APP_CLIENT_VERSION,
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers
    
    def _base_info(self) -> Dict[str, str]:
        """基础信息"""
        return {
            "channel_version": CHANNEL_VERSION,
            "bot_agent": BOT_AGENT,
        }
    
    async def _api_get(self, path: str, token: Optional[str] = None, 
                       base_url: Optional[str] = None) -> Dict[str, Any]:
        """GET请求封装"""
        session = await self._get_session()
        url = f"{base_url or BASE_URL}/{path}"
        headers = self._make_headers(token)
        
        try:
            async with session.get(url, headers=headers) as response:
                text = await response.text()
                logger.info(f"[GET {path}] HTTP {response.status} → {text[:300]}")
                
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    logger.error(f"[GET {path}] JSON解析失败: {text[:200]}")
                    return {}
                    
        except Exception as e:
            logger.error(f"[GET {path}] 请求失败: {e}")
            raise
    
    async def _api_post(self, path: str, body: Dict[str, Any], 
                        token: Optional[str] = None,
                        base_url: Optional[str] = None) -> Dict[str, Any]:
        """POST请求封装"""
        session = await self._get_session()
        url = f"{base_url or BASE_URL}/{path}"
        headers = self._make_headers(token)
        
        try:
            async with session.post(url, json=body, headers=headers) as response:
                text = await response.text()
                logger.debug(f"[POST {path}] HTTP {response.status} → {text[:200]}")
                
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    logger.error(f"[POST {path}] JSON解析失败: {text[:200]}")
                    return {}
                    
        except Exception as e:
            logger.error(f"[POST {path}] 请求失败: {e}")
            raise
    
    # ==================== 登录相关 API ====================
    
    async def get_qrcode(self, base_url: Optional[str] = None) -> QRCodeResult:
        """
        获取登录二维码
        
        接口: GET /ilink/bot/get_bot_qrcode?bot_type=3
        
        Returns:
            QRCodeResult: 包含二维码字符串和Base64图片
        """
        logger.info("[WeChatILinkClient] 正在获取登录二维码...")
        
        data = await self._api_get(
            "ilink/bot/get_bot_qrcode?bot_type=3",
            base_url=base_url
        )
        
        if not data or "qrcode" not in data:
            raise Exception("获取二维码失败: 服务器返回数据异常")
        
        result = QRCodeResult(
            qrcode=data["qrcode"],
            qrcode_image_content=data.get("qrcode_img_content", ""),
            expires_in=data.get("expires_in", 120)
        )
        
        logger.info(f"[WeChatILinkClient] ✅ 二维码获取成功! qrcode={result.qrcode[:20]}...")
        return result
    
    async def poll_login_status(self, qrcode: str, base_url: Optional[str] = None,
                                verify_code: Optional[str] = None) -> Dict[str, Any]:
        """
        轮询扫码状态
        
        接口: GET /ilink/bot/get_qrcode_status?qrcode={qrcode}
        
        可能的状态:
        - wait: 等待扫码
        - scaned: 已扫描，等待确认
        - confirmed: 已确认，返回bot_token
        - expired: 二维码过期
        - need_verifycode: 需要验证码
        - verify_code_blocked: 验证码错误次数过多
        """
        endpoint = f"ilink/bot/get_qrcode_status?qrcode={quote(qrcode, safe='')}"
        if verify_code:
            endpoint += f"&verify_code={quote(verify_code, safe='')}"
            
        status = await self._api_get(endpoint, base_url=base_url)
        state = status.get("status", "")
        
        safe_status = {k: (v[:30] + '...' if isinstance(v, str) and len(v) > 30 else v)
                       for k, v in status.items()}
        logger.info(f"[WeChatILinkClient] 扫码轮询原始响应: state={state}, data={safe_status}")
        
        if state in ("confirmed",) or status.get("bot_token"):
            logger.info(f"[WeChatILinkClient] ✅ 检测到登录成功 (state={state}, has_bot_token={bool(status.get('bot_token'))})")
            return {
                "success": True,
                "credentials": LoginCredentials(
                    bot_token=status.get("bot_token", ""),
                    base_url=status.get("baseurl") or status.get("base_url") or base_url or BASE_URL,
                    ilink_bot_id=status.get("ilink_bot_id", ""),
                    ilink_user_id=status.get("ilink_user_id", ""),
                )
            }
        elif state == "binded_redirect" or status.get("binded_redirect"):
            if status.get("bot_token"):
                logger.info(f"[WeChatILinkClient] ✅ binded_redirect 携带 bot_token，提取凭证")
                return {
                    "success": True,
                    "credentials": LoginCredentials(
                        bot_token=status.get("bot_token", ""),
                        base_url=status.get("baseurl") or status.get("base_url") or base_url or BASE_URL,
                        ilink_bot_id=status.get("ilink_bot_id", ""),
                        ilink_user_id=status.get("ilink_user_id", ""),
                    )
                }
            logger.info(f"[WeChatILinkClient] binded_redirect 无 bot_token，返回 already_connected")
            return {"success": True, "already_connected": True, "raw_response": status}
        elif state == "expired":
            return {"success": False, "expired": True}
        elif state == "scaned":
            return {"success": False, "scanned": True}
        elif state in ("need_verifycode", "verify_code_blocked"):
            return {"success": False, "need_verifycode": state == "need_verifycode"}
        elif state and state != "wait":
            logger.warning(f"[WeChatILinkClient] 未知状态: {state}, 原始数据: {status}")
            
        return {"success": False, "status": state}
    
    async def login_with_qrcode(self, base_url: Optional[str] = None, 
                               timeout_seconds: Optional[int] = None,
                               allow_already_connected: bool = False) -> LoginCredentials:
        """
        完整的登录流程(获取二维码 + 等待扫码确认)
        
        Args:
            base_url: 可选的自定义API地址
            timeout_seconds: 超时时间(秒)，None表示无限等待
            allow_already_connected: 是否允许已连接状态（用于重连场景）
            
        Returns:
            LoginCredentials: 登录凭证
            
        Raises:
            Exception: 登录失败或超时
        """
        logger.info("[WeChatILinkClient] 开始登录流程...")
        
        deadline = time.time() + timeout_seconds if timeout_seconds else None
        max_refresh_count = 3
        refresh_count = 0
        
        while refresh_count < max_refresh_count:
            # Step 1: 获取二维码
            qr_result = await self.get_qrcode(base_url)
            
            if not qr_result.qrcode:
                raise Exception("获取二维码失败: 返回为空")
            
            logger.info(f"[WeChatILinkClient] 📱 请扫描二维码: {qr_result.qrcode[:30]}...")
            
            # Step 2: 轮询等待扫码
            scanned_printed = False
            while True:
                if deadline and time.time() >= deadline:
                    raise TimeoutError("登录超时")
                
                try:
                    result = await self.poll_login_status(qr_result.qrcode, base_url)
                except Exception as e:
                    logger.warning(f"[WeChatILinkClient] 轮询状态失败，稍后重试: {e}")
                    await asyncio.sleep(1)
                    continue
                
                # 处理各种结果
                if result.get("success") and result.get("credentials"):
                    creds = result["credentials"]
                    self._credentials = creds
                    logger.info(f"[WeChatILinkClient] ✅✅✅ 登录成功! Token: {creds.bot_token[:20]}...")
                    logger.info(f"[WeChatILinkClient]   bot_id: {creds.ilink_bot_id}")
                    logger.info(f"[WeChatILinkClient]   user_id: {creds.ilink_user_id}")
                    logger.info(f"[WeChatILinkClient]   base_url: {creds.base_url}")
                    return creds
                    
                elif result.get("already_connected"):
                    if allow_already_connected:
                        # 重连场景：允许已连接，使用当前凭证（如果有）
                        if self._credentials and self._credentials.is_valid:
                            logger.info("[WeChatILinkClient] 已连接状态，复用现有Token")
                            return self._credentials
                        else:
                            logger.warning("[WeChatILinkClient] 已连接但无可用Token，将重新登录")
                            break
                    else:
                        # 首次登录：不允许已连接，重新生成二维码
                        logger.warning("[WeChatILinkClient] 服务端提示已连接，将重新生成二维码")
                        break
                    
                elif result.get("expired"):
                    logger.warning("[WeChatILinkClient] ⏰ 二维码已过期，正在刷新...")
                    break
                    
                elif result.get("scanned"):
                    if not scanned_printed:
                        logger.info("[WeChatILinkClient] ✅ 已扫码，请在手机上确认...")
                        scanned_printed = True
                        
                elif result.get("need_verifycode"):
                    logger.warning("[WeChatILinkClient] 🔐 需要输入验证码")
                    # 在非交互模式下跳过
                    break
                    
                await asyncio.sleep(1)
            
            refresh_count += 1
        
        raise Exception(f"登录失败: 二维码刷新次数超过上限({max_refresh_count})")
    
    # ==================== 消息收发 API ====================
    
    async def poll_messages(self) -> AsyncIterator[Message]:
        """
        持续监听消息(长轮询模式)
        
        接口: POST /ilink/bot/getupdates
        特点:
        - 35秒超时自动返回(即使没有新消息)
        - 使用 get_updates_buf 断点续传
        - 支持多用户同时在线
        
        Yields:
            Message: 收到的消息对象
        """
        if not self._credentials or not self._credentials.is_valid:
            raise Exception("未登录，无法接收消息")
        
        logger.info("[WeChatILinkClient] 🔄 开始监听消息...")
        self._running = True
        
        try:
            while self._running:
                try:
                    result = await self._api_post(
                        "ilink/bot/getupdates",
                        {
                            "get_updates_buf": self._get_updates_buf,
                            "base_info": self._base_info(),
                        },
                        token=self._credentials.bot_token,
                        base_url=self._credentials.base_url
                    )
                    
                    # 更新断点续传缓冲区
                    self._get_updates_buf = result.get("get_updates_buf", "") or self._get_updates_buf
                    
                    # 解析消息列表
                    msgs = result.get("msgs", [])
                    if not msgs:
                        await asyncio.sleep(1)
                        continue
                    
                    for msg_data in msgs:
                        # 只处理文本消息(message_type=1)
                        if msg_data.get("message_type") != 1:
                            logger.debug(f"[WeChatILinkClient] 跳过非文本消息: type={msg_data.get('message_type')}")
                            continue
                        
                        # 提取消息内容
                        item_list = msg_data.get("item_list", [])
                        text = ""
                        if item_list and len(item_list) > 0:
                            text_item = item_list[0].get("text_item", {})
                            text = text_item.get("text", "")
                        
                        if not text:
                            continue
                        
                        # 构建Message对象
                        message = Message(
                            from_user_id=msg_data.get("from_user_id", ""),
                            to_user_id=msg_data.get("to_user_id", ""),
                            text=text,
                            context_token=msg_data.get("context_token", ""),
                            message_type=msg_data.get("message_type", 1),
                            timestamp=msg_data.get("timestamp", int(time.time())),
                            client_id=msg_data.get("client_id", ""),
                        )
                        
                        # 缓存context_token到用户会话
                        self._update_user_session(message.from_user_id, message.context_token)
                        
                        logger.info(f"[WeChatILinkClient] 📩 收到消息: {message.from_user_id} → {text[:50]}")
                        
                        yield message
                        
                except asyncio.CancelledError:
                    logger.info("[WeChatILinkClient] 消息监听被取消")
                    break
                except Exception as e:
                    logger.error(f"[WeChatILinkClient] 消息轮询出错: {e}，5秒后重试...")
                    await asyncio.sleep(5)
                    
        finally:
            self._running = False
            logger.info("[WeChatILinkClient] 停止监听消息")
    
    async def send_text(self, to_user_id: str, context_token: str, text: str,
                       show_typing: bool = True) -> bool:
        """
        发送文本消息
        
        接口: POST /ilink/bot/sendmessage
        
        关键参数:
        - context_token: 从接收的消息中获取，必须带回！
        - to_user_id: 目标用户ID
        - text: 消息文本
        
        Args:
            to_user_id: 目标用户ID
            context_token: 会话令牌(从poll_messages收到的消息中提取)
            text: 要发送的文本
            show_typing: 是否先显示"对方正在输入..."
            
        Returns:
            bool: 是否发送成功
        """
        if not self._credentials or not self._credentials.is_valid:
            raise Exception("未登录，无法发送消息")
        
        if not to_user_id or not context_token:
            logger.error(f"[WeChatILinkClient] 发送失败: 参数缺失 to_user_id={to_user_id}, context_token={context_token}")
            return False
        
        logger.info(f"[WeChatILinkClient] 📤 发送消息给 {to_user_id}: {text[:50]}...")
        
        # 显示"正在输入..."
        if show_typing:
            await self.show_typing(to_user_id, True)
        
        try:
            client_id = f"pulse-studio-{random.randint(0, 0xFFFFFFFF):08x}"
            
            result = await self._api_post(
                "ilink/bot/sendmessage",
                {
                    "msg": {
                        "from_user_id": "",
                        "to_user_id": to_user_id,
                        "client_id": client_id,
                        "message_type": 2,           # 文本消息
                        "message_state": 2,          # 正常状态
                        "context_token": context_token,  # 关键！必须带回
                        "item_list": [{
                            "type": 1,               # 文本类型
                            "text_item": {"text": text}
                        }]
                    },
                    "base_info": self._base_info(),
                },
                token=self._credentials.bot_token,
                base_url=self._credentials.base_url
            )
            
            # 判断成功：有 message_id 或 ret==0
            success = ("message_id" in result) or (result.get("ret", -1) == 0)
            
            if success:
                msg_id = result.get("message_id", "N/A")
                logger.info(f"[WeChatILinkClient] ✅ 发送成功! to={to_user_id}, msg_id={msg_id}")
                return True
            else:
                errmsg = result.get("errmsg", "未知错误")
                logger.error(f"[WeChatILinkClient] ❌ 发送失败: result={result}")
                return False
                
        except Exception as e:
            logger.error(f"[WeChatILinkClient] ❌ 发送异常: {e}")
            return False
        finally:
            # 取消"正在输入..."
            if show_typing:
                await self.show_typing(to_user_id, False)
    
    async def show_typing(self, to_user_id: str, show: bool = True) -> bool:
        """
        显示/隐藏"对方正在输入..."效果
        
        接口: POST /ilink/bot/sendtyping
        
        Args:
            to_user_id: 目标用户ID
            show: True=显示, False=隐藏
            
        Returns:
            bool: 是否成功
        """
        if not self._credentials or not self._credentials.is_valid:
            return False
        
        # 获取用户的typing_ticket
        session = self._user_sessions.get(to_user_id)
        if not session or not session.typing_ticket:
            try:
                config = await self._api_post(
                    "ilink/bot/getconfig",
                    {
                        "ilink_user_id": to_user_id,
                        "context_token": session.context_token if session else "",
                        "base_info": self._base_info(),
                    },
                    token=self._credentials.bot_token,
                    base_url=self._credentials.base_url
                )
                typing_ticket = config.get("typing_ticket", "")
                
                if not session:
                    session = UserSession(user_id=to_user_id)
                    self._user_sessions[to_user_id] = session
                session.typing_ticket = typing_ticket
                
            except Exception as e:
                logger.warning(f"[WeChatILinkClient] 获取typing_ticket失败: {e}")
                return False
        
        try:
            result = await self._api_post(
                "ilink/bot/sendtyping",
                {
                    "ilink_user_id": to_user_id,
                    "typing_ticket": session.typing_ticket,
                    "status": 1 if show else 2,  # 1=显示, 2=取消
                    "base_info": self._base_info(),
                },
                token=self._credentials.bot_token,
                base_url=self._credentials.base_url
            )
            
            logger.debug(f"[WeChatILinkClient] {'显示' if show else '隐藏'}'正在输入...'状态 to={to_user_id}")
            return True
            
        except Exception as e:
            logger.warning(f"[WeChatILinkClient] 设置typing状态失败: {e}")
            return False

    # ==================== 图片发送 ====================

    async def send_image(self, to_user_id: str, context_token: str,
                         image_data: bytes, file_ext: str = "png",
                         show_typing: bool = True) -> bool:
        """
        发送图片消息 (iLink 2.x CDN + AES-128-ECB 协议)
        
        流程:
        1. 生成随机 AES-128 key (16 bytes)
        2. AES-128-ECB 加密图片 (PKCS7 padding)
        3. getuploadurl 获取 CDN 上传参数 (传 filekey/media_type/rawsize/rawfilemd5/filesize/aeskey)
        4. POST 加密文件到 CDN (upload_full_url)
        5. sendmessage 带 image_item.media {encrypt_query_param, aes_key, encrypt_type}
        
        Args:
            to_user_id: 目标用户ID
            context_token: 会话令牌
            image_data: 图片二进制数据
            file_ext: 文件扩展名(png/jpg/gif)
            show_typing: 是否显示"正在输入..."
            
        Returns:
            bool: 是否发送成功
        """
        if not self._credentials or not self._credentials.is_valid:
            raise Exception("未登录，无法发送图片")
        
        if not to_user_id or not context_token:
            logger.error(f"[WeChatILinkClient] 发送图片失败: 参数缺失")
            return False

        try:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            from cryptography.hazmat.backends import default_backend
            _HAS_CRYPTOGRAPHY = True
        except ImportError:
            _HAS_CRYPTOGRAPHY = False

        if not _HAS_CRYPTOGRAPHY:
            try:
                from Crypto.Cipher import AES
                from Crypto.Util.Padding import pad as crypto_pad
                _HAS_PYCRYPTODOME = True
            except ImportError:
                logger.error("[WeChatILinkClient] 发送图片需要 cryptography 或 pycryptodome: pip install cryptography")
                return False
        else:
            _HAS_PYCRYPTODOME = False

        import hashlib
        import os as _os

        logger.info(f"[WeChatILinkClient] 📤 发送图片给 {to_user_id}, size={len(image_data)}bytes")

        if show_typing:
            await self.show_typing(to_user_id, True)

        try:
            # Step 1: 生成随机 AES-128 key (16 bytes)
            aes_key = _os.urandom(16)
            aes_key_hex = aes_key.hex()
            aes_key_b64 = base64.b64encode(aes_key_hex.encode()).decode()

            # Step 2: AES-128-ECB 加密图片 (PKCS7 padding)
            if _HAS_CRYPTOGRAPHY:
                pad_len = 16 - (len(image_data) % 16)
                padded = image_data + bytes([pad_len] * pad_len)
                cipher = Cipher(algorithms.AES(aes_key), modes.ECB(), backend=default_backend())
                encryptor = cipher.encryptor()
                encrypted = encryptor.update(padded) + encryptor.finalize()
            else:
                encrypted = AES.new(aes_key, AES.MODE_ECB).encrypt(crypto_pad(image_data, 16))

            # Step 3: 计算 MD5 和 filekey
            raw_md5 = hashlib.md5(image_data).hexdigest()
            file_key = _os.urandom(8).hex()
            raw_size = len(image_data)
            file_size = len(encrypted)

            # Step 4: getuploadurl
            upload_result = await self._api_post(
                "ilink/bot/getuploadurl",
                {
                    "filekey": file_key,
                    "media_type": 1,
                    "to_user_id": to_user_id,
                    "rawsize": raw_size,
                    "rawfilemd5": raw_md5,
                    "filesize": file_size,
                    "no_need_thumb": True,
                    "aeskey": aes_key_hex,
                    "base_info": self._base_info(),
                },
                token=self._credentials.bot_token,
                base_url=self._credentials.base_url
            )

            logger.info(f"[WeChatILinkClient] getuploadurl 响应: {json.dumps(upload_result, ensure_ascii=False)[:500]}")

            upload_url = upload_result.get("upload_full_url")
            upload_param = upload_result.get("upload_param", "")

            if not upload_url and upload_param:
                cdn_base = "https://novac2c.cdn.weixin.qq.com/c2c"
                upload_url = f"{cdn_base}?{upload_param}"

            if not upload_url:
                upload_url = (
                    upload_result.get("upload_url")
                    or upload_result.get("url")
                    or upload_result.get("cdn_url")
                )

            if not upload_url:
                logger.error(f"[WeChatILinkClient] getuploadurl 未返回上传地址: {upload_result}")
                return False

            logger.info(f"[WeChatILinkClient] CDN上传URL: {upload_url[:200]}")

            # Step 5: POST 加密文件到 CDN，从响应 header 获取 x-encrypted-param
            download_param = ""
            async with aiohttp.ClientSession() as session:
                async with session.post(upload_url, data=encrypted) as resp:
                    if resp.status not in (200, 201, 204):
                        body = await resp.text()
                        logger.error(f"[WeChatILinkClient] CDN上传失败: status={resp.status}, body={body[:200]}")
                        return False

                    download_param = resp.headers.get("x-encrypted-param", "")
                    cdn_resp_text = await resp.text()
                    all_headers = dict(resp.headers)
                    logger.info(f"[WeChatILinkClient] CDN上传成功: status={resp.status}, x-encrypted-param={'有' if download_param else '无'}, headers={list(all_headers.keys())}")

            logger.info(f"[WeChatILinkClient] ✅ CDN上传完成, size={file_size}, download_param={'有' if download_param else '无'}")

            # Step 6: 如果 header 没返回 download_param，尝试从 getuploadurl 响应中取
            if not download_param:
                download_param = (
                    upload_result.get("download_encrypted_query_param")
                    or upload_result.get("encrypt_query_param")
                    or upload_result.get("download_param")
                    or ""
                )
                if download_param:
                    logger.info(f"[WeChatILinkClient] 从 getuploadurl 响应获取到 download_param")
                else:
                    logger.warning(f"[WeChatILinkClient] ⚠️ 未获取到 download_param (encrypt_query_param)，图片可能无法在微信端显示")

            # Step 7: sendmessage (图片消息)
            client_id = f"pulse-studio-{random.randint(0, 0xFFFFFFFF):08x}"

            result = await self._api_post(
                "ilink/bot/sendmessage",
                {
                    "msg": {
                        "from_user_id": "",
                        "to_user_id": to_user_id,
                        "client_id": client_id,
                        "message_type": 2,
                        "message_state": 2,
                        "context_token": context_token,
                        "item_list": [{
                            "type": 2,
                            "image_item": {
                                "media": {
                                    "encrypt_query_param": download_param,
                                    "aes_key": aes_key_b64,
                                    "encrypt_type": 1,
                                },
                                "mid_size": raw_size,
                            }
                        }]
                    },
                    "base_info": self._base_info(),
                },
                token=self._credentials.bot_token,
                base_url=self._credentials.base_url
            )

            logger.info(f"[WeChatILinkClient] sendmessage 响应: {json.dumps(result, ensure_ascii=False)[:500]}")

            success = ("message_id" in result) or (result.get("ret", -1) == 0)
            if success:
                msg_id = result.get("message_id", "N/A")
                logger.info(f"[WeChatILinkClient] ✅ 图片发送成功! msg_id={msg_id}")
                return True
            else:
                logger.error(f"[WeChatILinkClient] ❌ 图片发送失败: {result}")
                return False

        except Exception as e:
            logger.error(f"[WeChatILinkClient] ❌ 发送图片异常: {e}", exc_info=True)
            return False
        finally:
            if show_typing:
                await self.show_typing(to_user_id, False)

    # ==================== 会话管理 ====================
    
    def _update_user_session(self, user_id: str, context_token: str):
        """更新用户会话(缓存context_token)"""
        if user_id in self._user_sessions:
            self._user_sessions[user_id].context_token = context_token
            self._user_sessions[user_id].last_active_time = time.time()
        else:
            self._user_sessions[user_id] = UserSession(
                user_id=user_id,
                context_token=context_token,
                last_active_time=time.time()
            )
    
    def get_context_token(self, user_id: str) -> Optional[str]:
        """获取用户的最新context_token"""
        session = self._user_sessions.get(user_id)
        return session.context_token if session else None
    
    @property
    def is_logged_in(self) -> bool:
        """是否已登录"""
        return self._credentials is not None and self._credentials.is_valid
    
    @property
    def credentials(self) -> Optional[LoginCredentials]:
        """获取当前登录凭证"""
        return self._credentials
    
    @property
    def is_running(self) -> bool:
        """是否正在运行"""
        return self._running
    
    async def close(self):
        """关闭连接，释放资源"""
        logger.info("[WeChatILinkClient] 正在关闭连接...")
        self._running = False
        
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
        
        self._credentials = None
        self._user_sessions.clear()
        self._get_updates_buf = ""
        
        logger.info("[WeChatILinkClient] ✅ 连接已关闭")


# ==================== 便捷函数 ====================

async def create_client_and_login() -> WeChatILinkClient:
    """创建客户端并完成登录(便捷函数)"""
    client = WeChatILinkClient()
    creds = await client.login_with_qrcode()
    return client


if __name__ == "__main__":
    import sys
    
    async def main():
        """测试入口"""
        print("=" * 60)
        print("🤖 Pulse Studio 微信 iLink Bot 测试客户端")
        print("=" * 60)
        
        client = WeChatILinkClient()
        
        try:
            # 登录
            print("\n📱 步骤1: 获取二维码并登录...")
            creds = await client.login_with_qrcode(timeout_seconds=180)  # 3分钟超时
            
            print("\n✅ 登录成功!")
            print(f"   Token: {creds.bot_token[:30]}...")
            print(f"   Bot ID: {creds.ilink_bot_id}")
            print(f"   User ID: {creds.ilink_user_id}")
            
            # 监听消息
            print("\n🔄 步骤2: 开始监听消息(Echo模式)...")
            print("   (按 Ctrl+C 退出)\n")
            
            async for msg in client.poll_messages():
                print(f"\n[收到] {msg.from_user_id}: {msg.text}")
                
                # Echo回复
                reply = f"📨 Echo: {msg.text}\n⏰ 时间: {time.strftime('%H:%M:%S')}"
                success = await client.send_text(msg.from_user_id, msg.context_token, reply)
                
                if success:
                    print(f"[已回复] {msg.from_user_id}: {reply[:50]}...")
                else:
                    print(f"[❌ 回复失败]")
                    
        except KeyboardInterrupt:
            print("\n\n⚠️ 用户中断")
        except Exception as e:
            print(f"\n❌ 错误: {e}", file=sys.stderr)
        finally:
            await client.close()
            print("\n👋 客户端已关闭")
    
    asyncio.run(main())