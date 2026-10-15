"""Tests for ComputeScheduler — no real API calls."""

from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.adapters.video_pipeline import (
    VideoCapability,
    ProviderSlot,
    ComputeScheduler,
)


class TestProviderSlot:

    def test_available_initial(self):
        slot = ProviderSlot(name="ark", max_concurrent=3)
        assert slot.available == 3
        assert slot.is_cooled_down is True

    def test_available_after_start(self):
        slot = ProviderSlot(name="ark", max_concurrent=3)
        slot.record_start()
        slot.record_start()
        assert slot.available == 1
        assert slot._active == 2

    def test_available_after_success(self):
        slot = ProviderSlot(name="ark", max_concurrent=3)
        slot.record_start()
        slot.record_success(1.5)
        assert slot.available == 3
        assert slot._active == 0

    def test_effective_weight_basic(self):
        slot = ProviderSlot(name="ark", weight=2.0, max_concurrent=3)
        assert slot.effective_weight > 0

    def test_effective_weight_zero_when_full(self):
        slot = ProviderSlot(name="ark", weight=2.0, max_concurrent=2)
        slot.record_start()
        slot.record_start()
        assert slot.effective_weight == 0.0

    def test_effective_weight_zero_when_cooling(self):
        slot = ProviderSlot(name="ark", weight=2.0, max_concurrent=2)
        slot.record_failure(cooldown=300.0)
        assert slot.effective_weight == 0.0
        assert slot.is_cooled_down is False

    def test_latency_ema(self):
        slot = ProviderSlot(name="ark")
        slot.record_start()
        slot.record_success(2.0)
        assert slot._avg_latency == 2.0

        slot.record_start()
        slot.record_success(4.0)
        assert abs(slot._avg_latency - (0.7 * 2.0 + 0.3 * 4.0)) < 0.01

    def test_failure_triggers_cooldown(self):
        slot = ProviderSlot(name="ark")
        slot.record_failure(cooldown=10.0)
        assert slot._total_failures == 1
        assert slot.is_cooled_down is False

    def test_to_dict(self):
        slot = ProviderSlot(name="ark", weight=2.0, max_concurrent=3, priority=10)
        d = slot.to_dict()
        assert d["name"] == "ark"
        assert d["weight"] == 2.0
        assert d["available"] == 3
        assert "effective_weight" in d


class TestComputeSchedulerSelect:

    def test_select_single_provider(self):
        scheduler = ComputeScheduler(slots=[ProviderSlot(name="ark", weight=2.0, max_concurrent=3, priority=10)])
        slot = scheduler.select()
        assert slot is not None
        assert slot.name == "ark"

    def test_select_prefers_higher_effective_weight(self):
        scheduler = ComputeScheduler(slots=[
            ProviderSlot(name="ark", weight=2.0, max_concurrent=3, priority=10),
            ProviderSlot(name="dashscope", weight=1.0, max_concurrent=2, priority=5),
        ])
        slot = scheduler.select()
        assert slot.name == "ark"

    def test_select_skips_full_provider(self):
        ark = ProviderSlot(name="ark", weight=2.0, max_concurrent=1, priority=10)
        ark.record_start()
        scheduler = ComputeScheduler(slots=[
            ark,
            ProviderSlot(name="dashscope", weight=1.0, max_concurrent=2, priority=5),
        ])
        slot = scheduler.select()
        assert slot.name == "dashscope"

    def test_select_skips_cooling_provider(self):
        ark = ProviderSlot(name="ark", weight=2.0, max_concurrent=3, priority=10)
        ark.record_failure(cooldown=300.0)
        scheduler = ComputeScheduler(slots=[
            ark,
            ProviderSlot(name="dashscope", weight=1.0, max_concurrent=2, priority=5),
        ])
        slot = scheduler.select()
        assert slot.name == "dashscope"

    def test_select_all_unavailable_returns_earliest_cooldown(self):
        ark = ProviderSlot(name="ark", weight=2.0, max_concurrent=3)
        ark.record_failure(cooldown=10.0)
        ds = ProviderSlot(name="dashscope", weight=1.0, max_concurrent=2)
        ds.record_failure(cooldown=60.0)
        scheduler = ComputeScheduler(slots=[ark, ds])
        slot = scheduler.select()
        assert slot is not None
        assert slot.name == "ark"

    def test_select_all_empty_returns_none(self):
        scheduler = ComputeScheduler(slots=[])
        slot = scheduler.select()
        assert slot is None

    def test_select_with_required_caps(self):
        with patch("app.adapters.video_pipeline.resolve_provider") as mock_resolve:
            def _make_provider(name):
                if name == "ark":
                    p = MagicMock()
                    p.name = "ark"
                    p.supports = lambda c: c in {VideoCapability.IMAGE_TO_VIDEO, VideoCapability.FIRST_LAST_FRAME}
                    return p
                else:
                    p = MagicMock()
                    p.name = name
                    p.supports = lambda c: c in {VideoCapability.IMAGE_TO_VIDEO}
                    return p
            mock_resolve.side_effect = lambda name: _make_provider(name)

            scheduler = ComputeScheduler(slots=[
                ProviderSlot(name="ark", weight=2.0, max_concurrent=3, priority=10),
                ProviderSlot(name="dashscope", weight=1.0, max_concurrent=2, priority=5),
            ])
            slot = scheduler.select(required_caps={VideoCapability.FIRST_LAST_FRAME})
            assert slot is not None
            assert slot.name == "ark"


class TestComputeSchedulerDispatch:

    @pytest.mark.asyncio
    async def test_dispatch_single_task(self):
        mock_fn = AsyncMock(return_value=b"video_data")
        scheduler = ComputeScheduler(slots=[
            ProviderSlot(name="ark", weight=2.0, max_concurrent=3, priority=10),
        ])
        result, provider = await scheduler.dispatch(mock_fn, provider_name="ark")
        assert result == b"video_data"
        assert provider == "ark"

    @pytest.mark.asyncio
    async def test_dispatch_auto_select(self):
        mock_fn = AsyncMock(return_value=b"video_data")
        scheduler = ComputeScheduler(slots=[
            ProviderSlot(name="ark", weight=2.0, max_concurrent=3, priority=10),
        ])
        result, provider = await scheduler.dispatch(mock_fn)
        assert result == b"video_data"
        assert provider == "ark"

    @pytest.mark.asyncio
    async def test_dispatch_records_latency(self):
        async def slow_fn():
            await asyncio.sleep(0.05)
            return b"video_data"

        scheduler = ComputeScheduler(slots=[
            ProviderSlot(name="ark", weight=2.0, max_concurrent=3, priority=10),
        ])
        result, provider = await scheduler.dispatch(slow_fn, provider_name="ark")
        assert result == b"video_data"
        slot = scheduler._slots["ark"]
        assert slot._avg_latency > 0
        assert slot._total_dispatched == 1

    @pytest.mark.asyncio
    async def test_dispatch_failure_records_and_cools_down(self):
        mock_fn = AsyncMock(side_effect=RuntimeError("API error"))
        scheduler = ComputeScheduler(slots=[
            ProviderSlot(name="ark", weight=2.0, max_concurrent=3, priority=10),
        ])
        with pytest.raises(RuntimeError):
            await scheduler.dispatch(mock_fn, provider_name="ark")
        slot = scheduler._slots["ark"]
        assert slot._total_failures == 1
        assert slot.is_cooled_down is False


class TestComputeSchedulerBatch:

    @pytest.mark.asyncio
    async def test_dispatch_batch_distributes(self):
        async def mock_fn(idx: int) -> bytes:
            return f"video_{idx}".encode()

        scheduler = ComputeScheduler(slots=[
            ProviderSlot(name="ark", weight=2.0, max_concurrent=3, priority=10),
            ProviderSlot(name="dashscope", weight=1.0, max_concurrent=2, priority=5),
        ], global_max_concurrent=6)

        tasks = [(mock_fn, (i,), {}) for i in range(5)]
        results = await scheduler.dispatch_batch(tasks)

        assert len(results) == 5
        for i, (result, provider) in enumerate(results):
            assert result == f"video_{i}".encode()
            assert provider in ("ark", "dashscope")


class TestComputeSchedulerFromConfig:

    def test_from_config_creates_slots(self):
        cfg = {
            "providers": {
                "ark": {"weight": 2.0, "max_concurrent": 3, "priority": 10},
                "dashscope": {"weight": 1.0, "max_concurrent": 2, "priority": 5},
            },
            "global_max_concurrent": 5,
        }
        scheduler = ComputeScheduler.from_config(cfg)
        assert "ark" in scheduler._slots
        assert "dashscope" in scheduler._slots
        assert scheduler._slots["ark"].weight == 2.0
        assert scheduler._global_max == 5

    def test_from_config_empty(self):
        scheduler = ComputeScheduler.from_config(None)
        assert len(scheduler._slots) == 0


class TestComputeSchedulerStatus:

    def test_status_report(self):
        scheduler = ComputeScheduler(slots=[
            ProviderSlot(name="ark", weight=2.0, max_concurrent=3, priority=10),
            ProviderSlot(name="dashscope", weight=1.0, max_concurrent=2, priority=5),
        ], global_max_concurrent=6)
        status = scheduler.status()
        assert status["global_max_concurrent"] == 6
        assert "ark" in status["providers"]
        assert "dashscope" in status["providers"]
        assert status["providers"]["ark"]["available"] == 3


class TestAdaptiveBehavior:

    def test_low_latency_provider_gets_more_weight(self):
        fast = ProviderSlot(name="ark", weight=2.0, max_concurrent=3)
        fast.record_start()
        fast.record_success(1.0)

        slow = ProviderSlot(name="dashscope", weight=2.0, max_concurrent=3)
        slow.record_start()
        slow.record_success(5.0)

        assert fast.effective_weight > slow.effective_weight

    def test_failure_reduces_weight(self):
        clean = ProviderSlot(name="ark", weight=2.0, max_concurrent=3)
        clean.record_start()
        clean.record_success(1.0)

        failing = ProviderSlot(name="dashscope", weight=2.0, max_concurrent=3)
        failing.record_start()
        failing.record_success(1.0)
        failing.record_failure(cooldown=0.0)

        assert clean.effective_weight > failing.effective_weight

    @pytest.mark.asyncio
    async def test_scheduler_shifts_traffic_after_failure(self):
        scheduler = ComputeScheduler(slots=[
            ProviderSlot(name="ark", weight=2.0, max_concurrent=3, priority=10),
            ProviderSlot(name="dashscope", weight=1.0, max_concurrent=3, priority=5),
        ])

        slot1 = scheduler.select()
        assert slot1.name == "ark"

        scheduler._slots["ark"].record_failure(cooldown=300.0)

        slot2 = scheduler.select()
        assert slot2.name == "dashscope"