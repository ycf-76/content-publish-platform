"""XHS MCP client implementation — HTTP thin client.

架构（遵守 project_memory 约束：业务进程不接触 Playwright）：
- XhsMCPClient 不再直接调 Playwright，所有浏览器操作通过 qr_http_worker 的 HTTP 接口
- 扫码登录后 cookies 持久化到 DB；XhsMCPClient.connect() 用 cookies 调 worker
  创建工作会话（POST /session/create），拿到 session_id
- 后续 search_notes / get_current_user_info / get_note_detail 通过 session_id 调 worker
- D17: 双模式架构 — 插件 MCP（主） + 本地 Playwright（fallback，经 worker HTTP）
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from app.agents.skills.mcp.base import MCPClient, MCPConfig

logger = logging.getLogger(__name__)

# 默认 worker 地址
_DEFAULT_WORKER_BASE = "http://127.0.0.1:9010"


class XhsMCPClient(MCPClient):
    """XHS MCP client — 通过 qr_http_worker HTTP 接口操作浏览器。

    不再持有 Playwright 对象。cookies 由外部注入（refresh_session 或
    update_mcp_cookies_from_session），connect() 时用 cookies 创建工作会话。
    """

    def __init__(self, config: MCPConfig) -> None:
        self.config = config
        self._connected = False
        # cookies 列表（Playwright export_cookies 格式：[{name, value, domain, ...}]）
        self._cookies: list[dict[str, Any]] = []
        self._session_id: str | None = None
        self._worker_base = _DEFAULT_WORKER_BASE
        self._http_timeout = 60.0  # 搜索/导航可能较慢
        # 连接失败冷却：cookies 无效或 worker 不可用时，避免每次调用都反复尝试创建会话
        self._last_connect_fail_at: float = 0.0
        self._connect_fail_cooldown: float = 60.0  # 失败后 60 秒内不再尝试

    def set_cookies(self, cookies: list[dict[str, Any]] | dict[str, str]) -> None:
        """注入 cookies。支持两种格式：
        - list[dict]: Playwright export_cookies 格式（含 domain/path/expires）
        - dict[str, str]: 简单 name→value 映射（自动补全 domain）
        """
        if isinstance(cookies, dict):
            self._cookies = [
                {"name": k, "value": v, "domain": ".xiaohongshu.com", "path": "/"}
                for k, v in cookies.items()
            ]
        else:
            self._cookies = list(cookies)
        # cookies 变了，旧 session 失效
        self._session_id = None
        self._connected = False
        # 新 cookies 注入后重置失败冷却，允许立即尝试连接
        self._last_connect_fail_at = 0.0

    async def connect(self) -> bool:
        """用 cookies 调 worker 创建工作会话。"""
        if not self._cookies:
            logger.warning("XhsMCPClient connect: no cookies, skip")
            self._connected = False
            return False
        # 失败冷却：cookies 无效或 worker 不可用时，避免反复尝试浪费资源
        if self._last_connect_fail_at > 0:
            elapsed = time.time() - self._last_connect_fail_at
            if elapsed < self._connect_fail_cooldown:
                logger.debug(
                    f"XhsMCPClient connect: cooling down "
                    f"({self._connect_fail_cooldown - elapsed:.0f}s remaining)"
                )
                return False
        # 清理旧 session，避免 session 泄漏（QR Worker 也有 10min 超时，但主动清理更干净）
        if self._session_id:
            old_session = self._session_id
            self._session_id = None
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    await client.delete(f"{self._worker_base}/session/{old_session}")
            except Exception:
                pass  # 清理失败不影响主流程
        try:
            async with httpx.AsyncClient(timeout=self._http_timeout) as client:
                resp = await client.post(
                    f"{self._worker_base}/session/create",
                    json={"cookies": self._cookies},
                )
                resp.raise_for_status()
                data = resp.json()
            if not data.get("success"):
                msg = data.get("message", "unknown")
                logger.error(f"XhsMCPClient connect failed: {msg}")
                self._connected = False
                self._last_connect_fail_at = time.time()
                return False
            session_data = data.get("data") or {}
            session_id = session_data.get("session_id")
            if not session_id:
                logger.error(f"XhsMCPClient connect failed: no session_id in response")
                self._connected = False
                self._last_connect_fail_at = time.time()
                return False
            self._session_id = session_id
            self._connected = True
            self._last_connect_fail_at = 0.0  # 成功后重置冷却
            logger.info(f"XhsMCPClient connected (work session={self._session_id})")
            return True
        except Exception as e:
            logger.error(f"XhsMCPClient connect failed: {e}")
            self._connected = False
            self._last_connect_fail_at = time.time()
            return False

    async def _ensure_connected(self) -> None:
        if not self._connected or not self._session_id:
            success = await self.connect()
            if not success:
                raise RuntimeError(
                    "MCP client not connected（cookies 缺失或 worker 不可用）"
                )

    async def _post(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        """调 worker POST 接口，返回 data 字段。失败抛 RuntimeError。"""
        await self._ensure_connected()
        url = f"{self._worker_base}{path}"
        try:
            async with httpx.AsyncClient(timeout=self._http_timeout) as client:
                resp = await client.post(url, json=body or {})
                resp.raise_for_status()
                payload = resp.json()
        except httpx.HTTPError as e:
            logger.error(f"worker POST {path} failed: {e}")
            raise RuntimeError(f"worker 请求失败: {e}")
        if not payload.get("success"):
            msg = payload.get("message", "unknown")
            logger.error(f"worker POST {path} error: {msg}")
            raise RuntimeError(msg)
        return payload.get("data", {})

    async def search_notes(self, keyword: str, limit: int = 20) -> list[dict[str, Any]]:
        logger.info(f"[MCP] search_notes: keyword={keyword}, limit={limit}")
        # 失败时抛异常，让上层 MCPClientManager.search_notes 的 fallback 逻辑生效
        await self._ensure_connected()
        data = await self._post(
            f"/search/{self._session_id}",
            {"keyword": keyword, "limit": limit},
        )
        results = data if isinstance(data, list) else data.get("notes", [])
        logger.info(f"[MCP] search_notes OK: {len(results)} notes")
        return results[:limit]

    async def search_notes_with_details(
        self,
        keyword: str,
        limit: int = 8,
        detail_top_n: int = 5,
    ) -> dict[str, Any]:
        """搜索笔记并采集 top N 条详情（点击进入+拦截 feed XHR）。

        相比 search_notes，本方法会点击搜索结果卡片进入详情页，
        拦截 /api/sns/web/v1/feed XHR，提取 likes/comments/collects/shares 等完整字段。
        绕过直接 goto /explore/{note_id} 被风控(300031)的问题。

        Returns:
            {"results": [...], "details_collected": int}
            top N 条 result 包含完整字段（likes/comments/collects/shares/desc/tags等）
        """
        logger.info(
            f"[MCP] search_notes_with_details: keyword={keyword}, "
            f"limit={limit}, detail_top_n={detail_top_n}"
        )
        await self._ensure_connected()
        data = await self._post(
            f"/search_with_details/{self._session_id}",
            {"keyword": keyword, "limit": limit, "detail_top_n": detail_top_n},
        )
        results = data.get("results", []) if isinstance(data, dict) else []
        details_collected = data.get("details_collected", 0) if isinstance(data, dict) else 0
        logger.info(
            f"[MCP] search_notes_with_details OK: {len(results)} notes, "
            f"{details_collected} details collected"
        )
        return {"results": results, "details_collected": details_collected}

    async def get_note_detail(self, note_id: str) -> dict[str, Any]:
        logger.info(f"[MCP] get_note_detail: {note_id}")
        try:
            await self._ensure_connected()
            data = await self._post(
                f"/note_detail/{self._session_id}",
                {"note_id": note_id},
            )
            return data
        except RuntimeError as e:
            logger.error(f"[MCP] get_note_detail failed: {e}")
            return {"note_id": note_id, "title": "", "content": "", "images": [], "tags": []}

    async def get_current_user_info(self) -> dict[str, Any]:
        """获取当前登录用户真实信息。失败抛 RuntimeError（不返回假数据）。"""
        logger.info("[MCP] get_current_user_info")
        # 这个接口无 body
        await self._ensure_connected()
        url = f"{self._worker_base}/user_info_current/{self._session_id}"
        try:
            async with httpx.AsyncClient(timeout=self._http_timeout) as client:
                resp = await client.post(url, json={})
                resp.raise_for_status()
                payload = resp.json()
        except httpx.HTTPError as e:
            logger.error(f"worker user_info_current failed: {e}")
            raise RuntimeError(f"worker 请求失败: {e}")
        if not payload.get("success"):
            msg = payload.get("message", "unknown")
            logger.error(f"[MCP] get_current_user_info error: {msg}")
            raise RuntimeError(msg)
        info = payload.get("data", {})
        logger.info(
            f"[MCP] get_current_user_info OK: "
            f"user_id={info.get('xhs_user_id')}, nickname={info.get('nickname')}"
        )
        return info

    async def get_account_info(self, account_id: str) -> dict[str, Any]:
        """获取账号信息（复用 get_current_user_info）。失败抛 RuntimeError。"""
        info = await self.get_current_user_info()  # 失败会抛 RuntimeError
        return {
            "account_id": account_id,
            "nickname": info.get("nickname", ""),
            "avatar": info.get("avatar_url", ""),
            "fans_count": 0,
            "notes_count": 0,
        }

    async def publish_note(
        self,
        title: str,
        content: str,
        images_b64: list[str] | None = None,
    ) -> dict[str, Any]:
        """发布笔记到小红书（单次发布，不重试）。

        通过 worker 的 /publish/{session_id} 接口，用 Playwright 操作
        创作者发布页完成发布。需要先 connect() 创建工作会话（注入登录 cookies）。

        Args:
            title: 笔记标题（小红书限制 20 字，超出会被截断）
            content: 笔记正文
            images_b64: base64 编码的图片列表（可选，最多 9 张）

        Returns:
            {"success": bool, "post_id": str, "message": str}
        """
        logger.info(
            f"[MCP] publish_note: title={title!r}, images={len(images_b64 or [])}"
        )
        try:
            await self._ensure_connected()
            data = await self._post(
                f"/publish/{self._session_id}",
                {
                    "title": title,
                    "content": content,
                    "images_b64": images_b64 or [],
                },
            )
            logger.info(
                f"[MCP] publish_note OK: success={data.get('success')}, "
                f"message={data.get('message', '')}"
            )
            return data
        except RuntimeError as e:
            logger.error(f"[MCP] publish_note failed: {e}")
            return {
                "success": False,
                "post_id": "",
                "message": str(e),
            }

    async def check_publish_result(self) -> dict[str, Any]:
        """回查半自动发布结果。

        配合 publish_note（半自动模式）使用：publish 填好内容后不点击，
        由用户在浏览器窗口手动点「发布」，前端轮询此接口判断是否完成。

        Returns:
            {"success": bool, "status": "pending"|"published"|"failed"|"session_invalid",
             "url": str, "message": str}
            - status=published：发布成功，页面已跳转
            - status=pending：仍在编辑器，等用户点击
            - status=failed：发布失败（登录失效/页面错误提示）
            - status=session_invalid：会话过期，需重新创建
        """
        try:
            await self._ensure_connected()
            data = await self._post(
                f"/publish/{self._session_id}/check",
                {},
            )
            logger.info(
                f"[MCP] check_publish_result: status={data.get('status')}, "
                f"message={data.get('message', '')}"
            )
            return data
        except RuntimeError as e:
            logger.error(f"[MCP] check_publish_result failed: {e}")
            return {
                "status": "session_invalid",
                "url": "",
                "message": str(e),
            }

    async def generate_qrcode(self) -> dict[str, Any]:
        """生成二维码（转发到 login_service）。"""
        from app.account.login_service import get_login_service
        login_svc = get_login_service()
        return await login_svc.generate_qrcode()

    async def check_login_status(self, qr_id: str) -> dict[str, Any]:
        from app.account.login_service import get_login_service
        login_svc = get_login_service()
        return await login_svc.check_login_status(qr_id)

    async def close(self) -> None:
        # 关闭工作会话
        if self._session_id:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    await client.delete(
                        f"{self._worker_base}/session/{self._session_id}"
                    )
            except Exception as e:
                logger.warning(f"close work session failed: {e}")
        self._session_id = None
        self._connected = False
        logger.info("XhsMCPClient connection closed")


class MCPClientManager:
    def __init__(self) -> None:
        self._plugin_client: MCPClient | None = None
        self._local_client: MCPClient | None = None
        # 搜索频率控制（防止被小红书行为分析标记）
        self._search_timestamps: list[float] = []  # 滑动窗口：最近 60s 的搜索时间戳
        self._daily_search_count: int = 0  # 当日搜索次数
        self._daily_reset_at: float = 0.0  # 当日计数重置时间
        # 频率参数（保守值，远低于风控阈值）
        # v2: 深度防风控——每日上限从 30 降到 10，间隔从 30s 提到 60s
        # 小红书行为分析模型对高频访问敏感，10 次/天是安全区间
        self._min_interval = 60.0  # 两次搜索最少间隔 60 秒
        self._window_seconds = 60.0  # 滑动窗口大小
        self._window_max = 1  # 窗口内最大搜索次数（60秒内只搜1次）
        self._daily_max = 10  # 每日最大搜索次数（深度防风控）
        # 频率控制锁：防止并发请求绕过限制（asyncio.sleep 会让出控制权）
        self._rate_limit_lock: asyncio.Lock = asyncio.Lock()
        # cookies 加载冷却：数据库无账号时避免每次搜索都查库
        self._last_cookies_check_at: float = 0.0
        self._cookies_check_cooldown: float = 300.0  # 5 分钟

    def set_plugin_client(self, client: MCPClient) -> None:
        self._plugin_client = client

    def set_local_client(self, client: MCPClient) -> None:
        self._local_client = client

    async def _enforce_search_rate_limit(self) -> None:
        """三层频率控制：最小间隔 + 滑动窗口 + 每日上限。

        红线：扩展方案技术上无法被识别，但高频请求会被行为分析模型标记。
        保守控制频率在"正常用户"范围内。

        加锁：防止并发请求在 asyncio.sleep 让出控制权时同时通过检查。
        """
        async with self._rate_limit_lock:
            now = time.time()

            # 第 3 层：每日上限
            if now - self._daily_reset_at > 86400:  # 24 小时重置
                self._daily_search_count = 0
                self._daily_reset_at = now
            if self._daily_search_count >= self._daily_max:
                raise RuntimeError(
                    f"今日搜索次数已达上限（{self._daily_max}次），请明天再试"
                )

            # 第 2 层：滑动窗口（60 秒内最多 2 次）
            self._search_timestamps = [
                t for t in self._search_timestamps if now - t < self._window_seconds
            ]
            if len(self._search_timestamps) >= self._window_max:
                wait = self._window_seconds - (now - self._search_timestamps[0])
                logger.warning(
                    f"[rate_limit] 搜索频率过高，{wait:.0f}s 后再试"
                    f"（窗口内已有 {len(self._search_timestamps)} 次）"
                )
                await asyncio.sleep(max(wait, 0))

            # 第 1 层：最小间隔
            if self._search_timestamps:
                elapsed = now - self._search_timestamps[-1]
                if elapsed < self._min_interval:
                    wait = self._min_interval - elapsed
                    logger.info(f"[rate_limit] 最小间隔等待 {wait:.1f}s")
                    await asyncio.sleep(wait)

            self._search_timestamps.append(time.time())
            self._daily_search_count += 1

    async def _emit_degraded(self, reason: str, fallback_used: str) -> None:
        """发 search_degraded SSE 事件（如果有 workflow_id 上下文）。

        memory 约束：MCP 降级时必须通知前端。
        """
        try:
            from app.services.workflow_events import emit_search_degraded
            from app.services.context import current_workflow_id
            wf_id = current_workflow_id.get(None)
            if wf_id:
                await emit_search_degraded(wf_id, reason, fallback_used)
        except Exception as e:
            logger.warning(f"emit_search_degraded failed: {e}")

    async def search_notes(self, keyword: str, limit: int = 20) -> list[dict[str, Any]]:
        """搜索笔记。

        优先走插件 MCP（用户真实浏览器环境）；
        插件失败时 fallback 到 local_client（QR Worker session 方式，用数据库 cookies）。

        频率控制：三层节流（最小间隔 30s + 60s 窗口最多 2 次 + 每日 30 次）。
        """
        # 频率控制（在发请求前阻塞等待，避免高频触发风控）
        try:
            await self._enforce_search_rate_limit()
        except RuntimeError as e:
            logger.warning(f"[search] {e}")
            await self._emit_degraded(str(e), fallback_used="none")
            return []

        # 方案 1：插件 MCP（用户真实浏览器，零自动化特征）
        if self._plugin_client:
            try:
                return await self._plugin_client.search_notes(keyword, limit)
            except Exception as e:
                logger.warning(f"[search] 插件 MCP 搜索失败，尝试 fallback 到 QR Worker: {e}")

        # 方案 2：fallback 到 local_client（QR Worker session 方式）
        if not self._local_client:
            await self._emit_degraded(
                "插件 MCP 搜索失败且无 local client 可用",
                fallback_used="none",
            )
            raise RuntimeError("插件 MCP 搜索失败且无 local client 可用")

        # 确保 local_client 有有效 cookies（从数据库加载最新的 qrcode 账号）
        await self._ensure_local_client_cookies()

        try:
            results = await self._local_client.search_notes(keyword, limit)
            logger.info(f"[search] QR Worker session fallback 成功: {len(results)} notes")
            await self._emit_degraded(
                "插件 MCP 签名失败，已 fallback 到 QR Worker session 搜索",
                fallback_used="qr_worker_session",
            )
            return results
        except Exception as e:
            logger.error(f"[search] QR Worker session fallback 也失败: {e}")
            # session 可能已失效，标记为断开，下次重连
            if isinstance(self._local_client, XhsMCPClient):
                self._local_client._connected = False
                self._local_client._session_id = None
            await self._emit_degraded(
                f"所有搜索方式都失败: {e}",
                fallback_used="none",
            )
            raise

    async def search_notes_with_details(
        self,
        keyword: str,
        limit: int = 8,
        detail_top_n: int = 5,
    ) -> dict[str, Any]:
        """搜索笔记并采集 top N 条详情（带频率控制 + fallback）。

        通过点击搜索结果卡片进入详情页，拦截 feed XHR，
        提取 likes/comments/collects/shares 等完整字段。

        Returns:
            {"results": [...], "details_collected": int}
        """
        # 频率控制（详情采集比普通搜索更慢，但频率限制相同）
        try:
            await self._enforce_search_rate_limit()
        except RuntimeError as e:
            logger.warning(f"[search_with_details] {e}")
            await self._emit_degraded(str(e), fallback_used="none")
            return {"results": [], "details_collected": 0}

        # 详情采集只支持 local_client（QR Worker），插件 MCP 不支持
        if not self._local_client:
            await self._emit_degraded("无 local client 可用", fallback_used="none")
            raise RuntimeError("无 local client 可用")

        await self._ensure_local_client_cookies()

        try:
            if isinstance(self._local_client, XhsMCPClient):
                result = await self._local_client.search_notes_with_details(
                    keyword, limit, detail_top_n
                )
                logger.info(
                    f"[search_with_details] 成功: "
                    f"{len(result.get('results', []))} notes, "
                    f"{result.get('details_collected', 0)} details"
                )
                await self._emit_degraded(
                    "使用 QR Worker 详情采集模式（点击进入+拦截feed XHR）",
                    fallback_used="qr_worker_details",
                )
                return result
            else:
                # 非 XhsMCPClient 不支持详情采集，降级为普通搜索
                logger.warning("[search_with_details] local_client 非 XhsMCPClient，降级为普通搜索")
                results = await self._local_client.search_notes(keyword, limit)
                return {"results": results, "details_collected": 0}
        except Exception as e:
            logger.error(f"[search_with_details] 失败: {e}")
            if isinstance(self._local_client, XhsMCPClient):
                self._local_client._connected = False
                self._local_client._session_id = None
            await self._emit_degraded(f"详情采集失败: {e}", fallback_used="none")
            raise

    async def _ensure_local_client_cookies(self) -> None:
        """确保 local_client 有有效 cookies，没有或过期就从数据库加载最新的 qrcode 账号。

        cookies 过期检测：local_client 连接失败时清除 cookies，触发重新加载。
        冷却控制：数据库无账号时避免每次搜索都查库（5 分钟冷却）。
        """
        client = self._local_client
        if not client or not isinstance(client, XhsMCPClient):
            return
        # 已有 cookies 且连接正常就不重复加载
        if client._cookies and client._connected:
            return
        # 冷却期内跳过（避免数据库无账号时每次搜索都查库）
        now = time.time()
        if now - self._last_cookies_check_at < self._cookies_check_cooldown:
            logger.debug(
                f"[search] cookies 加载冷却期内，跳过数据库查询"
                f"（{self._cookies_check_cooldown - (now - self._last_cookies_check_at):.0f}s remaining）"
            )
            return
        self._last_cookies_check_at = now
        logger.info("[search] local_client 无 cookies 或连接失效，从数据库加载最新的 qrcode 账号")
        try:
            from sqlalchemy import select
            from app.db.session import AsyncSessionLocal
            from app.db.models import XhsAccount, LoginMethod, AccountStatus
            from app.crypto.token_crypto import TokenCrypto

            crypto = TokenCrypto()
            async with AsyncSessionLocal() as db:
                stmt = (
                    select(XhsAccount)
                    .where(XhsAccount.login_method == LoginMethod.QRCODE)
                    .where(XhsAccount.status == AccountStatus.ACTIVE)
                    .where(XhsAccount.session_data_encrypted.is_not(None))
                    .order_by(XhsAccount.created_at.desc())
                    .limit(1)
                )
                account = await db.scalar(stmt)
                if not account:
                    logger.warning("[search] 数据库无 qrcode 账号 cookies")
                    return
                session_data = crypto.decrypt_dict(account.session_data_encrypted)
                cookies = (
                    session_data.get("cookies", [])
                    if isinstance(session_data, dict)
                    else session_data
                )
                if cookies:
                    client.set_cookies(cookies)
                    # 成功加载后重置冷却
                    self._last_cookies_check_at = 0.0
                    logger.info(
                        f"[search] 已加载账号 {account.xhs_nickname} 的 cookies "
                        f"({len(cookies)} items)"
                    )
        except Exception as e:
            logger.warning(f"[search] 加载 cookies 失败: {e}")

    async def publish_note(
        self, title: str, content: str, images_b64: list[str]
    ) -> dict[str, Any]:
        """发布笔记。每次都先试插件，失败才 fallback 到 local（不永久切换）。

        注意：plugin_client.publish_note 失败时返回 {success: False, message: ...}
        而非抛异常，因此用 success 字段判断；抛异常时也触发 fallback。
        """
        last_err: Exception | None = None
        if self._plugin_client:
            try:
                result = await self._plugin_client.publish_note(title, content, images_b64)
                if result.get("success"):
                    return result
                # 插件返回失败：记录错误，尝试 fallback
                last_err = RuntimeError(result.get("message", "plugin publish failed"))
                logger.warning(f"Plugin MCP publish returned failure: {last_err}")
            except Exception as e:
                last_err = e
                logger.warning(f"Plugin MCP publish failed: {e}")
        if self._local_client:
            try:
                return await self._local_client.publish_note(title, content, images_b64)
            except Exception as e:
                logger.warning(f"Local MCP publish failed: {e}")
                last_err = e
        if last_err:
            return {"success": False, "post_id": "", "message": str(last_err)}
        return {"success": False, "post_id": "", "message": "无可用 MCP client"}

    async def check_publish_result(self) -> dict[str, Any]:
        """回查半自动发布结果。半自动发布走 local client（Playwright worker），
        plugin client（浏览器扩展）直接发布完成无需回查。

        Returns:
            {"status": "pending"|"published"|"failed"|"session_invalid"|"not_applicable",
             "url": str, "message": str}
            not_applicable: 无 local client（说明走 plugin 已发布完成）
        """
        if self._local_client:
            try:
                return await self._local_client.check_publish_result()
            except Exception as e:
                logger.warning(f"Local MCP check_publish_result failed: {e}")
                return {
                    "status": "session_invalid",
                    "url": "",
                    "message": str(e),
                }
        return {
            "status": "not_applicable",
            "url": "",
            "message": "半自动发布未启用（无 local MCP client）",
        }

    async def get_account_info(self, account_id: str) -> dict[str, Any]:
        """获取账号信息。每次都先试插件，失败才 fallback 到 local。"""
        last_err: Exception | None = None
        if self._plugin_client:
            try:
                return await self._plugin_client.get_account_info(account_id)
            except Exception as e:
                logger.warning(f"Plugin MCP get_account_info failed: {e}")
                last_err = e
        if self._local_client:
            try:
                return await self._local_client.get_account_info(account_id)
            except Exception as e:
                logger.warning(f"Local MCP get_account_info failed: {e}")
                last_err = e
        raise RuntimeError(f"无可用 MCP client 或全部失败: {last_err}")

    async def get_current_user_info(self) -> dict[str, Any]:
        """Fetch real current-user info. Raises RuntimeError on failure (no mock).

        每次都先试插件，失败才 fallback 到 local（不永久切换）。
        """
        last_err: Exception | None = None
        if self._plugin_client:
            try:
                return await self._plugin_client.get_current_user_info()
            except Exception as e:
                logger.warning(f"Plugin MCP get_current_user_info failed: {e}")
                last_err = e
        if self._local_client:
            try:
                return await self._local_client.get_current_user_info()
            except Exception as e:
                logger.warning(f"Local MCP get_current_user_info failed: {e}")
                last_err = e
        raise RuntimeError(
            f"Failed to fetch real user info from Xiaohongshu: {last_err}"
        )


mcp_manager = MCPClientManager()


async def init_mcp_clients() -> None:
    from app.config import get_settings
    from app.agents.skills.mcp.plugin_client import PluginMCPClient
    settings = get_settings()
    local_client = XhsMCPClient(MCPConfig(mode="local"))
    mcp_manager.set_local_client(local_client)
    # 不在启动时 connect（此时没有 cookies），等 refresh_session 或
    # update_mcp_cookies_from_session 注入 cookies 后再 connect
    logger.info("Local MCP client registered (deferred connect until cookies ready)")
    if settings.mcp_plugin_enabled:
        plugin_client = PluginMCPClient(MCPConfig(mode="plugin"))
        mcp_manager.set_plugin_client(plugin_client)
        try:
            await plugin_client.connect()
        except Exception as e:
            logger.warning(f"Plugin MCP connect failed: {e}")
    logger.info("MCP clients initialized")


def sync_cookies_to_local_client(cookies: list[dict[str, Any]] | dict[str, str]) -> bool:
    """把 cookies 注入 local MCP client（同步，供 refresh_session 调用）。

    cookies 格式：
    - list[dict]: Playwright export_cookies 格式
    - dict[str, str]: name→value 映射
    """
    client = mcp_manager._local_client
    if not client or not isinstance(client, XhsMCPClient):
        logger.warning("sync_cookies_to_local_client: local client not available")
        return False
    client.set_cookies(cookies)
    logger.info(f"Cookies synced to local MCP client ({len(client._cookies)} items)")
    return True


async def update_mcp_cookies_from_session(qr_id: str) -> bool:
    """扫码登录后把 cookies 同步到 MCP clients。"""
    from app.account.login_service import _active_sessions
    session = _active_sessions.get(qr_id)
    if not session or not session.get('cookies'):
        logger.warning(f"No cookies in session {qr_id}")
        return False
    cookies = session['cookies']
    # local client
    if mcp_manager._local_client and isinstance(mcp_manager._local_client, XhsMCPClient):
        mcp_manager._local_client.set_cookies(cookies)
    # plugin client 不用 cookies（走浏览器扩展）
    logger.info(f"Cookies synced to MCP clients from session {qr_id}")
    return True
