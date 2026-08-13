"""QR 登录服务（业务端 thin client）。

通过 HTTP 调用独立运行的 qr_http_worker 进程（sync_playwright + 同步 HTTP server），
绕开 uvicorn 事件循环与 playwright.async_api 的冲突。

worker 启动：
    backend\\.venv\\Scripts\\python.exe backend\\app\\account\\qr_http_worker.py 9010

环境变量：
    QR_WORKER_URL  worker 地址，默认 http://127.0.0.1:9010
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

WORKER_URL = os.environ.get("QR_WORKER_URL", "http://127.0.0.1:9010").rstrip("/")

# 业务端轻量会话缓存：qr_id -> {status, message}
# 仅供 account.py bind 路由检查 status 用；真实 user_info / cookies 由 bind 时实时调 worker 获取
_active_sessions: dict[str, dict[str, Any]] = {}

# 模块级 httpx async client（连接池复用）
_http_client: httpx.AsyncClient | None = None


async def _client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=60.0)
    return _http_client


async def _reset_client() -> httpx.AsyncClient:
    """关闭旧客户端并创建新实例（连接池失效时调用）。"""
    global _http_client
    if _http_client and not _http_client.is_closed:
        await _http_client.aclose()
    _http_client = httpx.AsyncClient(timeout=60.0)
    logger.info("httpx.AsyncClient reset (new connection pool)")
    return _http_client


async def _post(path: str, timeout: float = 60.0) -> dict:
    """POST worker 接口，返回 JSON。失败抛 RuntimeError。

    ConnectError 时自动重置连接池并重试一次，
    避免 worker 重启后旧连接池缓存了失败状态。
    """
    c = await _client()
    try:
        resp = await c.post(f"{WORKER_URL}{path}", timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except httpx.ConnectError:
        logger.warning(f"ConnectError on {path}, resetting client and retrying...")
        c = await _reset_client()
        try:
            resp = await c.post(f"{WORKER_URL}{path}", timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except httpx.ConnectError as e:
            raise RuntimeError(f"无法连接 QR worker（{WORKER_URL}），请确认 worker 进程已启动: {e}")
    except Exception as e:
        raise RuntimeError(f"worker 调用失败 {path}: {e}")


async def _get(path: str) -> dict:
    """GET worker 接口，返回 JSON。ConnectError 时自动重连重试。"""
    c = await _client()
    try:
        resp = await c.get(f"{WORKER_URL}{path}", timeout=10.0)
        resp.raise_for_status()
        return resp.json()
    except httpx.ConnectError:
        logger.warning(f"ConnectError on GET {path}, resetting client and retrying...")
        c = await _reset_client()
        try:
            resp = await c.get(f"{WORKER_URL}{path}", timeout=10.0)
            resp.raise_for_status()
            return resp.json()
        except httpx.ConnectError as e:
            raise RuntimeError(f"无法连接 QR worker（{WORKER_URL}），请确认 worker 进程已启动: {e}")
    except Exception as e:
        raise RuntimeError(f"worker 调用失败 {path}: {e}")


class XhsLoginService:
    """通过 worker HTTP 间接驱动 Playwright，业务进程不直接接触 playwright。"""

    async def generate_qrcode(self) -> dict:
        result = await _post("/qrcode", timeout=120.0)
        qr_id = result.get("qr_id", "")
        if qr_id:
            _active_sessions[qr_id] = {"status": "pending", "message": "等待扫码"}
        logger.info(f"QR generated via worker: {qr_id}")
        return result

    async def check_login_status(self, qr_id: str) -> dict:
        result = await _post(f"/status_detect/{qr_id}")
        # 同步业务端缓存
        status = result.get("status", "unknown")
        _active_sessions[qr_id] = {
            "status": status,
            "message": result.get("message", ""),
        }
        return result

    async def confirm_login(self, qr_id: str) -> dict:
        """确认登录：检查 worker 状态，confirmed 才返回成功。

        旧的假 confirm（直接改 status）已废弃，现在必须真扫码。
        """
        result = await self.check_login_status(qr_id)
        if result.get("status") == "confirmed":
            return {"success": True, "message": "已确认登录"}
        return {
            "success": False,
            "message": f"尚未扫码登录（当前状态: {result.get('status', 'unknown')}）",
        }

    async def fetch_user_info(self, qr_id: str) -> dict:
        """扫码成功后从 worker 抓取真实用户信息。"""
        result = await _post(f"/user_info/{qr_id}", timeout=120.0)
        if not result.get("success"):
            raise RuntimeError(result.get("message", "抓取用户信息失败"))
        data = result.get("data", {})
        # 缓存到 _active_sessions 供 bind 路由用
        if qr_id in _active_sessions:
            _active_sessions[qr_id]["user_info"] = data
        return data

    async def fetch_cookies(self, qr_id: str) -> list[dict]:
        """从 worker 导出会话 cookies 供持久化存储。"""
        result = await _post(f"/cookies/{qr_id}", timeout=120.0)
        if not result.get("success"):
            raise RuntimeError(result.get("message", "导出 cookies 失败"))
        cookies = result.get("data", [])
        if qr_id in _active_sessions:
            _active_sessions[qr_id]["cookies"] = cookies
        return cookies

    async def close_session(self, qr_id: str) -> dict:
        """关闭 worker 会话，释放浏览器 ctx。"""
        _active_sessions.pop(qr_id, None)
        try:
            return await _post(f"/close/{qr_id}")
        except Exception as e:
            logger.warning(f"close session {qr_id}: {e}")
            return {"success": False, "message": str(e)}

    async def health_check(self) -> bool:
        try:
            result = await _get("/health")
            return result.get("status") == "ok"
        except Exception:
            return False

    async def close(self) -> None:
        global _http_client
        if _http_client and not _http_client.is_closed:
            await _http_client.aclose()
        _http_client = None


_login_service: XhsLoginService | None = None


def get_login_service() -> XhsLoginService:
    global _login_service
    if _login_service is None:
        _login_service = XhsLoginService()
    return _login_service