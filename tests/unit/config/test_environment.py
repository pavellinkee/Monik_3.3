"""Поиск и загрузка файла с секретами."""

from __future__ import annotations

import pathlib

from monik.config.environment import load_env_file

CONTENT = """
# комментарий
MONIK_ZEROX_API_KEY=abc123
export MONIK_VELORA_API_KEY="partner"
MONIK_TELEGRAM_CHAT_ID='12345'
BROKEN_LINE
"""


def _file(tmp_path: pathlib.Path, content: str = CONTENT) -> pathlib.Path:
    path = tmp_path / "monik.env"
    path.write_text(content, encoding="utf-8")
    return path


class TestLoading:
    def test_values_reach_the_environment(self, tmp_path: pathlib.Path) -> None:
        environ: dict[str, str] = {}
        result = load_env_file(_file(tmp_path), environ=environ, search_paths=())

        assert result.found
        assert environ["MONIK_ZEROX_API_KEY"] == "abc123"
        assert environ["MONIK_VELORA_API_KEY"] == "partner"
        assert environ["MONIK_TELEGRAM_CHAT_ID"] == "12345"

    def test_comments_and_malformed_lines_are_ignored(self, tmp_path: pathlib.Path) -> None:
        environ: dict[str, str] = {}
        load_env_file(_file(tmp_path), environ=environ, search_paths=())

        assert "BROKEN_LINE" not in environ
        assert len(environ) == 3

    def test_existing_variables_win(self, tmp_path: pathlib.Path) -> None:
        """То, что оператор передал явно, важнее файла."""
        environ = {"MONIK_ZEROX_API_KEY": "from-environment"}
        result = load_env_file(_file(tmp_path), environ=environ, search_paths=())

        assert environ["MONIK_ZEROX_API_KEY"] == "from-environment"
        assert result.skipped == 1


class TestSearchOrder:
    def test_explicit_path_wins(self, tmp_path: pathlib.Path) -> None:
        explicit = _file(tmp_path, "NAME=explicit\n")
        fallback = tmp_path / "fallback.env"
        fallback.write_text("NAME=fallback\n", encoding="utf-8")

        environ: dict[str, str] = {}
        load_env_file(explicit, environ=environ, search_paths=(fallback,))
        assert environ["NAME"] == "explicit"

    def test_variable_is_used_when_no_explicit_path(self, tmp_path: pathlib.Path) -> None:
        chosen = _file(tmp_path, "NAME=from-variable\n")
        environ = {"MONIK_ENV_FILE": str(chosen)}
        load_env_file(None, environ=environ, search_paths=())
        assert environ["NAME"] == "from-variable"

    def test_search_path_is_the_last_resort(self, tmp_path: pathlib.Path) -> None:
        fallback = _file(tmp_path, "NAME=from-search\n")
        environ: dict[str, str] = {}
        load_env_file(None, environ=environ, search_paths=(fallback,))
        assert environ["NAME"] == "from-search"

    def test_missing_file_is_not_an_error(self, tmp_path: pathlib.Path) -> None:
        """Переменные могли быть заданы окружением службы напрямую."""
        environ: dict[str, str] = {}
        result = load_env_file(None, environ=environ, search_paths=(tmp_path / "absent.env",))

        assert not result.found
        assert result.loaded == 0
        assert environ == {}

    def test_unreadable_file_is_skipped(self, tmp_path: pathlib.Path) -> None:
        """Недоступный по правам файл не роняет запуск."""
        protected = _file(tmp_path, "NAME=secret\n")
        protected.chmod(0o000)
        readable = tmp_path / "readable.env"
        readable.write_text("NAME=readable\n", encoding="utf-8")

        environ: dict[str, str] = {}
        try:
            load_env_file(None, environ=environ, search_paths=(protected, readable))
        finally:
            protected.chmod(0o600)
        assert environ.get("NAME") in {"readable", "secret"}
