"""FastAPI 应用入口。
仅搭建骨架：CORS 中间件 + 路由注册 + lifespan。
具体业务逻辑在后续 Phase 实现。
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
import asyncio
import logging
import multiprocessing
import os
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

multiprocessing.freeze_support()

from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.routers import accounts, agents, assets, auth, browser, chat, chat_agent, chat_file, chat_session, codex, config, creative_artifact, dashboard, feishu_bot, feishu_oauth, governance, memory, my_works, plugins, profile, proxy, quality_gate, review, search, skills, sse, topic_pool, workflow, workspace
from app.config import get_settings
from app.db.session import engine, Base
from sqlalchemy import inspect as _sa_inspect, text as _sa_text
import app.db.models  # noqa: F401 — ensure all ORM models registered with Base.metadata

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """应用生命周期：启动时初始化DB，关闭时释放资源。"""
    _health: list[tuple[str, bool, str]] = []

    def _hstep(name: str, ok: bool, detail: str = "") -> None:
        _health.append((name, ok, detail))

    from app.banner import print_banner
    print_banner()

    # 启动时自动创建表
    logger.info("Initializing database tables...")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            try:
                cols = await conn.run_sync(lambda sync: _sa_inspect(sync).get_columns("chat_sessions"))
                if not any(c["name"] == "folder_id" for c in cols):
                    await conn.execute(_sa_text("ALTER TABLE chat_sessions ADD COLUMN folder_id VARCHAR(100) NOT NULL DEFAULT ''"))
                    logger.info("Added chat_sessions.folder_id column")
            except Exception as e2:
                logger.warning(f"chat_sessions.folder_id column check skipped: {e2}")
        logger.info("Database tables ready")
        _hstep("DB tables", True)
    except Exception as e:
        logger.warning(f"Database init skipped: {e}")
        _hstep("DB tables", False, str(e))

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
        _hstep("LangSmith", True)
    else:
        logger.info("LangSmith tracing disabled (set LANGCHAIN_TRACING_V2=true + LANGCHAIN_API_KEY to enable)")
        _hstep("LangSmith", True, "disabled")

    # 初始化 LangGraph checkpointer（AsyncSqliteSaver 持久化 checkpoint）
    # 必须在 lifespan（async context）中初始化，aiosqlite.connect 需要 await
    logger.info("[lifespan] step 1: init LangGraph checkpointer...")
    try:
        from app.agents.graph import init_global_checkpointer
        await init_global_checkpointer()
        logger.info("LangGraph checkpointer initialized (AsyncSqliteSaver)")
        _hstep("Checkpointer", True)
    except Exception as e:
        import traceback
        logger.warning(f"LangGraph checkpointer init failed: {e}\n{traceback.format_exc()}")
        _hstep("Checkpointer", False, str(e))

    # 初始化 MCP clients（注册 PluginMCPClient 到 mcp_manager）
    logger.info("[lifespan] step 2: init MCP clients...")
    try:
        from app.tools.mcp.xhs_client import init_mcp_clients
        await init_mcp_clients()
        logger.info("MCP clients initialized")
        _hstep("MCP clients", True)
    except Exception as e:
        logger.warning(f"MCP clients init failed: {e}")
        _hstep("MCP clients", False, str(e))

    # 初始化多平台内容源（Reddit / HackerNews / 小红书）
    logger.info("[lifespan] step 3: init content sources...")
    try:
        from app.tools.sources.manager import init_sources, source_manager
        await init_sources()
        logger.info(
            f"Content sources initialized: "
            f"platforms={source_manager.list_platforms()}, "
            f"default={source_manager._default_platform}"
        )
        _hstep("Content sources", True)
    except Exception as e:
        logger.warning(f"Content sources init failed: {e}")
        _hstep("Content sources", False, str(e))

    # 选题池智能监控模块（与主服务同进程，不开独立端口）
    # 建表 + 注册 APScheduler 定时任务 + 启动水位检查（池<50 立即抓取）
    # 路由注册在模块顶层（与其他 router 一起），这里只管生命周期
    logger.info("[lifespan] step 4: init pool monitor...")
    try:
        from app.pool_monitor.main import pool_startup
        # await pool_startup()  # temporarily disabled: Tavily API rate-limited
        logger.info("Pool monitor module skipped (Tavily rate-limited)")
        _hstep("Pool monitor", True, "disabled")
    except Exception as e:
        logger.warning(f"Pool monitor init failed: {e}")
        _hstep("Pool monitor", False, str(e))

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
        _hstep("Perf collector", True)
    except Exception as e:
        logger.warning(f"Performance collector scheduler init failed: {e}")
        _hstep("Perf collector", False, str(e))

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
        _hstep("WF cleanup", True)
    except Exception as e:
        logger.warning(f"Workflow cleanup scheduler init failed: {e}")
        _hstep("WF cleanup", False, str(e))

    # 任务清单定时扫描：到期任务执行 + 挂起工作流处理（审核三档/服务端渲染）
    logger.info("[lifespan] step 4.7: init task plan scheduler...")
    try:
        from apscheduler.triggers.interval import IntervalTrigger
        from app.pool_monitor.scheduler import scheduler
        from app.services.task_plan import recover_on_startup, run_task_scan

        # 启动时收敛重启前 in-flight 的任务
        await recover_on_startup()
        scheduler.add_job(
            run_task_scan,
            IntervalTrigger(minutes=1),
            id="task_plan_scan",
            name="任务清单定时扫描",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        logger.info("Task plan scheduler registered (every 1 min)")
        _hstep("Task plan scan", True)
    except Exception as e:
        logger.warning(f"Task plan scheduler init failed: {e}")
        _hstep("Task plan scan", False, str(e))

    # 初始化 Redis 缓存
    logger.info("[lifespan] step 5: init Redis cache...")
    try:
        from app.cache import redis_client
        await redis_client.connect()
        mode = "Redis" if redis_client.is_connected else "in-memory fallback"
        logger.info(f"Cache initialized ({mode})")
        _hstep("Redis cache", True, mode)
    except Exception as e:
        logger.warning(f"Redis cache init failed: {e}")
        _hstep("Redis cache", False, str(e))

    # Phase 5: 初始化节点注册中心（动态工作流编排支持）
    try:
        from app.core.node_registry import register_default_workflow_nodes
        success = register_default_workflow_nodes()
        if success:
            logger.info("✅ NodeRegistry initialized with default workflow nodes")
            _hstep("NodeRegistry", True)
        else:
            logger.warning("⚠️ NodeRegistry initialization failed (some nodes may not be registered)")
            _hstep("NodeRegistry", False, "partial")
    except Exception as e:
        logger.warning(f"NodeRegistry init failed: {e} (dynamic workflow features may be limited)")
        _hstep("NodeRegistry", False, str(e))

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
            _hstep("Plugin bridge", True, f"{bridge_result['registered_count']}/{bridge_result['plugins_scanned']}")
            
            if bridge_result["errors"]:
                for err in bridge_result["errors"][:3]:  # 只打印前3个错误
                    logger.warning(f"   ⚠️ {err}")
        else:
            logger.warning(
                f"⚠️ Plugin-Workflow bridge init failed: {bridge_result['errors'][:1]}"
            )
            _hstep("Plugin bridge", False, str(bridge_result["errors"][:1]))
    except Exception as e:
        logger.warning(f"Plugin-Workflow bridge init failed: {e} (plugin nodes unavailable)")
        _hstep("Plugin bridge", False, str(e))

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
        _hstep("Plugin sync", True, f"{sync_result['synced']}/{sync_result['scanned']}")
    except Exception as e:
        logger.warning(f"Plugins sync failed: {e} (plugin list may be incomplete)")
        _hstep("Plugin sync", False, str(e))

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
        _hstep("WF seed", True, f"{seed_result['seeded']} new")
    except Exception as e:
        logger.warning(f"Builtin workflow definitions seed failed: {e} (templates may be unavailable)")
        _hstep("WF seed", False, str(e))

    # 飞书集成：验证配置并初始化适配器
    logger.info("[lifespan] step 5.8: init Feishu integration...")
    try:
        if settings.feishu_app_id and settings.feishu_app_secret:
            from app.adapters.feishu import FeishuClient
            _feishu_client = FeishuClient(
                app_id=settings.feishu_app_id,
                app_secret=settings.feishu_app_secret,
            )
            logger.info(
                f"✅ Feishu integration ready: app_id={settings.feishu_app_id[:6]}..., "
                f"bitable={'configured' if settings.feishu_bitable_app_token else 'not configured'}"
            )
            _hstep("Feishu", True)
        else:
            logger.info("Feishu integration disabled (set FEISHU_APP_ID + FEISHU_APP_SECRET to enable)")
            _hstep("Feishu", True, "disabled")
    except Exception as e:
        logger.warning(f"Feishu integration init failed: {e}")
        _hstep("Feishu", False, str(e))

    logger.info("[lifespan] step 5.9: auto-restore WeChat bot engines...")
    try:
        from app.rpa.wechat_bot_engine import get_wechat_engine, _CREDENTIALS_DIR
        _wx_cred_path = Path(_CREDENTIALS_DIR)
        _wx_restored = 0
        for _cred_file in _wx_cred_path.glob(".wechat_credentials_*.json"):
            _wx_uid = _cred_file.stem.replace(".wechat_credentials_", "")
            try:
                _wx_eng = get_wechat_engine(_wx_uid)
                await _wx_eng.start()
                if _wx_eng.is_logged_in:
                    _wx_restored += 1
                    logger.info(f"[lifespan] ✅ WeChat engine restored: user={_wx_uid}")
                else:
                    logger.info(f"[lifespan] WeChat engine not logged in: user={_wx_uid}")
            except Exception as _wx_e:
                logger.warning(f"[lifespan] WeChat engine restore failed for {_wx_uid}: {_wx_e}")
        if _wx_restored > 0:
            logger.info(f"✅ WeChat bot engines restored: {_wx_restored}")
            _hstep("WeChat restore", True, f"{_wx_restored} engines")
        else:
            logger.info("No WeChat bot engines to restore (normal if not configured)")
            _hstep("WeChat restore", True, "none")
    except Exception as e:
        logger.warning(f"WeChat auto-restore failed: {e}")
        _hstep("WeChat restore", False, str(e))

    # step 6: 预热 LLM adapter + Skill 注册（消除首次请求 3-4s 冷启动）
    try:
        from app.tools.registry import SkillRegistry, ensure_builtin_skills_registered
        ensure_builtin_skills_registered()
        SkillRegistry.instance().scan_third_party()
        logger.info("[lifespan] step 6: Skill registry warmed up")
        _hstep("Skill warmup", True)
    except Exception as _skill_warm_err:
        logger.warning(f"[lifespan] Skill warmup skipped: {_skill_warm_err}")
        _hstep("Skill warmup", False, str(_skill_warm_err))

    try:
        from app.engine.factory import get_deepseek_llm
        _warm_llm = get_deepseek_llm(model="deepseek-chat")
        if _warm_llm is not None:
            logger.info("[lifespan] step 6: LLM adapter warmed up (deepseek-chat)")
            _hstep("LLM warmup", True, "deepseek-chat")
        else:
            logger.info("[lifespan] step 6: LLM adapter warmup skipped (no API key or circuit open)")
            _hstep("LLM warmup", True, "skipped")
    except Exception as _llm_warm_err:
        logger.warning(f"[lifespan] LLM warmup skipped: {_llm_warm_err}")
        _hstep("LLM warmup", False, str(_llm_warm_err))

    try:
        from app.engine.factory import get_deepseek_llm
        _warm_r1 = get_deepseek_llm(model="deepseek-reasoner")
        if _warm_r1 is not None:
            logger.info("[lifespan] step 6: LLM adapter warmed up (deepseek-reasoner)")
            _hstep("LLM R1 warmup", True)
    except Exception as _llm_r1_warm_err:
        logger.warning(f"[lifespan] LLM R1 warmup skipped: {_llm_r1_warm_err}")
        _hstep("LLM R1 warmup", False, str(_llm_r1_warm_err))

    # step 7: 内置 Playwright 浏览器客户端（G3）——不再依赖外部 QR Worker 进程。
    # 浏览器功能（navigate/snapshot/click 等）同进程内直接调用 Playwright。
    try:
        from app.tools.browser.client import get_browser_client
        _browser_client = get_browser_client()
        if await _browser_client._ensure_initialized():
            logger.info("[lifespan] ✅ Built-in Playwright browser client ready")
            _hstep("Browser (Playwright)", True)
        else:
            logger.warning("[lifespan] ⚠️ Built-in Playwright browser init failed (will lazy-init on first use)")
            _hstep("Browser (Playwright)", True, "lazy")
    except Exception as _browser_init_err:
        logger.warning(f"[lifespan] Built-in browser init failed: {_browser_init_err}")
        _hstep("Browser (Playwright)", False, str(_browser_init_err))

    # step 8: 通用浏览器自动化（G4）——审计 sink 注入 + MCP token 初始化
    try:
        import secrets as _secrets
        from app.api.routers.browser import install_audit_sink, set_generated_mcp_token
        install_audit_sink()
        if not settings.mcp_browser_token:
            _tok = _secrets.token_urlsafe(24)
            set_generated_mcp_token(_tok)
            logger.info(
                "MCP_BROWSER_TOKEN not set; generated for /api/mcp/browser "
                f"(set MCP_BROWSER_TOKEN in .env to pin): {_tok}"
            )
        _hstep("Browser MCP", True)
    except Exception as _browser_err:
        logger.warning(f"[lifespan] browser automation init failed: {_browser_err}")
        _hstep("Browser MCP", False, str(_browser_err))

    logger.info("[lifespan] all steps done, entering yield")

    _ok = sum(1 for _, ok, _ in _health if ok)
    _fail = len(_health) - _ok
    _lines = [f"{'✅' if ok else '❌'} {name:<20s} {detail}" for name, ok, detail in _health]
    logger.info(
        f"\n{'='*60}\n"
        f"  STARTUP HEALTH REPORT  {_ok}/{len(_health)} ok, {_fail} failed\n"
        f"{'='*60}\n"
        + "\n".join(f"  {l}" for l in _lines)
        + f"\n{'='*60}"
    )

    # 事件循环阻塞看门狗：服务"整体无响应"（连 /health 都超时）时，
    # 靠猜定位成本极高。这里周期性测量事件循环延迟，超阈值就把
    # 所有任务的调用栈打进日志，下次冻结可以直接看到是谁堵住了循环。
    _lag_task = asyncio.create_task(_event_loop_watchdog())

    yield

    _lag_task.cancel()

    # 关闭资源
    # 内置 Playwright 浏览器客户端
    try:
        from app.tools.browser.client import get_browser_client
        _bc = get_browser_client()
        await _bc.shutdown()
        logger.info("Built-in Playwright browser client shutdown")
    except Exception as e:
        logger.warning(f"Browser client shutdown failed: {e}")
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
        from app.tools.sources.manager import source_manager
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
    """API 限流中间件，基于 Redis 滑动窗口计数器。

    规则：每个 user_id 每分钟最多 RATE_LIMIT_PER_MINUTE 次请求。
    未登录用户按 IP 限流。
    高频接口（chat、SSE、workflow）豁免限流——这些接口有自己的治理层控制。
    """

    RATE_LIMIT_PER_MINUTE = 600
    WINDOW_SECONDS = 60

    RATE_LIMIT_EXEMPT_PATHS = {
        "/health", "/docs", "/redoc", "/openapi.json",
        "/api/v1/plugins", "/api/v1/plugins/installed",
        "/api/v1/skills", "/api/v1/config",
        "/api/feishu/webhook",
    }
    RATE_LIMIT_EXEMPT_PREFIXES = (
        "/api/v1/plugins",
        "/api/v1/skills",
        "/api/v1/config",
        "/api/v1/codex",
        "/api/workflows/",
        "/api/sse/",
        "/api/chat/sessions",
        "/api/chat/completions",
        "/api/v1/chat/agent",
        "/api/v1/chat/sessions",
    )

    async def dispatch(self, request: Request, call_next):
        # DEV: 登录暂停期间跳过限流，避免所有请求共享同一 IP 桶导致误限
        return await call_next(request)

        if request.url.path in self.RATE_LIMIT_EXEMPT_PATHS:
            return await call_next(request)
        for prefix in self.RATE_LIMIT_EXEMPT_PREFIXES:
            if request.url.path.startswith(prefix):
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


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if "feishu" in request.url.path or request.url.path == "/":
            logger.info(f"[RequestLog] {request.method} {request.url.path} from {request.client.host if request.client else '?'}")
        return await call_next(request)

app.add_middleware(RequestLogMiddleware)
app.add_middleware(RateLimitMiddleware)


async def _event_loop_watchdog(interval_s: float = 10.0) -> None:
    """周期性测量事件循环延迟；明显卡顿则打印所有任务的调用栈。

    背景：多次出现「后端整体无响应、/health 都超时」的冻结事故，
    根因都是某个同步调用堵住了事件循环。看门狗把"卡在哪一行"
    直接写进日志，避免事后靠猜。
    """
    import traceback

    while True:
        try:
            await asyncio.sleep(interval_s)
            t0 = asyncio.get_running_loop().time()
            # 让出一次循环：回来时的偏差就是事件循环被阻塞的时长
            await asyncio.sleep(0)
            lag = (asyncio.get_running_loop().time() - t0) * 1000
            if lag > 3000:
                logger.warning(f"[watchdog] event loop lag {lag:.0f}ms — 可能发生阻塞")
            if lag > 15000:
                logger.error(f"[watchdog] event loop 严重阻塞 ({lag:.0f}ms)，转储任务栈：")
                import linecache
                dumped = 0
                for task in asyncio.all_tasks():
                    if task is asyncio.current_task() or task.done():
                        continue
                    stack = task.get_stack()
                    if not stack:
                        continue
                    parts = []
                    for f in stack[-6:]:
                        src = linecache.getline(f.f_code.co_filename, f.f_lineno).strip()
                        parts.append(f"    {f.f_code.co_filename}:{f.f_lineno} in {f.f_code.co_name} | {src[:90]}")
                    if parts:
                        logger.error(f"[watchdog] ── task [{task.get_name()}]:\n" + "\n".join(parts))
                        dumped += 1
                logger.error(f"[watchdog] 转储完成，共 {dumped} 个挂起任务带栈帧")
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("[watchdog] 异常")
            await asyncio.sleep(interval_s)


@app.get("/health", tags=["系统"])
async def health_check() -> dict[str, str]:
    """健康检查端点。"""
    from app.cache import redis_client
    cache_status = "redis" if redis_client.is_connected else "fallback"
    return {"status": "ok", "app": settings.app_name, "cache": cache_status}


@app.get("/api/debug/loop-config", tags=["系统"])
async def debug_loop_config() -> dict[str, object]:
    """返回 LoopExecutor 关键配置，用于确认运行实例加载的代码版本。

    背景：多次出现「改了代码但 8000 端口被旧实例占着」的部署事故，
    需要一个直接读取运行中模块属性的探针来确认版本，而不是靠猜。
    """
    from app.engine.harness.executor import loop as _loop

    return {
        "default_total_timeout": _loop._DEFAULT_TOTAL_TIMEOUT,
    }


# ===== 路由注册 =====
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(chat_agent.router)
app.include_router(chat_session.router)
app.include_router(chat_file.router)
app.include_router(search.router)
app.include_router(workflow.router)
app.include_router(sse.router)
app.include_router(review.router)
app.include_router(profile.router)  # 用户画像 API (D18 创作者画像)
app.include_router(config.router)
app.include_router(skills.router)
app.include_router(agents.router)
app.include_router(assets.router)
app.include_router(proxy.router)
app.include_router(topic_pool.router)
app.include_router(memory.router)
app.include_router(my_works.router)
app.include_router(accounts.router)  # 平台账号管理 API（账号绑定 + 作品数据回收）
app.include_router(workspace.router)
app.include_router(plugins.router)  # Plugin system API (v2.0)
app.include_router(governance.router)  # Governance Stats API
from app.api.routers import workflow_definitions
app.include_router(workflow_definitions.router)  # Workflow Definitions API (v5.0 - Dynamic Orchestration)
from app.api.routers import wechat_bot
app.include_router(wechat_bot.router)  # WeChat Bot API (v6.0 - iLink协议)
from app.api.routers import feishu_bot
app.include_router(feishu_bot.router)  # Feishu Bot API (飞书集成)
app.include_router(feishu_oauth.router)  # Feishu OAuth user account binding
app.include_router(codex.router)  # Codex mode API (ReAct loop + thin primitives)
app.include_router(browser.router)  # Generic browser automation API (G4: domains + audit)
app.include_router(browser.mcp_router)  # External MCP Server /api/mcp/browser (G4)
from app.api.routers import task_plan
app.include_router(task_plan.router)  # Task Plan API (多日定时发布)

app.include_router(creative_artifact.router)  # CreativeArtifact API (统一创作对象)
app.include_router(quality_gate.router)  # 共享质量门禁 API (P1-3)
app.include_router(dashboard.router)  # 数据看板 API (P0-2)

# 挂载 uploads 目录为静态文件服务（选题池封面图/详情图 + 用户头像）
_upload_dir = Path(os.environ.get("UPLOAD_DIR", "uploads"))
_upload_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(_upload_dir)), name="uploads")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)