"""Состояние управления сканером."""

from __future__ import annotations

from monik.domain.enums.base import DomainEnum


class ScannerRunState(DomainEnum):
    """Разрешено ли сейчас начинать новые циклы сканирования.

    Это **не** health: сканер, остановленный оператором, полностью
    работоспособен (``19_HEALTH_MONITORING.md`` §54). Поэтому состояние
    хранится отдельно от состояния подсистем.
    """

    #: Новые циклы Level 1 запускаются по расписанию.
    RUNNING = "running"
    #: Новые циклы не начинаются; принятые Level 2 Job доводятся до конца.
    PAUSED = "paused"
    #: Запрошен перезапуск процесса.
    RESTARTING = "restarting"


class ScannerStopReason(DomainEnum):
    """Почему сканирование прекращено.

    Причина определяет текст уведомления и его важность. Штатная
    остановка оператором и аварийное завершение — разные события, и
    сообщать о них одинаково нельзя (``19_HEALTH_MONITORING.md`` §48).
    """

    OPERATOR = "operator"
    RESTART = "restart"
    SHUTDOWN = "shutdown"
    CRITICAL_FAILURE = "critical_failure"
