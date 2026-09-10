"""Классификация ошибок для retry-политики.

Retry-оркестрация принадлежит Resource Manager (``38_INTERFACES.md`` §91):
подсистемы не создают собственные циклы повторов. Здесь определяется только
правило «можно ли повторять», которым Resource Manager пользуется.
"""

from __future__ import annotations

from monik.domain.enums.errors import ErrorCategory, Retryability
from monik.domain.errors.base import ErrorInfo

__all__ = [
    "AVAILABILITY_FAILURE_CATEGORIES",
    "RETRYABLE_CATEGORIES",
    "is_availability_failure",
    "is_retryable",
]

#: Категории, которые допускают повтор без изменения контекста запроса.
RETRYABLE_CATEGORIES: frozenset[ErrorCategory] = frozenset(
    {
        ErrorCategory.NETWORK,
        ErrorCategory.TIMEOUT,
        ErrorCategory.RATE_LIMIT,
        ErrorCategory.PROVIDER,
        ErrorCategory.RESOURCE,
        ErrorCategory.DATABASE,
    }
)


#: Категории, означающие, что **провайдер недоступен**.
#:
#: Health описывает доступность, а не бизнес-результат
#: (``19_HEALTH_MONITORING.md`` §54-56). Отсутствие ликвидности для одной
#: пары, отвергнутый запрос и неподдерживаемая операция говорят о запросе
#: или о данных, а не о работоспособности API: провайдер на них ответил.
#:
#: ``RESOURCE`` сюда не входит намеренно. Это **наши** ограничения —
#: открытый circuit breaker, переполненная очередь, истёкшее ожидание
#: слота. Засчитывать их провайдеру значит превращать собственную защиту
#: в доказательство его недоступности: один открывшийся breaker выдал бы
#: подряд десятки отказов и гарантированно довёл бы провайдера до
#: ``UNAVAILABLE``. Настоящий таймаут запроса относится к ``TIMEOUT`` и
#: учитывается.
AVAILABILITY_FAILURE_CATEGORIES: frozenset[ErrorCategory] = frozenset(
    {
        ErrorCategory.NETWORK,
        ErrorCategory.TIMEOUT,
        ErrorCategory.RATE_LIMIT,
        ErrorCategory.PROVIDER,
        # Отвергнутые credentials делают провайдера непригодным целиком,
        # и оператор обязан это видеть (``18_ERROR_HANDLING.md`` §10).
        ErrorCategory.AUTHENTICATION,
    }
)


def is_availability_failure(error: ErrorInfo) -> bool:
    """Свидетельствует ли ошибка о недоступности провайдера."""
    return error.category in AVAILABILITY_FAILURE_CATEGORIES


def is_retryable(error: ErrorInfo, *, attempts_used: int, max_attempts: int) -> bool:
    """Можно ли повторить операцию после этой ошибки.

    Правила:

    * повтор невозможен, если исчерпан бюджет попыток
      (``CLAUDE.md`` §32: бесконечные повторы запрещены);
    * ``NON_RETRYABLE`` не повторяется никогда — в частности, data errors
      и ошибки аутентификации, для которых повтор не изменит результат;
    * ``CONDITIONAL`` повторяется только для категорий, где повтор
      осмыслен: временный сбой провайдера, rate limit, нехватка ресурса,
      блокировка БД.
    """
    if max_attempts <= 0:
        raise ValueError("max_attempts must be positive")
    if attempts_used < 0:
        raise ValueError("attempts_used must not be negative")
    if attempts_used >= max_attempts:
        return False
    if error.retryability is Retryability.NON_RETRYABLE:
        return False
    if error.retryability is Retryability.RETRYABLE:
        return True
    return error.category in RETRYABLE_CATEGORIES
