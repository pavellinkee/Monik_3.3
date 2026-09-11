"""Smoke-тесты фундамента проекта (этап S0)."""

from __future__ import annotations

import importlib
import pathlib
import pkgutil
import re
import tomllib

import pytest

import monik

EXPECTED_PACKAGES = [
    "monik.app",
    "monik.config",
    "monik.domain",
    "monik.domain.models",
    "monik.domain.enums",
    "monik.domain.value_objects",
    "monik.domain.errors",
    "monik.services",
    "monik.services.level1",
    "monik.services.level2",
    "monik.services.opportunity",
    "monik.services.calculator",
    "monik.services.fees",
    "monik.services.gas",
    "monik.services.prices",
    "monik.services.resources",
    "monik.services.scheduler",
    "monik.services.notifications",
    "monik.services.registries",
    "monik.services.health",
    "monik.services.observability",
    "monik.repositories",
    "monik.repositories.interfaces",
    "monik.repositories.sqlite",
    "monik.infrastructure",
    "monik.infrastructure.http",
    "monik.infrastructure.db",
    "monik.infrastructure.telegram",
    "monik.infrastructure.providers",
    "monik.infrastructure.providers.oneinch",
    "monik.infrastructure.providers.zero_x",
    "monik.infrastructure.providers.velora",
    "monik.infrastructure.providers.uniswap",
]


def test_version_is_exposed() -> None:
    """Версия объявлена и выглядит как версия."""
    assert re.fullmatch(r"\d+\.\d+\.\d+", monik.__version__), monik.__version__


def test_version_label_names_the_application() -> None:
    assert monik.version_label() == f"{monik.APPLICATION_NAME} {monik.__version__}"


def test_pyproject_version_matches_the_package() -> None:
    """Единственный источник истины версии (``CLAUDE.md`` §18).

    Дублировать номер версии в тесте нельзя: тогда он сам стал бы вторым
    источником. Проверяется совпадение объявленных значений.
    """
    pyproject = pathlib.Path(__file__).resolve().parents[2] / "pyproject.toml"
    declared = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]
    assert declared == monik.__version__


@pytest.mark.parametrize("module_name", EXPECTED_PACKAGES)
def test_architecture_package_exists(module_name: str) -> None:
    """Каждый архитектурный слой представлен импортируемым пакетом."""
    module = importlib.import_module(module_name)
    assert module.__doc__, f"{module_name} должен иметь docstring с описанием ответственности"


def test_every_package_is_importable() -> None:
    """Ни один модуль пакета не должен падать при импорте."""
    failures: list[str] = []
    for module_info in pkgutil.walk_packages(monik.__path__, prefix="monik."):
        try:
            importlib.import_module(module_info.name)
        except Exception as exc:  # noqa: BLE001 - собираем все ошибки разом
            failures.append(f"{module_info.name}: {exc!r}")
    assert not failures, failures


def test_package_is_typed() -> None:
    """Пакет помечен как типизированный (py.typed)."""
    marker = next(iter(monik.__path__)) + "/py.typed"
    with open(marker):
        pass


def test_version_follows_the_state_directory() -> None:
    """Копия, названная новым номером, сообщает новый номер.

    Состояния Monik живут отдельными каталогами, и приложение обязано
    представляться версией того состояния, из которого запущено
    (``24_DEPLOYMENT.md`` §6).
    """
    assert monik._version_from_directory("monik_3.3") == "3.3.0"
    assert monik._version_from_directory("Monik_3.4") == "3.4.0"
    assert monik._version_from_directory("monik-4.0") == "4.0.0"
    assert monik._version_from_directory("Monik 3.4.1") == "3.4.1"
    assert monik._version_from_directory("monik_3.10") == "3.10.0"


def test_unnamed_directory_falls_back_to_the_declared_version() -> None:
    """Каталог без номера не должен давать выдуманную версию."""
    assert monik._version_from_directory("src") is None
    assert monik._version_from_directory("claude_monik") is None
    assert monik._version_from_directory("monik") is None


def test_reported_version_is_resolved_not_hardcoded() -> None:
    assert monik.APPLICATION_VERSION == monik.resolve_version()
    assert monik.version_label() == f"{monik.APPLICATION_NAME} {monik.APPLICATION_VERSION}"
