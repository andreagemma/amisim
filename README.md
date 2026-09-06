# amisim
Meso-scopic Traffic Assignment Model

## CLI

The console command is `amisim` and supports these command modes:

- `amisim run [-s SETTINGS] [-p PARAMS] [-e KEY=VALUE ...] [-O SECTION:NAME=VALUE ...]`
- `amisim server [-H HOST] [-P PORT] [-D]`
- `amisim init_db [-u URL] [-S SCHEMA] [-H HOST] [-P PORT] [-U USER] [-W PASSWORD] [-N NAME] [-t TYPE] [-D DRIVER]`

Help aliases:

- `amisim help` prints full CLI help.
- `amisim run help` prints help for the `run` command (same pattern for `server` and `init_db`).

Behavior notes:

- If no command is provided, arguments are parsed as `run`.
- In `run`, `-s/--settings` points to the base software configuration; when empty and `settings.ini` exists in the current working directory, that file is used.
- In `run`, `-p/--params` points to algorithm execution parameters; when empty and `parmas.json` exists in the current working directory, that file is used.
- In `run`, `-e/--env` can be passed multiple times as `KEY=VALUE` to override environment variables for the execution scope.
- In `run`, `-O/--option` can be passed multiple times as `SECTION:NAME=VALUE` to override settings values at runtime.

Detailed CLI documentation is available in `docs/cli.md`.

## Library Usage

The package now exposes `AmisimApplication` as a library-facing integration class.

```python
from amisim import AmisimApplication

app = AmisimApplication()

# Create and initialize the internal DB (default local SQLite file)
app.init_db()
```

The method `init_db` is implemented and initializes the internal AMISim database.
The methods `load_settings`, `load_params`, and `run` are currently stubs and intentionally raise `NotImplementedError` until the core simulation logic is implemented.

Logging is configured through `loguru`; logs are emitted to stderr and persisted in the internal DB log table once `init_db` has initialized the database.

`load_settings` uses `ga-configreader` and accepts runtime override options passed from CLI as `-O SECTION:NAME=VALUE`, transformed into a nested dictionary.
If `DATABASE_SETTINGS.DB_SETTINGS_USE=True`, settings are reconfigured to include the DB provider using `DB_SETTINGS_URL` and query metadata.

Log configuration is loaded from the `LOGGING` section, including colored output format and contextual fields like `execution_id`, elapsed time from start, and elapsed time from previous message.

The app logger extends `ga-tictoc` `TicToc`, so elapsed/progress timing utilities are directly available on logger instances.

Detailed library API documentation is available in `docs/library.md`.

## Runtime Dependencies

The project declares these primary runtime dependencies:

- `ga-configreader`
- `ga-tictoc`
- `SQLAlchemy`
- `loguru`
