"""CreativeArtifact 存储层的并发安全：原子写入与读-改-写互斥。

这些用例刻意走真实文件系统（把 _STORE_DIR 指向 tmp_path），
因为要验证的正是「两个协程同时改同一份 JSON」这类只在真实 IO 下才暴露的问题。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from app.cards.composer import compose_deck
from app.cards.operations import CardEdit, apply_card_edit
from app.cards.schema import CardDeck
from app.services import creative_artifact as ca


class FakeLLM:
    async def chat(self, **kwargs):
        return {"content": '{"subtitle":"三点速览","sections":['
                '{"kind":"list","title":"准备物品","items":["雨衣","充电宝"]},'
                '{"kind":"steps","title":"出门步骤","items":["看天气","收拾背包"]},'
                '{"kind":"compare","title":"方式对比","left_title":"旧","right_title":"新",'
                '"rows":[["慢","快"],["多","少"]]}],"closing":"收藏清单"}'}


@pytest.fixture
def store(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setattr(ca, "_STORE_DIR", tmp_path)
    monkeypatch.setattr(ca, "_LOCK_TIMEOUT", 0.05)
    return tmp_path


async def _draft() -> dict:
    return await compose_deck(topic="旅行", content="第一句。第二句。", user_id="u1", llm=FakeLLM())


@pytest.mark.asyncio
async def test_save_artifact_is_atomic_and_round_trips(store):
    artifact = ca.build_artifact(artifact_id="ca_atomic", owner_user_id="u1", card_draft=await _draft())
    ca.save_artifact(artifact)

    loaded = ca.load_artifact("ca_atomic")
    assert loaded is not None
    assert loaded.artifact_id == "ca_atomic"
    assert loaded.card_deck is not None
    # 临时文件必须已经消失，否则说明替换没走完，磁盘上会越堆越多垃圾
    assert list(store.glob("*.tmp-*")) == []


@pytest.mark.asyncio
async def test_failed_write_keeps_the_previous_artifact(store):
    first = ca.build_artifact(artifact_id="ca_atomic", owner_user_id="u1", card_draft=await _draft())
    first.brief.title = "旧标题"
    ca.save_artifact(first)

    second = ca.load_artifact("ca_atomic")
    second.brief.title = "新标题"
    with patch.object(ca.os, "replace", side_effect=OSError("disk full")):
        with pytest.raises(OSError):
            ca.save_artifact(second)

    assert ca.load_artifact("ca_atomic").brief.title == "旧标题"
    assert list(store.glob("*.tmp-*")) == []


def test_file_lock_is_exclusive_between_handles(store):
    path = ca._lock_path("ca_lock")
    first = open(path, "a+b")
    second = open(path, "a+b")
    try:
        assert ca._try_lock(first) is True
        assert ca._try_lock(second) is False
        ca._release_lock(first)
        first.close()
        assert ca._try_lock(second) is True
    finally:
        ca._release_lock(second)
        second.close()


@pytest.mark.asyncio
async def test_artifact_lock_times_out_instead_of_deadlocking(store):
    async with ca.artifact_lock("ca_lock"):
        with pytest.raises(RuntimeError, match="正在被其他操作修改"):
            async with ca.artifact_lock("ca_lock"):
                pass


@pytest.mark.asyncio
async def test_concurrent_card_edits_do_not_overwrite_each_other(store):
    artifact = ca.build_artifact(artifact_id="ca_race", owner_user_id="u1", card_draft=await _draft())
    ca.save_artifact(artifact)

    deck = CardDeck.model_validate(artifact.card_deck)
    page = deck.pages[0]
    block = next(b for b in page.blocks if b.type == "heading")
    edits = [
        CardEdit(page_id=page.id, block_id=block.id, op="set_text", value="甲方标题"),
        CardEdit(page_id=page.id, block_id=block.id, op="set_text", value="乙方标题"),
    ]

    results = await asyncio.gather(
        *(apply_card_edit("ca_race", "u1", artifact.version, edit) for edit in edits),
        return_exceptions=True,
    )

    succeeded = [item for item in results if not isinstance(item, BaseException)]
    failed = [item for item in results if isinstance(item, BaseException)]
    # 同版本号并发提交，必须有且只有一次落盘，另一次要么抢不到锁、要么版本过期
    assert len(succeeded) == 1
    assert all(isinstance(item, RuntimeError) for item in failed)

    stored = ca.load_artifact("ca_race")
    assert stored.version == artifact.version + 1
    stored_heading = next(
        b for b in stored.card_deck["pages"][0]["blocks"] if b["type"] == "heading"
    )
    assert stored_heading["text"] == succeeded[0]["deck"]["pages"][0]["blocks"][0]["text"]
