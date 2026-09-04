from __future__ import annotations

from argparse import Namespace

import pytest

from amisim.__main__ import _build_sqlalchemy_url, _parse_env_overrides, _resolve_optional_file, parse_cli_args


def test_parse_cli_defaults_to_run() -> None:
    args = parse_cli_args([])
    assert args.command == "run"
    assert args.settings == ""
    assert args.params == ""
    assert args.env == []


def test_parse_cli_run_with_options() -> None:
    args = parse_cli_args(["run", "-s", "custom.ini", "-p", "custom.json", "-e", "A=1", "-e", "B=2"])
    assert args.command == "run"
    assert args.settings == "custom.ini"
    assert args.params == "custom.json"
    assert args.env == ["A=1", "B=2"]


def test_parse_cli_server() -> None:
    args = parse_cli_args(["server", "-H", "0.0.0.0", "-P", "9000", "-D"])
    assert args.command == "server"
    assert args.host == "0.0.0.0"
    assert args.port == 9000
    assert args.debug is True


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
