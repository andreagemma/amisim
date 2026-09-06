from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from sqlalchemy import create_engine, text

import pytest
from tictoc import TicToc

from amisim.__main__ import _build_sqlalchemy_url, _parse_env_overrides, _resolve_optional_file, parse_cli_args
from amisim.app_logger import _normalize_format
from amisim.application import AmisimApplication
from amisim.utils import nested_dict_from_key_value_list, parse_section_option_overrides
from amisim import get_logger


def test_parse_cli_defaults_to_run() -> None:
    args = parse_cli_args([])
    assert args.command == "run"
    assert args.settings == ""
    assert args.params == ""
    assert args.env == []


def test_parse_cli_run_with_options() -> None:
    args = parse_cli_args(
        ["run", "-s", "custom.ini", "-p", "custom.json", "-e", "A=1", "-e", "B=2", "-O", "GENERAL:DEBUG=True"]
    )
    assert args.command == "run"
    assert args.settings == "custom.ini"
    assert args.params == "custom.json"
    assert args.env == ["A=1", "B=2"]
    assert args.option == ["GENERAL:DEBUG=True"]


def test_parse_cli_server() -> None:
    args = parse_cli_args(["server", "-H", "0.0.0.0", "-P", "9000", "-D"])
    assert args.command == "server"
    assert args.host == "0.0.0.0"
    assert args.port == 9000
    assert args.debug is True


def test_parse_cli_init_db_with_schema() -> None:
    args = parse_cli_args(["init_db", "--schema", "sim", "-t", "postgresql", "-N", "amisim"])
    assert args.command == "init_db"
    assert args.schema == "sim"
    assert args.type == "postgresql"
    assert args.name == "amisim"


def test_parse_cli_root_help_alias(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        parse_cli_args(["help"])

    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "run" in out
    assert "server" in out
    assert "init_db" in out


def test_parse_cli_subcommand_help_alias(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        parse_cli_args(["run", "help"])

    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "--settings" in out
    assert "--params" in out
    assert "--env" in out


def test_resolve_optional_file_uses_default_if_exists(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    default_file = tmp_path / "settings.ini"
    default_file.write_text("[main]\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    resolved = _resolve_optional_file("", "settings.ini")
    assert resolved == default_file


def test_resolve_optional_file_returns_none_if_missing(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    resolved = _resolve_optional_file("", "settings.ini")
    assert resolved is None


def test_parse_env_overrides() -> None:
    parsed = _parse_env_overrides(["A=1", "B=2=3"])
    assert parsed == {"A": "1", "B": "2=3"}


def test_parse_env_overrides_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        _parse_env_overrides(["INVALID"])


def test_parse_section_option_overrides() -> None:
    parsed = parse_section_option_overrides(["GENERAL:DEBUG=True", "DATABASE:URL=sqlite:///a.db"])
    assert parsed == {"GENERAL": {"DEBUG": "True"}, "DATABASE": {"URL": "sqlite:///a.db"}}


def test_parse_section_option_overrides_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        parse_section_option_overrides(["GENERAL_DEBUG=True"])


def test_nested_dict_from_key_value_list() -> None:
    nested = nested_dict_from_key_value_list(
        {
            "a": "1",
            "b:c": "2",
            "b:d": "3",
            "e:f:g": "4",
        }
    )
    assert nested == {"a": "1", "b": {"c": "2", "d": "3"}, "e": {"f": {"g": "4"}}}


def test_normalize_log_format_legacy_style() -> None:
    legacy = "%(asctime)s | %(levelname)s | %(name)s | %(last_elapsed).2f/%(elapsed).2fs | %(execution_id)s -> %(message)s"
    normalized = _normalize_format(legacy)
    assert "{time:" in normalized
    assert "{level:" in normalized
    assert "{name}" in normalized
    assert "{extra[last_elapsed]:.2f}" in normalized
    assert "{extra[elapsed]:.2f}" in normalized
    assert "{extra[execution_id]}" in normalized
    assert "{message}" in normalized


def test_get_logger_returns_tictoc_based_logger() -> None:
    log = get_logger(section="assignment", execution_id=42)
    assert isinstance(log, TicToc)
    assert log.extra.get("execution_id") == 42


def test_build_sqlalchemy_url_from_parts() -> None:
    args = Namespace(
        type="postgresql",
        driver="psycopg",
        user="alice",
        password="secret",
        host="db.local",
        port=5432,
        name="traffic",
    )

    url = _build_sqlalchemy_url(args)
    assert url == "postgresql+psycopg://alice:secret@db.local:5432/traffic"


def test_application_init_db_defaults_to_local_sqlite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str | None] = {}

    def fake_init_db(database_url: str, schema: str | None = None) -> None:
        captured["url"] = database_url
        captured["schema"] = schema

    monkeypatch.setattr("amisim.application.DB.init_db", fake_init_db)
    monkeypatch.setattr("amisim.application.configure_logging", lambda: None)
    monkeypatch.setattr("amisim.application.get_logger", lambda: type("L", (), {"info": lambda *args: None})())
    monkeypatch.chdir(tmp_path)

    app = AmisimApplication()
    app.init_db()

    expected = f"sqlite+pysqlite:///{(tmp_path / 'amisim.db').as_posix()}"
    assert captured["url"] == expected
    assert captured["schema"] is None


def test_application_init_db_from_structured_options(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str | None] = {}

    def fake_init_db(database_url: str, schema: str | None = None) -> None:
        captured["url"] = database_url
        captured["schema"] = schema

    monkeypatch.setattr("amisim.application.DB.init_db", fake_init_db)
    monkeypatch.setattr("amisim.application.configure_logging", lambda: None)
    monkeypatch.setattr("amisim.application.get_logger", lambda: type("L", (), {"info": lambda *args: None})())

    app = AmisimApplication()
    app.init_db(
        db_type="postgresql",
        driver="psycopg",
        user="alice",
        password="secret",
        host="db",
        port=5432,
        name="amisim",
        schema="sim",
    )

    assert captured["url"] == "postgresql+psycopg://alice:secret@db:5432/amisim"
    assert captured["schema"] == "sim"


def test_application_init_db_requires_name_for_non_sqlite() -> None:
    app = AmisimApplication()
    with pytest.raises(ValueError):
        app.init_db(db_type="postgresql")


def test_application_load_settings_with_overrides(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.ini"
    settings_file.write_text("[GENERAL]\nDEBUG=False\n", encoding="utf-8")

    app = AmisimApplication()
    app.load_settings(settings_file, overrides={"GENERAL": {"DEBUG": "True"}})

    assert app.settings is not None
    assert app.settings.get("DEBUG", section="GENERAL") == "True"


def test_application_load_settings_with_database_settings(tmp_path: Path) -> None:
    db_path = tmp_path / "settings.db"
    db_url = f"sqlite:///{db_path.as_posix()}"
    settings_file = tmp_path / "settings.ini"
    settings_file.write_text(
        "\n".join(
            [
                "[GENERAL]",
                "DEBUG=False",
                "",
                "[DATABASE_SETTINGS]",
                "DB_SETTINGS_USE=True",
                f"DB_SETTINGS_URL={db_url}",
                "DB_SETTINGS_TABLE_NAME=settings",
                "DB_SETTINGS_QUERY=SELECT value FROM settings WHERE name = :name and section = :section",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE settings (section TEXT, name TEXT, value TEXT)"))
        conn.execute(text("INSERT INTO settings (section, name, value) VALUES ('GENERAL', 'DEBUG', 'True')"))

    app = AmisimApplication()
    app.load_settings(settings_file)

    assert app.settings is not None
    assert app.settings.get("DEBUG", section="GENERAL") == "True"
