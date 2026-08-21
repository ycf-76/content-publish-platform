"""FastAPI 应用入口。
仅搭建骨架：CORS 中间件 + 路由注册 + lifespan。
具体业务逻辑在后续 Phase 实现。
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
import logging
import os

from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.routers import account, auth, chat, chat_agent, chat_session, config, esther_factory, mcp_bridge, memory, plugins, proxy, recovery, review, rollback, search, skills, sse, topic_pool, workflow
from app.config import get_settings
from app.db.session import engine, Base
import app.db.models  # noqa: F401 — ensure all ORM models registered with Base.metadata

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """应用生命周期：启动时初始化DB，关闭时释放资源。"""
    # 启动时自动创建表
    logger.info("Initializing database tables...")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables ready")
    except Exception as e:
        logger.warning(f"Database init skipped: {e}")

    # 初始化 LangSmith 追踪（设置环境变量，LangGraph 运行自动上报）
    if settings.langchain_tracing_v2 and settings.langchain_api_key:
        import os
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
        os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project
        os.environ["LANGCHAIN_ENDPOINT"] = settings.langchain_endpoint
        # 国内网络优化：增大超时 + 重试，避免 SSL 写超时
        os.environ.setdefault("LANGCHAIN_TIMEOUT", "60")
        # 限制单次上报大小（5MB），避免大 trace 上传失败
        os.environ.setdefault("LANGCHAIN_MAX_PAYLOAD_SIZE", "5242880")
        # 服务密钥只有写入权限，不做读取验证（list_projects/list_sessions 会 403）
        # LangSmith SDK 会在后台异步上报，失败时自动重试
        logger.info(
            f"LangSmith tracing enabled: project={settings.langchain_project}, "
            f"endpoint={settings.langchain_endpoint}"
        )
    else:
        logger.info("LangSmith tracing disabled (set LANGCHAIN_TRACING_V2=true + LANGCHAIN_API_KEY to enable)")

    # 初始化 LangGraph checkpointer（AsyncSqliteSaver 持久化 checkpoint）
    # 必须在 lifespan（async context）中初始化，aiosqlite.connect 需要 await
    logger.info("[lifespan] step 1: init LangGraph checkpointer...")
    try:
        from app.agents.graph import init_global_checkpointer
        await init_global_checkpointer()
        logger.info("LangGraph checkpointer initialized (AsyncSqliteSaver)")
    except Exception as e:
        import traceback
        logger.warning(f"LangGraph checkpointer init failed: {e}\n{traceback.format_exc()}")

    # 初始化 MCP clients（注册 PluginMCPClient 到 mcp_manager）
    logger.info("[lifespan] step 2: init MCP clients...")
    try:
        from app.agents.skills.mcp.xhs_client import init_mcp_clients
        await init_mcp_clients()
        logger.info("MCP clients initialized")
    except Exception as e:
        logger.warning(f"MCP clients init failed: {e}")

    # 初始化多平台内容源（Reddit / HackerNews / 小红书）
    logger.info("[lifespan] step 3: init content sources...")
    try:
        from app.agents.skills.sources.manager import init_sources, source_manager
        await init_sources()
        logger.info(
            f"Content sources initialized: "
            f"platforms={source_manager.list_platforms()}, "
            f"default={source_manager._default_platform}"
        )
    except Exception as e:
        logger.warning(f"Content sources init failed: {e}")

    # 选题池智能监控模块（与主服务同进程，不开独立端口）
    # 建表 + 注册 APScheduler 定时任务 + 启动水位检查（池<50 立即抓取）
    # 路由注册在模块顶层（与其他 router 一起），这里只管生命周期
    logger.info("[lifespan] step 4: init pool monitor...")
    try:
        from app.pool_monitor.main import pool_startup
        # await pool_startup()  # temporarily disabled: Tavily API rate-limited
        logger.info("Pool monitor module skipped (Tavily rate-limited)")
    except Exception as e:
        logger.warning(f"Pool monitor init failed: {e}")

    # 反馈闭环定时任务（T+7 回采 + 权重校准）
    logger.info("[lifespan] step 4.5: init performance collector scheduler...")
    try:
        from app.pool_monitor.scheduler import scheduler
        from app.services.performance_collector import (
            collect_performance_7d,
            calibrate_weights,
        )
        scheduler.add_job(
            collect_performance_7d,
            "cron",
            hour=3,
            minute=0,
            id="collect_performance_7d",
            replace_existing=True,
        )
        scheduler.add_job(
            calibrate_weights,
            "cron",
            day_of_week="mon",
            hour=4,
            minute=0,
            id="calibrate_weights",
            replace_existing=True,
        )
        logger.info("Performance collector scheduler registered (T+7 daily 03:00, calibration weekly Mon 04:00)")
    except Exception as e:
        logger.warning(f"Performance collector scheduler init failed: {e}")

    # 工作流僵尸清理：PAUSED 超时终止 + running 卡死挂起
    logger.info("[lifespan] step 4.6: init workflow cleanup scheduler...")
    try:
        from apscheduler.triggers.interval import IntervalTrigger
        from app.pool_monitor.scheduler import scheduler
        from app.services.workflow_cleanup import cleanup_stale_workflows

        scheduler.add_job(
            cleanup_stale_workflows,
            IntervalTrigger(minutes=10),
            id="workflow_cleanup",
            name="工作流僵尸清理",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        logger.info("Workflow cleanup scheduler registered (every 10 min)")
    except Exception as e:
        logger.warning(f"Workflow cleanup scheduler init failed: {e}")

    # 初始化 Redis 缓存
    logger.info("[lifespan] step 5: init Redis cache...")
    try:
        from app.cache import redis_client
        await redis_client.connect()
        mode = "Redis" if redis_client.is_connected else "in-memory fallback"
        logger.info(f"Cache initialized ({mode})")
    except Exception as e:
        logger.warning(f"Redis cache init failed: {e}")

    # Phase 5: 初始化节点注册中心（动态工作流编排支持）
    try:
        from app.core.node_registry import register_default_workflow_nodes
        success = register_default_workflow_nodes()
        if success:
            logger.info("✅ NodeRegistry initialized with default workflow nodes")
        else:
            logger.warning("⚠️ NodeRegistry initialization failed (some nodes may not be registered)")
    except Exception as e:
        logger.warning(f"NodeRegistry init failed: {e} (dynamic workflow features may be limited)")

    # Phase 5.5: 初始化插件→工作流节点桥接（扫描并注册所有 workflow_node 插件）
    logger.info("[lifespan] step 5.5: init plugin-workflow bridge...")
    try:
        from app.core.plugin_node_bridge import initialize_plugin_nodes
        bridge_result = await initialize_plugin_nodes()
        
        if bridge_result["success"]:
            logger.info(
                f"✅ Plugin-Workflow bridge initialized: "
                f"{bridge_result['registered_count']}/{bridge_result['plugins_scanned']} nodes registered"
            )
            
            if bridge_result["errors"]:
                for err in bridge_result["errors"][:3]:  # 只打印前3个错误
                    logger.warning(f"   ⚠️ {err}")
        else:
            logger.warning(
                f"⚠️ Plugin-Workflow bridge init failed: {bridge_result['errors'][:1]}"
            )
    except Exception as e:
        logger.warning(f"Plugin-Workflow bridge init failed: {e} (plugin nodes unavailable)")

    # Phase 5.6: 同步插件到数据库（扫描 plugins/builtin/ + plugins/third_party/ → upsert DB）
    logger.info("[lifespan] step 5.6: sync all plugins (builtin + third_party) to DB...")
    try:
        from app.core.sync_builtin_plugins import sync_all_plugins_to_db
        sync_result = await sync_all_plugins_to_db()
        logger.info(
            f"✅ Plugins synced: "
            f"{sync_result['synced']}/{sync_result['scanned']} upserted, "
            f"{sync_result['skipped']} unchanged"
        )
    except Exception as e:
        logger.warning(f"Plugins sync failed: {e} (plugin list may be incomplete)")

    # Phase 5.7: 预置内置工作流模板到数据库
    logger.info("[lifespan] step 5.7: seed builtin workflow definitions...")
    try:
        from app.db.seed_workflow_definitions import seed_builtin_workflow_definitions
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as seed_db:
            seed_result = await seed_builtin_workflow_definitions(seed_db)
            logger.info(
                f"✅ Builtin workflow definitions seeded: "
                f"{seed_result['seeded']} new, {seed_result['skipped']} existing"
            )
    except Exception as e:
        logger.warning(f"Builtin workflow definitions seed failed: {e} (templates may be unavailable)")

    logger.info("[lifespan] all steps done, entering yield")

    yield

    # 关闭资源
    # 关闭 Redis 连接
    try:
        from app.cache import redis_client
        await redis_client.close()
        logger.info("Redis connection closed")
    except Exception as e:
        logger.warning(f"Redis close failed: {e}")
    # 选题池调度器关闭
    try:
        from app.pool_monitor.main import pool_shutdown
        pool_shutdown()
    except Exception as e:
        logger.warning(f"Pool monitor shutdown failed: {e}")
    try:
        from app.agents.skills.sources.manager import source_manager
        await source_manager.close_all()
    except Exception as e:
        logger.warning(f"Content sources close failed: {e}")
    await engine_dispose()


async def engine_dispose() -> None:
    """关闭数据库引擎连接池。"""
    from app.db.session import engine
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    description="多智能体小红书创作平台后端服务",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback
    tb = traceback.format_exc()
    logger.error(f"Unhandled exception on {request.method} {request.url}: {exc}\n{tb}")
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal Server Error: {str(exc)}", "traceback": tb},
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """P2：API 限流中间件，基于 Redis 滑动窗口计数器。

    规则：每个 user_id 每分钟最多 RATE_LIMIT_PER_MINUTE 次请求。
    未登录用户按 IP 限流。
    配置类、插件类、Skills 类等轻量查询接口不限流。
    """

    RATE_LIMIT_PER_MINUTE = 300
    WINDOW_SECONDS = 60

    RATE_LIMIT_EXEMPT_PATHS = {
        "/health", "/docs", "/redoc", "/openapi.json",
        "/api/v1/plugins", "/api/v1/plugins/installed",
        "/api/v1/skills", "/api/v1/config",
    }

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self.RATE_LIMIT_EXEMPT_PATHS or request.url.path.startswith("/api/v1/plugins") or request.url.path.startswith("/api/v1/skills") or request.url.path.startswith("/api/v1/config"):
            return await call_next(request)

        from app.cache import redis_client

        user_id = None
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            try:
                from app.security import verify_jwt
                payload = verify_jwt(auth_header[7:])
                user_id = payload.get("sub")
            except Exception:
                pass

        limit_key = f"ratelimit:user:{user_id}" if user_id else f"ratelimit:ip:{request.client.host if request.client else 'unknown'}"

        try:
            count = await redis_client.incr(limit_key)
            if count == 1:
                await redis_client.expire(limit_key, self.WINDOW_SECONDS)

            if count > self.RATE_LIMIT_PER_MINUTE:
                return JSONResponse(
                    status_code=429,
                    content={"detail": f"请求过于频繁，请稍后再试（限制：{self.RATE_LIMIT_PER_MINUTE}次/分钟）"},
                )
        except Exception:
            pass

        response = await call_next(request)
        return response


app.add_middleware(RateLimitMiddleware)


@app.get("/health", tags=["系统"])
async def health_check() -> dict[str, str]:
    """健康检查端点。"""
    from app.cache import redis_client
    cache_status = "redis" if redis_client.is_connected else "fallback"
    return {"status": "ok", "app": settings.app_name, "cache": cache_status}


# ===== 路由注册 =====
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(chat_agent.router)
app.include_router(chat_session.router)
app.include_router(search.router)
app.include_router(workflow.router)
app.include_router(sse.router)
app.include_router(review.router)
app.include_router(rollback.router)
app.include_router(recovery.router)
app.include_router(account.router)
app.include_router(config.router)
app.include_router(skills.router)
app.include_router(mcp_bridge.router)
app.include_router(proxy.router)
app.include_router(topic_pool.router)
app.include_router(memory.router)
app.include_router(esther_factory.router)
app.include_router(plugins.router)  # Plugin system API (v2.0)
from app.api.routers import workflow_definitions
app.include_router(workflow_definitions.router)  # Workflow Definitions API (v5.0 - Dynamic Orchestration)
from app.api.routers import wechat_bot
app.include_router(wechat_bot.router)  # WeChat Bot API (v6.0 - iLink协议)

# 挂载 uploads 目录为静态文件服务（选题池封面图/详情图 + 用户头像）
_upload_dir = Path(os.environ.get("UPLOAD_DIR", "uploads"))
_upload_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(_upload_dir)), name="uploads")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)