"""Console entrypoint for amisim."""

from __future__ import annotations

import argparse
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable

from .application import AmisimApplication


def _build_parser() -> argparse.ArgumentParser:
    """Build the root CLI parser with explicit subcommands.

    :return: Configured parser for run, server, and init_db commands.
    """
    parser = argparse.ArgumentParser(prog="amisim")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run")
    _add_run_arguments(run_parser)

    server_parser = subparsers.add_parser("server")
    server_parser.add_argument("-P", "--port", type=int, default=0, help="Port to run the server on")
    server_parser.add_argument("-H", "--host", default="127.0.0.1", help="Host to run the server on")
    server_parser.add_argument("-D", "--debug", action="store_true", help="Enable debug mode for the server")

    init_db_parser = subparsers.add_parser("init_db")
    init_db_parser.add_argument("-u", "--url", default="", help="Database connection URL")
    init_db_parser.add_argument("-H", "--host", default="", help="Database host")
    init_db_parser.add_argument("-P", "--port", type=int, help="Database port")
    init_db_parser.add_argument("-U", "--user", default="", help="Database user")
    init_db_parser.add_argument("-W", "--password", default="", help="Database password")
    init_db_parser.add_argument("-N", "--name", default="", help="Database name")
    init_db_parser.add_argument("-t", "--type", default="", help="Database type (e.g., postgresql, mysql)")
    init_db_parser.add_argument("-D", "--driver", default="", help="Database driver (e.g., psycopg)")

    return parser


def _build_default_run_parser() -> argparse.ArgumentParser:
    """Build a parser for implicit run mode.

    :return: Parser accepting run arguments without a subcommand token.
    """
    parser = argparse.ArgumentParser(prog="amisim")
    _add_run_arguments(parser)
    return parser


def _add_run_arguments(parser: argparse.ArgumentParser) -> None:
    """Register run-mode arguments on a parser.

    :param parser: Parser to extend with run options.
    """
    parser.add_argument("-s", "--settings", default="", help="Path to the settings INI file")
    parser.add_argument("-p", "--params", default="", help="Path to the parameters JSON file with scenario parameters")
    parser.add_argument(
        "-e", "--env", action="append", default=[], help="Environment variable overrides in the form KEY=VALUE"
    )


def parse_cli_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    If no explicit subcommand is provided, arguments are interpreted as
    run-mode options and command is forced to ``run``.

    :param argv: Optional argument vector excluding executable name.
    :return: Parsed namespace including resolved command name.
    """
    args_list = list(argv if argv is not None else sys.argv[1:])

    # If an explicit subcommand is provided, parse the full subcommand tree.
    if args_list and args_list[0] in {"run", "server", "init_db"}:
        parser = _build_parser()
        return parser.parse_args(args_list)

    # No subcommand means backward-compatible "run" mode with run arguments.
    parser = _build_default_run_parser()
    namespace = parser.parse_args(args_list)
    namespace.command = "run"
    return namespace


def _resolve_optional_file(raw_value: str, default_filename: str) -> Path | None:
    """Resolve an optional file argument with cwd fallback.

    :param raw_value: Raw user-provided value.
    :param default_filename: Default filename to check in current directory.
    :return: Explicit or discovered path, otherwise ``None``.
    """
    value = raw_value.strip()
    if value:
        return Path(value)

    # Use the default filename only when it exists in the current working directory.
    default_path = Path.cwd() / default_filename
    if default_path.exists():
        return default_path

    return None


def _parse_env_overrides(values: Iterable[str]) -> dict[str, str]:
    """Parse repeatable KEY=VALUE environment overrides.

    :param values: Iterable of raw override entries.
    :return: Mapping of environment variables to temporary values.
    :raises ValueError: If an entry is not in KEY=VALUE format.
    """
    overrides: dict[str, str] = {}
    for item in values:
        if "=" not in item:
            raise ValueError(f"Invalid -e/--env value: {item!r}. Expected KEY=VALUE")
        key, val = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Invalid -e/--env value: {item!r}. Empty key")
        overrides[key] = val
    return overrides


@contextmanager
def _temporary_env(overrides: dict[str, str]):
    """Temporarily apply environment overrides within a context.

    :param overrides: Environment values to set for the context duration.
    :return: A context manager restoring previous values on exit.
    """
    if not overrides:
        yield
        return

    # Apply temporary overrides for the command lifecycle and restore afterwards.
    previous: dict[str, str | None] = {k: os.environ.get(k) for k in overrides}
    os.environ.update(overrides)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _build_sqlalchemy_url(args: argparse.Namespace) -> str:
    """Build a SQLAlchemy URL from structured CLI options.

    :param args: Parsed init_db namespace.
    :return: SQLAlchemy URL or an empty string when db type is missing.
    """
    # Build URL only when enough structured components are provided.
    db_type = args.type.strip()
    if not db_type:
        return ""

    driver = args.driver.strip()
    dialect = f"{db_type}+{driver}" if driver else db_type

    user = args.user.strip()
    password = args.password.strip()
    auth = ""
    if user:
        auth = user
        if password:
            auth = f"{auth}:{password}"
        auth = f"{auth}@"

    host = args.host.strip()
    port = f":{args.port}" if args.port is not None else ""
    db_name = args.name.strip()

    return f"{dialect}://{auth}{host}{port}/{db_name}"


def _handle_run(args: argparse.Namespace, app: AmisimApplication) -> int:
    """Execute run-mode orchestration.

    :param args: Parsed run namespace.
    :param app: Application facade used for library-level calls.
    :return: Process exit code.
    :raises ValueError: If environment override syntax is invalid.
    :raises NotImplementedError: If underlying app methods are still stubs.
    """
    # Follow requested defaults: settings.ini and parmas.json if present.
    settings_path = _resolve_optional_file(args.settings, "settings.ini")
    params_path = _resolve_optional_file(args.params, "parmas.json")
    env_overrides = _parse_env_overrides(args.env)

    with _temporary_env(env_overrides):
        if settings_path is not None:
            app.load_settings(settings_path)
        if params_path is not None:
            app.load_params(params_path)
        app.run()

    return 0


def _handle_server(_: argparse.Namespace) -> int:
    """Execute server-mode orchestration.

    :raises NotImplementedError: Always, until server behavior is implemented.
    """
    raise NotImplementedError("server command is not implemented yet")


def _handle_init_db(args: argparse.Namespace, app: AmisimApplication) -> int:
    """Execute init_db-mode orchestration.

    :param args: Parsed init_db namespace.
    :param app: Application facade used for library-level calls.
    :return: Process exit code.
    :raises NotImplementedError: If underlying app method is still a stub.
    """
    url = args.url.strip() or _build_sqlalchemy_url(args)
    app.init_db(
        url=url or None,
        host=args.host.strip() or None,
        port=args.port,
        user=args.user.strip() or None,
        password=args.password.strip() or None,
        name=args.name.strip() or None,
        db_type=args.type.strip() or None,
        driver=args.driver.strip() or None,
    )
    return 0


def main(argv: list[str] | None = None, app: AmisimApplication | None = None) -> int:
    """Run the CLI entrypoint.

    :param argv: Optional argument vector excluding executable name.
    :param app: Optional application instance for dependency injection.
    :return: Exit code according to command outcome.
    """
    args = parse_cli_args(argv)
    application = app if app is not None else AmisimApplication()

    try:
        # Dispatch by subcommand while keeping library methods injectable for tests.
        if args.command == "run":
            return _handle_run(args, application)
        if args.command == "server":
            return _handle_server(args)
        if args.command == "init_db":
            return _handle_init_db(args, application)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except NotImplementedError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"Unknown command: {args.command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
