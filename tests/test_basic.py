from __future__ import annotations

import datetime
from argparse import Namespace
from pathlib import Path
from sqlalchemy import create_engine, text

import pytest
from tictoc import TicToc

from amisim.__main__ import (
    _build_sqlalchemy_url,
    _handle_clean_db,
    _parse_env_overrides,
    _resolve_optional_file,
    parse_cli_args,
)
from amisim.app_logger import _normalize_format
from amisim.application import AmisimApplication
from amisim.utils import nested_dict_from_key_value_list, parse_age_to_timedelta, parse_section_option_overrides
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


def test_parse_cli_clean_db_defaults() -> None:
    args = parse_cli_args(["clean_db"])
    assert args.command == "clean_db"
    assert args.settings == ""
    assert args.url == ""
    assert args.schema == ""
    assert args.what == "all"
    assert args.time == ""
    assert args.include_pending_executions is False
    assert args.include_active_tokens is False
    assert args.checkpoint_truncate is True
    assert args.vacuum is True


def test_parse_cli_clean_db_with_options() -> None:
    args = parse_cli_args(
        [
            "clean_db",
            "--settings",
            "settings.ini",
            "--url",
            "sqlite:///x.db",
            "--what",
            "logs",
            "--time",
            "2d",
            "--include-pending-executions",
            "--include-active-tokens",
            "--checkpoint-truncate",
            "--vacuum",
        ]
    )
    assert args.command == "clean_db"
    assert args.settings == "settings.ini"
    assert args.url == "sqlite:///x.db"
    assert args.what == "logs"
    assert args.time == "2d"
    assert args.include_pending_executions is True
    assert args.include_active_tokens is True
    assert args.checkpoint_truncate is True
    assert args.vacuum is True


def test_parse_cli_clean_db_disable_maintenance_flags() -> None:
    args = parse_cli_args(["clean_db", "--no-checkpoint-truncate", "--no-vacuum"])
    assert args.command == "clean_db"
    assert args.checkpoint_truncate is False
    assert args.vacuum is False


def test_handle_clean_db_uses_explicit_db_url(monkeypatch: pytest.MonkeyPatch) -> None:
    opened: dict[str, object] = {}
    cleaned: dict[str, object] = {}

    class FakeApp:
        def clean_db(self, **kwargs: object) -> dict[str, int]:
            cleaned.update(kwargs)
            return {"logs": 0, "tokens": 0, "executions": 0}

    monkeypatch.setattr(
        "amisim.__main__.DB.open_db", lambda url, schema=None: opened.update({"url": url, "schema": schema})
    )
    monkeypatch.setattr("amisim.__main__.DB.is_initialized", lambda: False)

    args = parse_cli_args(
        ["clean_db", "--url", "sqlite:///tmp.db", "--what", "logs", "--time", "2d", "--checkpoint-truncate"]
    )
    code = _handle_clean_db(args, FakeApp())

    assert code == 0
    assert opened["url"] == "sqlite:///tmp.db"
    assert cleaned["what"] == "logs"
    assert cleaned["time"] == "2d"
    assert cleaned["checkpoint_truncate"] is True
    assert cleaned["vacuum"] is True


def test_handle_clean_db_reads_db_url_from_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    opened: dict[str, object] = {}

    class FakeApp:
        def clean_db(self, **kwargs: object) -> dict[str, int]:
            return {"logs": 0, "tokens": 0, "executions": 0}

    settings = tmp_path / "settings.ini"
    settings.write_text("[DATABASE]\nDATABASE_URL=sqlite:///from_settings.db\n", encoding="utf-8")

    monkeypatch.setattr(
        "amisim.__main__.DB.open_db", lambda url, schema=None: opened.update({"url": url, "schema": schema})
    )
    monkeypatch.setattr("amisim.__main__.DB.is_initialized", lambda: False)

    args = parse_cli_args(["clean_db", "--settings", str(settings)])
    code = _handle_clean_db(args, FakeApp())

    assert code == 0
    assert opened["url"] == "sqlite:///from_settings.db"


def test_handle_clean_db_requires_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeApp:
        def clean_db(self, **kwargs: object) -> dict[str, int]:
            return {"logs": 0, "tokens": 0, "executions": 0}

    monkeypatch.setattr("amisim.__main__.DB.is_initialized", lambda: False)

    args = parse_cli_args(["clean_db", "--settings", "missing.ini"])
    with pytest.raises(ValueError):
        _handle_clean_db(args, FakeApp())


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


def test_parse_age_to_timedelta() -> None:
    assert parse_age_to_timedelta("2d") == datetime.timedelta(days=2)
    assert parse_age_to_timedelta("1d12h") == datetime.timedelta(days=1, hours=12)


def test_parse_age_to_timedelta_rejects_invalid() -> None:
    with pytest.raises(ValueError):
        parse_age_to_timedelta("two_days")


def test_normalize_log_format_legacy_style() -> None:
    legacy = (
        "%(asctime)s | %(levelname)s | %(name)s | %(last_elapsed).2f/%(elapsed).2fs | %(execution_id)s -> %(message)s"
    )
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
    monkeypatch.setattr(
        "amisim.application.get_logger", lambda *args, **kwargs: type("L", (), {"info": lambda *x: None})()
    )
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
    monkeypatch.setattr(
        "amisim.application.get_logger", lambda *args, **kwargs: type("L", (), {"info": lambda *x: None})()
    )

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

    assert app.settings_reader is not None
    assert app.settings_reader.get("DEBUG", section="GENERAL") == "True"
    assert app.ini.GENERAL.DEBUG is True


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

    assert app.settings_reader is not None
    assert app.settings_reader.get("DEBUG", section="GENERAL") == "True"
    assert app.ini.GENERAL.DEBUG is True


def test_application_load_settings_without_ini_builds_typed_defaults() -> None:
    app = AmisimApplication()
    app.load_settings(None)

    assert app.settings_reader is not None
    assert app.ini.GENERAL.DEBUG is False
    assert app.ini.DATABASE.DATABASE_URL == "sqlite:///amisim.db"


def test_application_settings_model_supports_autocomplete_style_access(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.ini"
    settings_file.write_text(
        "\n".join(
            [
                "[GENERAL]",
                "DEBUG=True",
                "",
                "[DATABASE]",
                "DATABASE_URL=sqlite:///custom.db",
                "",
                "[LOGGING]",
                "LOG_LEVEL=INFO",
                "LOG_ON_FILE=False",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    app = AmisimApplication()
    app.load_settings(settings_file)

    assert app.ini.GENERAL.DEBUG is True
    assert app.ini.DATABASE.DATABASE_URL == "sqlite:///custom.db"
    assert app.ini.LOGGING.LOG_LEVEL == "INFO"
    assert app.ini.LOGGING.LOG_ON_FILE is False
    assert app.ini.get("GENERAL", "DEBUG", default=10) is True


def test_application_settings_model_supports_dynamic_sections_and_fields(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.ini"
    settings_file.write_text(
        "\n".join(
            [
                "[GENERAL]",
                "DEBUG=False",
                "",
                "[CUSTOM_SECTION]",
                "CUSTOM_FIELD=custom-value",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    app = AmisimApplication()
    app.load_settings(settings_file)

    assert hasattr(app.ini, "CUSTOM_SECTION")
    assert app.ini.CUSTOM_SECTION.CUSTOM_FIELD == "custom-value"
    assert app.ini.get("CUSTOM_SECTION", "CUSTOM_FIELD", default="") == "custom-value"


def test_application_reuses_shared_logger_for_all_logs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, int] = {"get_logger": 0, "info": 0}

    class FakeLogger:
        def info(self, _message: str) -> None:
            calls["info"] += 1

    def fake_get_logger(*_args, **_kwargs):
        calls["get_logger"] += 1
        return FakeLogger()

    settings_file = tmp_path / "settings.ini"
    settings_file.write_text("[GENERAL]\nDEBUG=False\n", encoding="utf-8")

    monkeypatch.setattr("amisim.application.get_logger", fake_get_logger)
    monkeypatch.setattr("amisim.application.configure_logging", lambda: None)
    monkeypatch.setattr("amisim.application.configure_logging_from_typed_settings", lambda _settings: None)
    monkeypatch.setattr("amisim.application.DB.init_db", lambda _url, schema=None: None)

    app = AmisimApplication()
    app.init_db()
    app.load_settings(settings_file)

    assert calls["get_logger"] == 1
    assert calls["info"] == 2


def test_application_clean_db_default_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeLogger:
        def info(self, *_args: object) -> None:
            return

    def fake_clean_db(**kwargs: object) -> dict[str, int]:
        captured.update(kwargs)
        return {"logs": 1, "tokens": 2, "executions": 3}

    monkeypatch.setattr("amisim.application.get_logger", lambda *args, **kwargs: FakeLogger())
    monkeypatch.setattr("amisim.application.DB.clean_db", fake_clean_db)

    app = AmisimApplication()
    deleted = app.clean_db(what="all")

    assert deleted == {"logs": 1, "tokens": 2, "executions": 3}
    assert captured["what"] == "all"
    assert captured["cutoff"] is None
    assert captured["include_pending_executions"] is False
    assert captured["include_active_tokens"] is False


def test_application_clean_db_time_string_builds_cutoff(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeLogger:
        def info(self, *_args: object) -> None:
            return

    def fake_clean_db(**kwargs: object) -> dict[str, int]:
        captured.update(kwargs)
        return {"logs": 0, "tokens": 0, "executions": 0}

    monkeypatch.setattr("amisim.application.get_logger", lambda *args, **kwargs: FakeLogger())
    monkeypatch.setattr("amisim.application.DB.clean_db", fake_clean_db)

    app = AmisimApplication()
    app.clean_db(
        time="2d",
        what="executions",
        include_pending_executions=True,
        include_active_tokens=True,
        checkpoint_truncate=True,
        vacuum=True,
    )

    assert captured["what"] == "executions"
    assert isinstance(captured["cutoff"], datetime.datetime)
    assert captured["include_pending_executions"] is True
    assert captured["include_active_tokens"] is True
    assert captured["checkpoint_truncate"] is True
    assert captured["vacuum"] is True
