"""Категории и severity нормализованных ошибок."""

from __future__ import annotations

from monik.domain.enums.base import DomainEnum


class ErrorCategory(DomainEnum):
    """Категория ошибки (``18_ERROR_HANDLING.md`` §3, ``CLAUDE.md`` §31).

    Список категорий §3 задан как **минимальный**, поэтому реализация его
    расширяет там, где смешение исказило бы смысл:

    * ``DATA`` — некорректные данные провайдера никогда не должны
      превращаться в валидный quote (``CLAUDE.md`` §12);
    * ``UNSUPPORTED`` — заявленное отсутствие поддержки сети или операции
      (``06_AGGREGATOR_ADAPTERS.md`` §75);
    * ``NO_ROUTE`` — провайдер ответил корректно, но маршрута для
      запрошенной комбинации сейчас нет. Это не отказ провайдера и не
      повреждённый ответ: смешивать его с ``DATA`` значит портить
      health, а с ``UNSUPPORTED`` — портить capability (§75-77).
    * ``ROUTE_REJECTED`` — маршрут существует, но провайдер отказался его
      предложить по собственному правилу: например, ожидаемая потеря
      превышает допустимое им влияние на цену. Это тоже штатный
      отрицательный ответ, но причина другая, чем у ``NO_ROUTE``:
      смешав их, мы перестали бы отличать «маршрута нет» от «маршрут
      плох», а это разные сведения о паре и о сумме.
    """

    CONFIGURATION = "configuration"
    VALIDATION = "validation"
    DATA = "data"
    NETWORK = "network"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    AUTHENTICATION = "authentication"
    PROVIDER = "provider"
    UNSUPPORTED = "unsupported"
    NO_ROUTE = "no_route"
    ROUTE_REJECTED = "route_rejected"
    DATABASE = "database"
    RESOURCE = "resource"
    CALCULATION = "calculation"
    CANCELLATION = "cancellation"
    INTERNAL = "internal"


class ErrorSeverity(DomainEnum):
    """Severity ошибки (``18_ERROR_HANDLING.md`` §17-18)."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class Retryability(DomainEnum):
    """Классификация повторяемости (``18_ERROR_HANDLING.md`` §33-36).

    ``CONDITIONAL`` означает, что решение зависит от контекста
    (например, наличие ``Retry-After`` или оставшегося retry budget).
    """

    RETRYABLE = "retryable"
    NON_RETRYABLE = "non_retryable"
    CONDITIONAL = "conditional"
