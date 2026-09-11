"""Конфигурация token universe."""

from __future__ import annotations

from pydantic import Field

from monik.config.base import ConfigSection
from monik.domain.value_objects.identity import NetworkId, TokenAddress, TokenSymbol

__all__ = ["TokenConfig"]


class TokenConfig(ConfigSection):
    """Описание одного токена.

    Authoritative metadata живёт в Token Registry, но разрешённый набор
    задаётся конфигурацией (``17_CONFIGURATION.md`` §28-29).
    ``decimals`` указывается явно и не выводится из символа
    (``01_PROJECT_REQUIREMENTS.md`` §10).
    """

    network_id: NetworkId
    address: TokenAddress
    symbol: TokenSymbol
    decimals: int = Field(ge=0, le=36)
    enabled: bool = True
    rank: int | None = Field(default=None, ge=1)
    #: Привязан ли токен к доллару. Объявляет оператор: код не угадывает
    #: это по символу. Признак нужен ровно для одного: когда агрегатор
    #: присылает стоимость газа в долларах, её можно взять как есть, не
    #: спрашивая курс отдельным запросом. К сравнению сумм признак
    #: отношения не имеет — оно всегда ведётся в токенах.
    usd_stable: bool = False
