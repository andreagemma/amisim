# amisim CLI

The amisim command can be used in explicit subcommand mode or in implicit run mode.

## Command Summary

- amisim run [-s SETTINGS] [-p PARAMS] [-e KEY=VALUE ...]
- amisim server [-H HOST] [-P PORT] [-D]
- amisim init_db [-u URL] [-H HOST] [-P PORT] [-U USER] [-W PASSWORD] [-N NAME] [-t TYPE] [-D DRIVER]

If no subcommand is provided, arguments are interpreted as run arguments.

## run

Purpose:
- Prepare runtime inputs and execute the simulation workflow.

Arguments:
- -s, --settings: optional path to settings INI file.
- -p, --params: optional path to params JSON file.
- -e, --env: repeatable environment override in KEY=VALUE format.

Default file discovery:
- If --settings is omitted or empty, the CLI checks for settings.ini in the current working directory.
- If --params is omitted or empty, the CLI checks for parmas.json in the current working directory.

Environment override behavior:
- Each -e/--env entry must be in KEY=VALUE format.
- Overrides are applied only during command execution and restored afterwards.

Examples:

```bash
amisim run
amisim run -s examples/settings.ini
amisim run -s examples/settings.ini -p examples/data/output/1/params.json
amisim run -e AMISIM_LOG_LEVEL=DEBUG -e AMISIM_THREADS=4
```

## server

Purpose:
- Reserve CLI contract for future server mode.

Arguments:
- -H, --host: host address (default 127.0.0.1).
- -P, --port: server port (default 0).
- -D, --debug: debug flag.

Current status:
- The command interface is available, but runtime behavior is not implemented yet.

## init_db

Purpose:
- Reserve CLI contract for database initialization.

Arguments:
- -u, --url: SQLAlchemy URL.
- -H, --host: database host.
- -P, --port: database port.
- -U, --user: database user.
- -W, --password: database password.
- -N, --name: database name.
- -t, --type: database type (for example postgresql, mysql, sqlite).
- -D, --driver: SQLAlchemy driver suffix.

URL construction behavior:
- If --url is provided and non-empty, that URL is used.
- Otherwise, a URL is built from --type/--driver and optional auth/host/port/name fields.

Current status:
- The command interface is available, but runtime behavior is not implemented yet.

## Exit Codes

- 0: command accepted and dispatched.
- 1: command reached a reserved but not implemented behavior.
- 2: invalid user input.
