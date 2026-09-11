"""Память об отказах «маршрута нет»."""

from __future__ import annotations

from datetime import timedelta

from monik.config.sections.scanner import NoRouteMemoryConfig
from monik.domain.enums.capability import CapabilityOperation
from monik.domain.enums.providers import ProviderId
from monik.domain.models.capability import CapabilityKey
from monik.services.level1.no_route import NoRouteMemory
from monik.services.observability import FakeClock
from tests import factories as f


def _key(token: object | None = None) -> CapabilityKey:
    return CapabilityKey(
        provider_id=ProviderId.VELORA,
        network_id=f.POLYGON,
        operation=CapabilityOperation.QUOTE_BUY,
        token=(token or f.AAVE.key),
    )


def _memory(**overrides: object) -> tuple[NoRouteMemory, FakeClock]:
    clock = FakeClock(f.NOW)
    config = NoRouteMemoryConfig(**overrides)  # type: ignore[arg-type]
    return NoRouteMemory(config, clock), clock


class TestPause:
    def test_single_refusal_does_not_pause(self) -> None:
        """Один отказ ничего не значит: маршрут мог исчезнуть на миг."""
        memory, _ = _memory(failure_threshold=3)
        memory.remember(_key())
        assert not memory.should_skip(_key())

    def test_threshold_pauses_requests(self) -> None:
        memory, _ = _memory(failure_threshold=3)
        for _ in range(3):
            memory.remember(_key())
        assert memory.should_skip(_key())

    def test_pause_expires_and_the_pair_is_rechecked(self) -> None:
        """Пауза временная: ликвидность может появиться."""
        memory, clock = _memory(failure_threshold=2, recheck_after_hours=24)
        memory.remember(_key())
        memory.remember(_key())
        assert memory.should_skip(_key())

        clock.advance(timedelta(hours=24, seconds=1))
        assert not memory.should_skip(_key())

    def test_success_clears_the_pause_immediately(self) -> None:
        memory, _ = _memory(failure_threshold=2)
        memory.remember(_key())
        memory.remember(_key())
        assert memory.should_skip(_key())

        memory.forget(_key())
        assert not memory.should_skip(_key())

    def test_pairs_are_independent(self) -> None:
        """Отказ по одному токену не влияет на другой."""
        memory, _ = _memory(failure_threshold=2)
        memory.remember(_key())
        memory.remember(_key())
        assert memory.should_skip(_key())
        assert not memory.should_skip(_key(token=f.USDT.key))

    def test_disabled_memory_never_skips(self) -> None:
        memory, _ = _memory(enabled=False, failure_threshold=1)
        memory.remember(_key())
        assert not memory.should_skip(_key())

    def test_paused_lists_only_active_pauses(self) -> None:
        memory, clock = _memory(failure_threshold=1, recheck_after_hours=1)
        memory.remember(_key())
        assert memory.paused() == (_key(),)

        clock.advance(timedelta(hours=1, seconds=1))
        assert memory.paused() == ()
