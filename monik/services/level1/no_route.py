"""Память об отказах «маршрута нет».

Часть комбинаций провайдер/сеть/операция/токен стабильно не даёт маршрута:
у токена слишком мало ликвидности в этой сети, и агрегатор отвечает
отрицательно на любую сумму. Спрашивать такую комбинацию в каждом цикле —
трата запросов, которых у нас ограниченное число
(``10_LEVEL_1_SCANNER.md`` §15, ``02_LEVEL1_SCANNER.md`` §76).

Отсутствие маршрута **не является** отсутствием поддержки, поэтому
Capability Registry этим не занимается: там ``UNSUPPORTED`` означает
заявленное провайдером отсутствие поддержки и держится до следующего
discovery (``06_AGGREGATOR_ADAPTERS.md`` §75-77). Ликвидность же может
появиться в любой момент, и решение обязано само истекать.

Поэтому память отдельная и временная: после нескольких отказов подряд
комбинация перестаёт запрашиваться, а по истечении срока проверяется
снова. Первый же успешный ответ стирает запись.

Память живёт в процессе и не переживает перезапуск: это оптимизация
числа запросов, а не источник истины о поддержке. После перезапуска
Monik узнаёт положение дел заново за один цикл.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from monik.config.sections.scanner import NoRouteMemoryConfig
from monik.domain.models.capability import CapabilityKey
from monik.domain.value_objects.timestamps import UtcDatetime
from monik.services.observability.clock import Clock
from monik.services.observability.logging import get_logger, log_fields

__all__ = ["NoRouteMemory"]

_LOGGER = get_logger("services.level1.no_route")


@dataclass(slots=True)
class _Entry:
    """Состояние одной комбинации."""

    failures: int = 0
    skip_until: UtcDatetime | None = None


class NoRouteMemory:
    """Помнит комбинации, которые сейчас не дают маршрута."""

    def __init__(self, config: NoRouteMemoryConfig, clock: Clock) -> None:
        self._config = config
        self._clock = clock
        self._entries: dict[CapabilityKey, _Entry] = {}

    def remember(self, key: CapabilityKey) -> None:
        """Учесть отрицательный ответ по комбинации."""
        if not self._config.enabled:
            return
        entry = self._entries.setdefault(key, _Entry())
        entry.failures += 1
        if entry.failures < self._config.failure_threshold:
            return
        if entry.skip_until is not None:
            return
        now = self._clock.now()
        entry.skip_until = now + timedelta(hours=self._config.recheck_after_hours)
        _LOGGER.info(
            "combination has no route; requests paused until recheck",
            extra=log_fields(
                capability=str(key),
                failures=entry.failures,
                recheck_at=str(entry.skip_until),
            ),
        )

    def forget(self, key: CapabilityKey) -> None:
        """Стереть запись: комбинация снова даёт маршрут."""
        entry = self._entries.pop(key, None)
        if entry is not None and entry.skip_until is not None:
            _LOGGER.info(
                "combination has a route again; requests resumed",
                extra=log_fields(capability=str(key)),
            )

    def should_skip(self, key: CapabilityKey) -> bool:
        """Пропустить ли комбинацию в этом цикле."""
        if not self._config.enabled:
            return False
        entry = self._entries.get(key)
        if entry is None or entry.skip_until is None:
            return False
        if self._clock.now() < entry.skip_until:
            return True
        # Срок истёк: комбинация проверяется заново с чистого счёта.
        del self._entries[key]
        return False

    def paused(self) -> tuple[CapabilityKey, ...]:
        """Комбинации, запросы по которым сейчас приостановлены."""
        now = self._clock.now()
        return tuple(
            key
            for key, entry in self._entries.items()
            if entry.skip_until is not None and now < entry.skip_until
        )
