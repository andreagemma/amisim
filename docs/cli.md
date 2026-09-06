# amisim CLI

The amisim command can be used in explicit subcommand mode or in implicit run mode.

## Command Summary

- amisim run [-s SETTINGS] [-p PARAMS] [-e KEY=VALUE ...] [-O SECTION:NAME=VALUE ...]
- amisim server [-H HOST] [-P PORT] [-D]
- amisim init_db [-u URL] [-S SCHEMA] [-H HOST] [-P PORT] [-U USER] [-W PASSWORD] [-N NAME] [-t TYPE] [-D DRIVER]
- amisim clean_db [-s SETTINGS | -u URL | -t TYPE -H HOST -P PORT -U USER -W PASSWORD -N NAME [-D DRIVER]] [-S SCHEMA] [-w {all,logs,tokens,executions}] [-T TIME] [--include-pending-executions] [--include-active-tokens] [--[no-]checkpoint-truncate] [--[no-]vacuum]

If no subcommand is provided, arguments are interpreted as run arguments.

Main help includes a short command description for:
- run: execute workflow.
- server: reserved server command.
- init_db: initialize internal database.
- clean_db: clean internal database records.

Help aliases:
- `amisim help` shows full CLI help.
- `amisim run help` shows help for the run command.
- `amisim server help` shows help for the server command.
- `amisim init_db help` shows help for the init_db command.
- `amisim clean_db help` shows help for the clean_db command.

## run

Purpose:
- Prepare runtime inputs and execute the simulation workflow.

Arguments:
- -s, --settings: optional path to base software configuration INI file.
- -p, --params: optional path to algorithm execution parameters JSON file.
- -e, --env: repeatable environment override in KEY=VALUE format.
- -O, --option: repeatable settings override in SECTION:NAME=VALUE format.

Default file discovery:
- If --settings is omitted or empty, the CLI checks for settings.ini in the current working directory.
- If --params is omitted or empty, the CLI checks for parmas.json in the current working directory.

Environment override behavior:
- Each -e/--env entry must be in KEY=VALUE format.
- Overrides are applied only during command execution and restored afterwards.

Settings override behavior:
- Each -O/--option entry must be in SECTION:NAME=VALUE format.
- Entries are transformed into a nested dictionary and passed to settings loading.
- CLI options override values loaded from INI and DB settings providers.

Example mapping:
- `-O GENERAL:DEBUG=True -O LOGGING:LOG_LEVEL=INFO`
- becomes `{"GENERAL": {"DEBUG": "True"}, "LOGGING": {"LOG_LEVEL": "INFO"}}`

Examples:

```bash
amisim run
amisim run -s examples/settings.ini
amisim run -s examples/settings.ini -p examples/data/output/1/params.json
amisim run -e AMISIM_LOG_LEVEL=DEBUG -e AMISIM_THREADS=4
amisim run -O GENERAL:DEBUG=True -O LOGGING:LOG_LEVEL=INFO
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
- Create and initialize the internal database used by AMISim.

Arguments:
- -u, --url: SQLAlchemy URL.
- -S, --schema: target schema where tables are created, if supported by the backend.
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

Schema behavior:
- If --schema is provided and the backend supports named schemas, AMISim creates and uses tables in that schema.
- For backends without named schema support (for example SQLite), the schema value is ignored.

Current status:
- The command creates and initializes the internal AMISim database schema.

## clean_db

Purpose:
- Clean internal database tables with target and retention filters.

Arguments:
- -s, --settings: optional settings INI used to resolve `DATABASE.DATABASE_URL`.
- -u, --url: SQLAlchemy URL for the internal DB.
- -S, --schema: target schema where tables are resolved, if supported by the backend.
- -H, --host: database host.
- -P, --port: database port.
- -U, --user: database user.
- -W, --password: database password.
- -N, --name: database name.
- -t, --type: database type (for example postgresql, mysql, sqlite).
- -D, --driver: SQLAlchemy driver suffix.
- -w, --what: cleanup target (`all`, `logs`, `tokens`, `executions`).
- -T, --time: optional retention age (for example `2d`, `12h`, `1w2d`).
- --include-pending-executions: include pending executions in deletion.
- --include-active-tokens: include non-expired tokens in deletion.
- --checkpoint-truncate / --no-checkpoint-truncate: enable/disable SQLite WAL checkpoint in TRUNCATE mode after cleanup (default enabled).
- --vacuum / --no-vacuum: enable/disable SQLite VACUUM after cleanup (default enabled).

Behavior details:
- DB selection precedence is: explicit `--url`, then structured DB options (`--type` and related fields), then `--settings` via `DATABASE.DATABASE_URL`.
- If `--time` is empty, cleanup has no cutoff filter.
- Logs are filtered by `created_at` when `--time` is provided.
- Executions are filtered by `end_time` for non-pending rows.
- Pending executions are excluded by default and included only with `--include-pending-executions`.
- Tokens remove only expired rows by default and remove all tokens when `--include-active-tokens` is set.
- `--checkpoint-truncate` and `--vacuum` are enabled by default as SQLite-oriented maintenance steps to reduce residual `-wal`/`-shm` artifacts and compact storage.

Examples:

```bash
amisim clean_db
amisim clean_db -w logs -T 2d
amisim clean_db -w executions
amisim clean_db -w all --include-pending-executions --include-active-tokens
amisim clean_db -w all --checkpoint-truncate --vacuum
amisim clean_db -w all --no-vacuum
```

## Exit Codes

- 0: command accepted and dispatched.
- 1: command reached a reserved but not implemented behavior.
- 2: invalid user input.
