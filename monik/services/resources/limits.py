"""Ограничения на использование внешних ресурсов.

Concurrency limit и rate limit — **разные** ограничения
(``12_RESOURCE_MANAGER.md`` §19): первое ограничивает число одновременных
запросов, второе — их частоту. Неограниченная конкурентность запрещена
(``05_RESOURCE_MANAGER.md`` §61).
"""

from __future__ import annotations

from dataclasses import dataclass

from monik.services.observability.clock import Clock

__all__ = ["RateLimiter", "ResourceLimits"]


@dataclass(frozen=True, slots=True)
class ResourceLimits:
    """Лимиты одного ресурса.

    ``min_interval_seconds`` — наименьшая пауза между двумя запросами к
    этому ресурсу. Ограничение действует **внутри одной очереди**: у
    каждого ресурса собственный :class:`RateLimiter`, поэтому пауза
    одного агрегатора не задерживает другие (``05_RESOURCE_MANAGER.md``
    §48). По умолчанию паузы нет: её задаёт тот, кто регистрирует лимиты.
    """

    max_concurrent: int
    requests_per_second: float
    burst: int
    min_interval_seconds: float = 0.0

    def __post_init__(self) -> None:
        if self.max_concurrent < 1:
            raise ValueError("max_concurrent must be at least 1")
        if self.requests_per_second <= 0:
            raise ValueError("requests_per_second must be positive")
        if self.burst < 1:
            raise ValueError("burst must be at least 1")
        if self.min_interval_seconds < 0:
            raise ValueError("min_interval_seconds must not be negative")


class RateLimiter:
    """Token bucket с учётом стоимости запроса.

    Batch не считается автоматически одним запросом: если провайдер
    учитывает каждый элемент отдельно, стоимость передаётся явно
    (``05_RESOURCE_MANAGER.md`` §55-56, ``12_RESOURCE_MANAGER.md`` §48).
    """

    def __init__(self, limits: ResourceLimits, clock: Clock) -> None:
        self._limits = limits
        self._clock = clock
        self._tokens = float(limits.burst)
        self._updated_at = clock.monotonic()
        #: Момент, на который занят последний выданный слот. ``None`` —
        #: слотов ещё не выдавали.
        self._last_slot: float | None = None

    @property
    def burst(self) -> int:
        """Максимальная стоимость запроса, которую корзина может выдать."""
        return self._limits.burst

    @property
    def min_interval_seconds(self) -> float:
        """Наименьшая пауза между запросами к ресурсу."""
        return self._limits.min_interval_seconds

    def reserve(self, units: int = 1) -> float:
        """Занять место в очереди и вернуть паузу перед выполнением.

        Стоимость списывается сразу, поэтому корзина может уйти в минус:
        это и есть очередь ожидающих. Возвращённая пауза — время, через
        которое долг будет покрыт пополнением.

        Поверх корзины действует наименьшая пауза между слотами: она не
        даёт стартовому запасу уйти одним всплеском и разносит запросы
        внутри **этой** очереди.

        Такая резервация заменяет цикл «подождать и попробовать снова».
        Цикл был неверен дважды: ожидающие просыпались одновременно и
        соревновались за одни и те же токены, теряя порядок очереди, а
        погрешность вещественной арифметики могла оставить не хватать
        десятитысячных долей токена — и цикл повторялся вхолостую.
        """
        if units < 1:
            raise ValueError("units must be at least 1")
        self._refill()
        now = self._clock.monotonic()
        self._tokens -= units
        ready = now if self._tokens >= 0 else now - self._tokens / self._limits.requests_per_second
        slot = self._apply_min_interval(ready)
        self._last_slot = slot
        return max(0.0, slot - now)

    def _apply_min_interval(self, ready: float) -> float:
        """Отодвинуть слот, если предыдущий был выдан слишком недавно.

        Пауза считается от предыдущего **выданного** слота, а не от
        текущего момента: иначе несколько одновременно вставших в очередь
        запросов получили бы один и тот же момент выполнения.
        """
        interval = self._limits.min_interval_seconds
        if interval <= 0 or self._last_slot is None:
            return ready
        return max(ready, self._last_slot + interval)

    def _refill(self) -> None:
        now = self._clock.monotonic()
        elapsed = now - self._updated_at
        if elapsed <= 0:
            return
        self._updated_at = now
        self._tokens = min(
            float(self._limits.burst),
            self._tokens + elapsed * self._limits.requests_per_second,
        )
