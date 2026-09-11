"""Курс native token, выведенный из стоимости газа в долларах."""

from __future__ import annotations

from decimal import Decimal

from monik.domain.enums.fees import FeeStatus
from monik.domain.models.gas import Gas, GasPrice
from monik.services.prices.quoted import SOURCE, gas_rate_from_quotes
from tests import factories as f


def _gas(cost_native: str | None = "0.01") -> Gas:
    if cost_native is None:
        return Gas(
            network_id=f.POLYGON,
            status=FeeStatus.UNKNOWN,
            observed_at=f.NOW,
            source="test",
        )
    return Gas(
        network_id=f.POLYGON,
        status=FeeStatus.KNOWN,
        gas_units=200_000,
        gas_price=GasPrice(
            network_id=f.POLYGON,
            wei_per_gas=50_000_000_000,
            source="test",
            observed_at=f.NOW,
        ),
        native_token=f.WMATIC.key,
        cost_native=Decimal(cost_native),
        observed_at=f.NOW,
        source="test",
    )


def _quote(cost_usd: str | None) -> object:
    quote = f.quote()
    return quote.model_copy(
        update={"estimated_gas_cost_usd": Decimal(cost_usd) if cost_usd else None}
    )


class TestDerivedRate:
    def test_rate_is_dollars_per_native_unit(self) -> None:
        """0.005 доллара за 0.01 POL — значит POL стоит 0.5 доллара."""
        rate = gas_rate_from_quotes(
            _gas("0.01"), (_quote("0.005"),), target=f.USDT_STABLE, now=f.NOW
        )

        assert rate is not None
        assert rate.rate == Decimal("0.5")
        assert rate.source == SOURCE
        assert rate.to_token == f.USDT_STABLE.key

    def test_any_leg_may_report_the_cost(self) -> None:
        """Стоимость относится к сети, а не к провайдеру."""
        rate = gas_rate_from_quotes(
            _gas("0.01"), (_quote(None), _quote("0.005")), target=f.USDT_STABLE, now=f.NOW
        )
        assert rate is not None


class TestRefusals:
    """Приблизительное значение вместо точного не подставляется."""

    def test_target_must_be_declared_usd_stable(self) -> None:
        """Признак объявляет оператор; по символу код не угадывает."""
        assert gas_rate_from_quotes(_gas(), (_quote("0.005"),), target=f.AAVE, now=f.NOW) is None

    def test_unknown_native_cost_gives_no_rate(self) -> None:
        assert (
            gas_rate_from_quotes(_gas(None), (_quote("0.005"),), target=f.USDT_STABLE, now=f.NOW)
            is None
        )

    def test_no_reported_dollars_gives_no_rate(self) -> None:
        assert (
            gas_rate_from_quotes(_gas("0.01"), (_quote(None),), target=f.USDT_STABLE, now=f.NOW)
            is None
        )

    def test_zero_values_give_no_rate(self) -> None:
        assert (
            gas_rate_from_quotes(_gas("0"), (_quote("0.005"),), target=f.USDT_STABLE, now=f.NOW)
            is None
        )
        assert (
            gas_rate_from_quotes(_gas("0.01"), (_quote("0"),), target=f.USDT_STABLE, now=f.NOW)
            is None
        )
