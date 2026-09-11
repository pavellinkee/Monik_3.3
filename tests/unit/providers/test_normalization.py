"""Перевод отказов доменной модели в ошибки данных провайдера."""

from __future__ import annotations

import pytest

from monik.domain.enums.providers import ProviderId
from monik.domain.errors import DataError
from monik.domain.models.route import RouteStep
from monik.infrastructure.providers.normalization import normalized_response
from tests import factories as f


class TestNormalizedResponse:
    def test_model_failure_becomes_a_data_error(self) -> None:
        """Ошибка библиотеки не должна выходить за границу адаптера."""
        with pytest.raises(DataError) as raised:
            with normalized_response(ProviderId.UNISWAP):
                RouteStep(
                    input_token=f.USDT.key,
                    output_token=f.AAVE.key,
                    protocol="x" * 2048,
                )

        info = raised.value.info
        assert info.code == "provider_response_invalid"
        assert info.provider_code == ProviderId.UNISWAP.value

    def test_message_names_the_field(self) -> None:
        """Диагностика должна указывать, что именно не подошло."""
        with pytest.raises(DataError) as raised:
            with normalized_response(ProviderId.ZERO_X):
                RouteStep(input_token=f.USDT.key, output_token=f.AAVE.key, protocol="")

        assert "protocol" in raised.value.info.message

    def test_message_stays_bounded(self) -> None:
        """Сообщение не растёт вместе с ответом провайдера."""
        with pytest.raises(DataError) as raised:
            with normalized_response(ProviderId.VELORA):
                RouteStep(input_token=f.USDT.key, output_token=f.AAVE.key, protocol="y" * 4096)

        assert len(raised.value.info.message) <= 256

    def test_monik_errors_pass_through_unchanged(self) -> None:
        """Собственные ошибки Monik не переоборачиваются."""
        original = DataError("already normalized", code="provider_amount_invalid")
        with pytest.raises(DataError) as raised:
            with normalized_response(ProviderId.UNISWAP):
                raise original

        assert raised.value is original

    def test_success_is_not_touched(self) -> None:
        with normalized_response(ProviderId.UNISWAP):
            step = RouteStep(input_token=f.USDT.key, output_token=f.AAVE.key, protocol="v3")
        assert step.protocol == "v3"
