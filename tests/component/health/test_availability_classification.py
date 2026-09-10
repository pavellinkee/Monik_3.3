"""Что именно считается отказом доступности провайдера.

Health описывает **доступность**, а не бизнес-результат конкретного
запроса (``19_HEALTH_MONITORING.md`` §54-56). Регрессия: отказом
считалась любая ошибка, поэтому отсутствие ликвидности у одной пары и
наш собственный открытый circuit breaker портили состояние агрегатора и
давали быстрое мигание healthy → degraded → unavailable → recovering.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from monik.config.sections.health import HealthConfig
from monik.domain.enums.health import ProviderHealthStatus
from monik.domain.enums.operations import RoutingMode
from monik.domain.enums.providers import ProviderId
from monik.domain.errors import (
    AuthenticationError,
    DataError,
    DomainValidationError,
    MonikError,
    NetworkError,
    NoRouteError,
    ProviderError,
    RateLimitError,
    ResourceError,
    TimeoutError,
    UnsupportedError,
)
from monik.domain.models.quote import Quote
from monik.infrastructure.providers.contract import (
    AdapterCapabilities,
    AdapterHealth,
    QuoteRequest,
    RouteValidation,
)
from monik.infrastructure.providers.health_tracking import HealthTrackingAdapter
from monik.services.health.monitor import HealthMonitor
from monik.services.observability import FakeClock
from tests import factories as f

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
PROVIDER = ProviderId.ZERO_X

#: Ошибки, означающие недоступность провайдера.
AVAILABILITY_FAILURES = [
    NetworkError("connection reset", code="http_transport_error"),
    TimeoutError("timed out", code="http_timeout"),
    RateLimitError("429", code="http_rate_limited"),
    ProviderError("500", code="http_server_error"),
    AuthenticationError("rejected", code="http_authentication_failed"),
]

#: Ошибки, которые доступности не опровергают.
NON_AVAILABILITY_FAILURES = [
    NoRouteError("no liquidity", code="provider_no_route"),
    DataError("400", code="http_client_error"),
    DataError("missing field", code="provider_field_missing"),
    DataError("redirected", code="http_redirect_not_followed"),
    DomainValidationError("bad url", code="url_host_not_allowed"),
    UnsupportedError("no such network", code="provider_network_unsupported"),
    ResourceError("breaker is open", code="resource_circuit_open"),
    ResourceError("queue is full", code="resource_queue_overflow"),
]


class _StubAdapter:
    """Адаптер с заданным исходом обращения."""

    def __init__(self, outcome: MonikError | None = None) -> None:
        self._outcome = outcome
        self.provider_id = PROVIDER
        self.capabilities = AdapterCapabilities(
            provider_id=PROVIDER,
            supported_networks=frozenset({f.POLYGON}),
            routing_modes=frozenset({RoutingMode.CLASSIC}),
        )

    async def get_quote(self, request: QuoteRequest) -> Quote:
        if self._outcome is not None:
            raise self._outcome
        return f.quote(provider_id=PROVIDER)

    async def validate_fixed_route(self, request: QuoteRequest) -> RouteValidation:
        raise NotImplementedError

    async def discover_capabilities(self) -> AdapterCapabilities:
        return self.capabilities

    async def discover_fees(self, network_id: object) -> tuple[()]:
        return ()

    async def health_check(self) -> AdapterHealth:
        raise NotImplementedError

    async def aclose(self) -> None:
        return None


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(NOW)


@pytest.fixture
def health(clock: FakeClock) -> HealthMonitor:
    return HealthMonitor(HealthConfig(), clock)


def _request() -> QuoteRequest:
    return QuoteRequest(
        network_id=f.POLYGON,
        operation=f.OperationType.BUY,
        input_token=f.USDT,
        output_token=f.AAVE,
        input_amount=f.USDT.amount_from_base_units(100_000_000),
        request_id=f.RequestId.generate(),
    )


async def _observe(health: HealthMonitor, outcome: MonikError | None, times: int = 1) -> None:
    adapter = HealthTrackingAdapter(_StubAdapter(outcome), health)  # type: ignore[arg-type]
    for _ in range(times):
        if outcome is None:
            await adapter.get_quote(_request())
            continue
        with pytest.raises(type(outcome)):
            await adapter.get_quote(_request())


class TestNonAvailabilityErrors:
    @pytest.mark.parametrize("error", NON_AVAILABILITY_FAILURES, ids=lambda e: e.info.code)
    async def test_does_not_degrade_the_provider(
        self, health: HealthMonitor, error: MonikError
    ) -> None:
        await _observe(health, error, times=10)

        state = health.provider(PROVIDER)
        assert state.status is ProviderHealthStatus.UNKNOWN
        assert state.consecutive_failures == 0

    async def test_does_not_count_as_a_success_either(self, health: HealthMonitor) -> None:
        """Ошибка данных — не наблюдение о доступности ни в какую сторону."""
        await _observe(health, NetworkError("down", code="http_transport_error"), times=2)
        before = health.provider(PROVIDER)

        await _observe(health, NoRouteError("no route", code="provider_no_route"), times=5)

        after = health.provider(PROVIDER)
        assert after.status is before.status
        assert after.consecutive_failures == before.consecutive_failures


class TestAvailabilityErrors:
    @pytest.mark.parametrize("error", AVAILABILITY_FAILURES, ids=lambda e: e.info.code)
    async def test_still_degrades_the_provider(
        self, health: HealthMonitor, error: MonikError
    ) -> None:
        await _observe(health, error, times=4)

        assert health.provider(PROVIDER).status is ProviderHealthStatus.UNAVAILABLE

    async def test_recovery_still_works(self, health: HealthMonitor) -> None:
        await _observe(health, NetworkError("down", code="http_transport_error"), times=4)
        assert health.provider(PROVIDER).status is ProviderHealthStatus.UNAVAILABLE

        await _observe(health, None, times=2)

        assert health.provider(PROVIDER).status is ProviderHealthStatus.HEALTHY


class TestFlapping:
    async def test_missing_liquidity_does_not_flap_the_provider(
        self, health: HealthMonitor
    ) -> None:
        """Смесь удачных пар и пар без маршрута — обычный цикл Level 1.

        Регрессия: такая последовательность за шесть запросов проводила
        провайдера через degraded → unavailable → recovering → healthy.
        """
        await _observe(health, None, times=2)
        assert health.provider(PROVIDER).status is ProviderHealthStatus.HEALTHY

        for _ in range(20):
            await _observe(health, NoRouteError("no route", code="provider_no_route"))
            await _observe(health, None)

        assert health.provider(PROVIDER).status is ProviderHealthStatus.HEALTHY

    async def test_open_breaker_does_not_cascade(self, health: HealthMonitor) -> None:
        """Собственная защита не является доказательством недоступности."""
        await _observe(health, None, times=2)

        await _observe(
            health, ResourceError("breaker is open", code="resource_circuit_open"), times=50
        )

        assert health.provider(PROVIDER).status is ProviderHealthStatus.HEALTHY
