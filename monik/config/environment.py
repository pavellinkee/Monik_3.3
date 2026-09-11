"""Загрузка файла окружения с секретами.

Секреты в репозиторий не попадают никогда (``22_SECURITY.md``,
``CLAUDE.md`` §49), поэтому файл с ними живёт вне проекта и переносится
отдельно. Из этого следует практическая задача: копия Monik на другом
сервере — или новое состояние на этом же — должна найти секреты сама, без
правки кода и без ручного экспорта переменных.

Поиск ведётся по фиксированному порядку, от частного к общему:

1. путь, заданный явно (аргумент ``--env-file``);
2. путь из переменной ``MONIK_ENV_FILE``;
3. общесистемный файл службы ``/etc/monik/monik.env``;
4. пользовательский ``~/.config/monik/monik.env``;
5. файл ``.env`` рядом с конфигурацией.

Общесистемный файл принадлежит root и обычно недоступен приложению,
запущенному от имени оператора: его читает systemd через
``EnvironmentFile`` и передаёт службе уже готовым окружением. Поэтому в
порядке есть и пользовательское расположение — оно работает для ручного
запуска и для копии на другом сервере, где службы ещё нет.

Берётся первый существующий; остальные не читаются. Уже заданные
переменные окружения **не перезаписываются**: то, что оператор передал
явно, важнее файла, и systemd со своим ``EnvironmentFile`` продолжает
работать как прежде.

Значения не логируются и не возвращаются наружу: модуль сообщает только
путь и число загруженных имён.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

__all__ = ["SEARCH_PATHS", "EnvFileResult", "load_env_file"]

#: Общесистемный файл секретов службы.
SYSTEM_ENV_FILE = Path("/etc/monik/monik.env")

#: Переменная, которой путь задаётся явно.
ENV_FILE_VARIABLE = "MONIK_ENV_FILE"

#: Пользовательский файл секретов: доступен без root.
USER_ENV_FILE = Path.home() / ".config" / "monik" / "monik.env"

#: Порядок поиска по умолчанию, от частного к общему.
SEARCH_PATHS: tuple[Path, ...] = (SYSTEM_ENV_FILE, USER_ENV_FILE, Path(".env"))


@dataclass(frozen=True, slots=True)
class EnvFileResult:
    """Итог загрузки: что нашли и сколько имён добавили."""

    path: Path | None = None
    loaded: int = 0
    skipped: int = 0

    @property
    def found(self) -> bool:
        """Найден ли файл окружения."""
        return self.path is not None


def load_env_file(
    explicit: str | os.PathLike[str] | None = None,
    *,
    environ: dict[str, str] | None = None,
    search_paths: tuple[Path, ...] = SEARCH_PATHS,
) -> EnvFileResult:
    """Загрузить первый найденный файл окружения.

    Возвращает путь и число добавленных имён. Если файл не найден,
    результат пуст: отсутствие файла ошибкой не является — переменные
    могли быть заданы окружением напрямую.
    """
    target = environ if environ is not None else os.environ
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(Path(explicit))
    from_variable = target.get(ENV_FILE_VARIABLE)
    if from_variable:
        candidates.append(Path(from_variable))
    candidates.extend(search_paths)

    for candidate in candidates:
        try:
            if not candidate.is_file():
                continue
            content = candidate.read_text(encoding="utf-8")
        except OSError:
            # Файл может быть недоступен по правам: это не повод падать,
            # переменные могли прийти из окружения службы.
            continue
        loaded, skipped = _apply(content, target)
        return EnvFileResult(path=candidate, loaded=loaded, skipped=skipped)
    return EnvFileResult()


def _apply(content: str, target: dict[str, str] | os._Environ[str]) -> tuple[int, int]:
    """Перенести значения в окружение, не затирая уже заданные."""
    loaded = 0
    skipped = 0
    for raw in content.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        name, separator, value = line.partition("=")
        if not separator:
            continue
        name = name.strip()
        if not name:
            continue
        if name in target:
            skipped += 1
            continue
        target[name] = _unquote(value.strip())
        loaded += 1
    return loaded, skipped


def _unquote(value: str) -> str:
    """Снять обрамляющие кавычки, если они есть."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value
