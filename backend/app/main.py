"""FastAPI 应用入口。
仅搭建骨架：CORS 中间件 + 路由注册 + lifespan。
具体业务逻辑在后续 Phase 实现。
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import account, auth, config, mcp_bridge, memory, proxy, recovery, review, rollback, search, skills, sse, topic_pool, workflow
from app.config import get_settings
from app.db.session import engine, Base
from app.db.models import User, XhsAccount, Workflow, WorkflowNode, TopicPoolItem

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
            # topic_pool_items 增量迁移：create_all 不会给已存在的表加列，
            # 手动补齐 v2 新增字段（collects/shares/fans_count/images）。
            from sqlalchemy import text, inspect as sa_inspect
            try:
                def _has_col(sync_conn, table: str, col: str) -> bool:
                    insp = sa_inspect(sync_conn)
                    return col in {c["name"] for c in insp.get_columns(table)}
                # MySQL 用 JSON，PostgreSQL 用 JSONB，SQLite 用 JSON
                json_type = "JSON"
                for col in ("collects", "shares", "fans_count"):
                    if not await conn.run_sync(_has_col, "topic_pool_items", col):
                        await conn.execute(text(
                            f"ALTER TABLE topic_pool_items ADD COLUMN {col} INT NOT NULL DEFAULT 0"
                        ))
                if not await conn.run_sync(_has_col, "topic_pool_items", "images"):
                    await conn.execute(text(
                        f"ALTER TABLE topic_pool_items ADD COLUMN images {json_type} NULL"
                    ))
                # v6 合并：选题池监控字段（auto_source/simhash/heat_score/heat_status/dimensions/published_at）
                for col, col_type in [
                    ("auto_source", "VARCHAR(20) NOT NULL DEFAULT 'manual'"),
                    ("simhash_fingerprint", "VARCHAR(64) NULL"),
                    ("heat_score", "FLOAT NOT NULL DEFAULT 0"),
                    ("heat_status", "VARCHAR(20) NOT NULL DEFAULT '活跃'"),
                    ("dimensions", json_type),
                    ("published_at", "DATETIME NULL"),
                ]:
                    if not await conn.run_sync(_has_col, "topic_pool_items", col):
                        await conn.execute(text(
                            f"ALTER TABLE topic_pool_items ADD COLUMN {col} {col_type}"
                        ))
                # v7 详情页字段：tags（关键词标签）/ ai_summary（AI详细摘要）/
                # view_count（访问次数）/ ai_summary_generated_at（AI摘要生成时间）
                for col, col_type in [
                    ("tags", json_type),
                    ("ai_summary", "TEXT NULL"),
                    ("view_count", "INT NOT NULL DEFAULT 0"),
                    ("ai_summary_generated_at", "DATETIME NULL"),
                ]:
                    if not await conn.run_sync(_has_col, "topic_pool_items", col):
                        await conn.execute(text(
                            f"ALTER TABLE topic_pool_items ADD COLUMN {col} {col_type}"
                        ))
                logger.info("topic_pool_items migration checked (v6 monitor + v7 detail fields added)")
            except Exception as me:
                logger.warning(f"topic_pool_items migration skipped: {me}")
        logger.info("Database tables ready")
        # 用户通过小红书扫码登录自动创建（/api/auth/qr-login），无需启动时初始化默认用户
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
        await pool_startup()
        logger.info("Pool monitor module started")
    except Exception as e:
        logger.warning(f"Pool monitor init failed: {e}")
    logger.info("[lifespan] all steps done, entering yield")

    yield

    # 关闭资源
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["系统"])
async def health_check() -> dict[str, str]:
    """健康检查端点。"""
    return {"status": "ok", "app": settings.app_name}


# ===== 路由注册 =====
app.include_router(auth.router)
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)