"""DB 集成测试：ChatSession / ChatMessage CRUD + get_last_workflow_topic。

用 SQLite 内存库隔离，不依赖真实 MySQL。
所有测试在同一个 async 上下文中运行，避免 asyncio.run() 的 event loop 冲突。
"""

import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///test_chat_session.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-db-test")

from sqlalchemy import desc, select, func, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import Base, ChatSession, ChatMessage, User, Workflow, WorkflowStatus, WorkflowDefinition, XhsAccount


async def main():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        echo=False,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _pragma(dbapi_connection, _):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        tables = [User.__table__, XhsAccount.__table__, WorkflowDefinition.__table__, Workflow.__table__, ChatSession.__table__, ChatMessage.__table__]
        for t in tables:
            await conn.run_sync(t.create, checkfirst=True)

    sf = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False,
    )

    passed = 0
    failed = 0

    # === Test 1: create_and_get_session ===
    try:
        async with sf() as db:
            user = User(id="u1", nickname="测试1")
            db.add(user)
            await db.commit()

            s = ChatSession(user_id="u1", title="测试会话")
            db.add(s)
            await db.commit()
            await db.refresh(s)

            assert s.id is not None
            assert s.user_id == "u1"
            assert s.title == "测试会话"

            fetched = await db.get(ChatSession, s.id)
            assert fetched is not None
            assert fetched.title == "测试会话"

        print("  [PASS] create_and_get_session")
        passed += 1
    except Exception as e:
        print(f"  [FAIL] create_and_get_session: {e}")
        failed += 1

    # === Test 2: list_sessions_ordered ===
    try:
        async with sf() as db:
            s1 = ChatSession(user_id="u1", title="会话1")
            s2 = ChatSession(user_id="u1", title="会话2")
            db.add_all([s1, s2])
            await db.commit()

            stmt = (
                select(ChatSession)
                .where(ChatSession.user_id == "u1")
                .order_by(desc(ChatSession.updated_at))
            )
            result = await db.scalars(stmt)
            sessions = result.all()
            assert len(sessions) >= 2

        print("  [PASS] list_sessions_ordered")
        passed += 1
    except Exception as e:
        print(f"  [FAIL] list_sessions_ordered: {e}")
        failed += 1

    # === Test 3: add_message_and_list ===
    try:
        async with sf() as db:
            s = ChatSession(user_id="u1", title="消息测试")
            db.add(s)
            await db.commit()

            m1 = ChatMessage(session_id=s.id, role="user", content="你好")
            m2 = ChatMessage(session_id=s.id, role="assistant", content="你好！")
            db.add_all([m1, m2])
            await db.commit()

            stmt = (
                select(ChatMessage)
                .where(ChatMessage.session_id == s.id)
                .order_by(ChatMessage.created_at)
            )
            result = await db.scalars(stmt)
            messages = result.all()
            assert len(messages) == 2
            assert messages[0].role == "user"
            assert messages[1].role == "assistant"

        print("  [PASS] add_message_and_list")
        passed += 1
    except Exception as e:
        print(f"  [FAIL] add_message_and_list: {e}")
        failed += 1

    # === Test 4: agent_meta_json ===
    try:
        async with sf() as db:
            s = ChatSession(user_id="u1", title="meta测试")
            db.add(s)
            await db.commit()

            meta = {
                "workflow_id": "wf_123",
                "intent": {"action": "full_pipeline", "params": {"topic": "AI教育"}},
                "workflow_status": "running",
            }
            msg = ChatMessage(
                session_id=s.id,
                role="assistant",
                content="正在执行...",
                agent_meta=meta,
            )
            db.add(msg)
            await db.commit()
            await db.refresh(msg)

            assert msg.agent_meta is not None
            assert msg.agent_meta["workflow_id"] == "wf_123"
            assert msg.agent_meta["intent"]["action"] == "full_pipeline"

        print("  [PASS] agent_meta_json")
        passed += 1
    except Exception as e:
        print(f"  [FAIL] agent_meta_json: {e}")
        failed += 1

    # === Test 5: get_last_workflow_id ===
    try:
        async with sf() as db:
            s = ChatSession(user_id="u1", title="wf_id测试")
            db.add(s)
            await db.commit()

            stmt = (
                select(ChatMessage)
                .where(ChatMessage.session_id == s.id, ChatMessage.role == "assistant")
                .order_by(desc(ChatMessage.created_at))
                .limit(1)
            )
            result = await db.scalar(stmt)
            assert result is None

            msg = ChatMessage(
                session_id=s.id,
                role="assistant",
                content="执行中",
                agent_meta={"workflow_id": "wf_abc"},
            )
            db.add(msg)
            await db.commit()

            stmt = (
                select(ChatMessage)
                .where(ChatMessage.session_id == s.id, ChatMessage.role == "assistant")
                .order_by(desc(ChatMessage.created_at))
                .limit(1)
            )
            result = await db.scalar(stmt)
            assert result is not None
            assert result.agent_meta.get("workflow_id") == "wf_abc"

        print("  [PASS] get_last_workflow_id")
        passed += 1
    except Exception as e:
        print(f"  [FAIL] get_last_workflow_id: {e}")
        failed += 1

    # === Test 6: get_last_workflow_topic ===
    try:
        async with sf() as db:
            s = ChatSession(user_id="u1", title="topic测试")
            db.add(s)
            await db.commit()

            workflow = Workflow(
                id="wf_topic_test",
                user_id="u1",
                account_id=None,
                topic="AI教育",
                status=WorkflowStatus.COMPLETED,
            )
            db.add(workflow)

            msg = ChatMessage(
                session_id=s.id,
                role="assistant",
                content="完成",
                agent_meta={"workflow_id": "wf_topic_test"},
            )
            db.add(msg)
            await db.commit()

            wf = await db.get(Workflow, "wf_topic_test")
            assert wf is not None
            assert wf.topic == "AI教育"

        print("  [PASS] get_last_workflow_topic")
        passed += 1
    except Exception as e:
        print(f"  [FAIL] get_last_workflow_topic: {e}")
        failed += 1

    # === Test 7: session_updated_at_touch ===
    try:
        import time
        from datetime import UTC, datetime

        async with sf() as db:
            s = ChatSession(user_id="u1", title="touch测试")
            db.add(s)
            await db.commit()
            await db.refresh(s)

            original = s.updated_at
            time.sleep(0.05)

            s.updated_at = datetime.now(UTC)
            await db.commit()
            await db.refresh(s)

            assert s.updated_at >= original

        print("  [PASS] session_updated_at_touch")
        passed += 1
    except Exception as e:
        print(f"  [FAIL] session_updated_at_touch: {e}")
        failed += 1

    # === Test 8: cascade_delete ===
    try:
        async with sf() as db:
            s = ChatSession(user_id="u1", title="级联删除测试")
            db.add(s)
            await db.commit()

            m1 = ChatMessage(session_id=s.id, role="user", content="hi")
            m2 = ChatMessage(session_id=s.id, role="assistant", content="hello")
            db.add_all([m1, m2])
            await db.commit()

            await db.delete(s)
            await db.commit()

            count = await db.scalar(
                select(func.count()).select_from(ChatMessage).where(ChatMessage.session_id == s.id)
            )
            assert count == 0

        print("  [PASS] cascade_delete")
        passed += 1
    except Exception as e:
        print(f"  [FAIL] cascade_delete: {e}")
        failed += 1

    # === Test 9: chat_session service functions ===
    try:
        # chat_session 服务用 AsyncSessionLocal（全局引擎），先在其上建表
        from app.db.session import engine as global_engine
        async with global_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        from app.services import chat_session

        s_dict = await chat_session.create_session("u1", "服务层测试")
        assert s_dict["user_id"] == "u1"
        assert s_dict["title"] == "服务层测试"
        session_id = s_dict["id"]

        fetched = await chat_session.get_session(session_id)
        assert fetched is not None
        assert fetched["id"] == session_id

        msg_dict = await chat_session.add_message(
            session_id, "user", "帮我写一篇AI教育的文章"
        )
        assert msg_dict["role"] == "user"
        assert msg_dict["content"] == "帮我写一篇AI教育的文章"

        msg_dict2 = await chat_session.add_message(
            session_id, "assistant", "正在执行...",
            agent_meta={"workflow_id": "wf_service_test"},
        )
        assert msg_dict2["agent_meta"]["workflow_id"] == "wf_service_test"

        messages = await chat_session.list_messages(session_id)
        assert len(messages) == 2

        last_wf_id = await chat_session.get_last_workflow_id(session_id)
        assert last_wf_id == "wf_service_test"

        sessions = await chat_session.list_sessions("u1")
        assert len(sessions) >= 1

        print("  [PASS] chat_session service functions")
        passed += 1
    except Exception as e:
        print(f"  [FAIL] chat_session service functions: {e}")
        failed += 1

    # === Cleanup ===
    async with engine.begin() as conn:
        for t in [ChatMessage.__table__, ChatSession.__table__, Workflow.__table__, WorkflowDefinition.__table__, XhsAccount.__table__, User.__table__]:
            await conn.run_sync(t.drop, checkfirst=True)
    await engine.dispose()

    print(f"\n  DB Integration Test: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    import asyncio
    success = asyncio.run(main())
    exit(0 if success else 1)