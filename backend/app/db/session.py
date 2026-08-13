"""SQLAlchemy 异步引擎与 Base。

多数据库兼容：当 DATABASE_URL 为 sqlite/mysql 时，自动把 PostgreSQL 的
JSONB 类型降级为通用 JSON，让 SQLite/MySQL 也能建表（生产用 PostgreSQL
时不受影响）。
"""

from collections.abc import AsyncGenerator

import sqlalchemy
from sqlalchemy.dialects import postgresql as _pg
from sqlalchemy.dialects import mysql as _mysql
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()
_url = settings.database_url
is_sqlite = _url.startswith('sqlite')
is_mysql = _url.startswith('mysql')

# === 非 PostgreSQL 兼容：JSONB → JSON ===
# 必须在 import app.db.models 之前完成，否则 models.py 顶部的
# `from sqlalchemy.dialects.postgresql import JSONB` 已经绑定到原类型
if is_sqlite or is_mysql:
    _pg.JSONB = sqlalchemy.JSON

if is_sqlite:
    engine = create_async_engine(
        _url, echo=settings.db_echo,
        connect_args={'check_same_thread': False},
    )
elif is_mysql:
    # MySQL: aiomysql 驱动，连接池配置
    # pool_recycle 避免 MySQL 8h 空闲断连（wait_timeout 默认 28800s）
    engine = create_async_engine(
        _url,
        pool_size=settings.db_pool_size, max_overflow=settings.db_max_overflow,
        pool_recycle=3600, pool_pre_ping=True,
        echo=settings.db_echo, future=True,
    )
else:
    engine = create_async_engine(
        _url,
        pool_size=settings.db_pool_size, max_overflow=settings.db_max_overflow,
        echo=settings.db_echo, future=True,
    )

AsyncSessionLocal = async_sessionmaker(
    bind=engine, class_=AsyncSession,
    expire_on_commit=False, autoflush=False,
)

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

class Base(DeclarativeBase):
    pass
