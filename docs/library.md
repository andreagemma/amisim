# amisim Library API

AMISim can be used as a Python library through the AmisimApplication class.

## Public Entry Point

```python
from amisim import AmisimApplication
```

## Class: AmisimApplication

This class is prepared for integration and keeps method signatures stable while internal behavior is being developed.

Available methods:
- init_db
- load_settings
- clean_db
- load_params
- run

`init_db` is implemented and creates the internal AMISim database schema.
`load_settings` and `clean_db` are implemented.
`load_params` and `run` currently raise NotImplementedError by design.

Typed settings model:
- `AmisimApplication.settings_reader` is the active `ConfigReader` instance.
- `AmisimApplication.ini` provides typed access to configuration sections through `IniBase`/`IniModel`.
- The model is defined in `src/amisim/ini_model.py` with uppercase section and field names.
- Values are read on-demand at runtime from `settings_reader` (for example `ini.GENERAL.DEBUG` or `ini.get("GENERAL", "DEBUG", default=False)`).
- Unknown sections and fields discovered from active providers are created dynamically at runtime and are exposed as string fields.
- If `load_settings(None)` is called, a default `ConfigReader` is created and the typed default structure remains available.

## Method Reference

### init_db

Signature:

```python
init_db(
    *,
    url: str | None = None,
    schema: str | None = None,
    host: str | None = None,
    port: int | None = None,
    user: str | None = None,
    password: str | None = None,
    name: str | None = None,
    db_type: str | None = None,
    driver: str | None = None,
) -> None
```

Use this method to create and initialize the internal AMISim database. It accepts either a ready SQLAlchemy URL or components required to build one.

Behavior details:
- If `url` is provided, it is used directly.
- If no URL is provided and no explicit type is passed, AMISim defaults to `sqlite+pysqlite:///.../amisim.db` in the current working directory.
- If `schema` is provided, tables are created and resolved in that schema when supported by the selected backend.
- For non-SQLite databases, `name` is required.
- After database initialization, process logging is configured through `loguru`.

### load_settings

Signature:

```python
load_settings(
    settings_path: Path | None = None,
    overrides: dict[str, dict[str, str]] | None = None,
) -> None
```

Use this method to load base software settings from an INI file, optionally overriding values.

Behavior details:
- `overrides` expects a nested dictionary in the shape `section -> key -> value`.
- If section `DATABASE_SETTINGS` has `DB_SETTINGS_USE=True`, AMISim reads `DB_SETTINGS_URL` and `DB_SETTINGS_QUERY` (or `DB_SETTINGS_TABLE_NAME`) and reconfigures the reader to source settings from DB as well.
- Provider precedence is: CLI overrides, DB settings (if enabled), INI values, environment values.
- The method updates `settings_reader` and keeps `ini` synchronized for autocomplete-friendly, runtime-backed access.

### load_params

Signature:

```python
load_params(params_path: Path | None = None) -> None
```

Use this method to load runtime parameters from a JSON file.

### clean_db

Signature:

```python
clean_db(
    *,
    time: str | datetime.timedelta | datetime.datetime | None = None,
    what: str = "all",
    include_pending_executions: bool = False,
    include_active_tokens: bool = False,
    checkpoint_truncate: bool = True,
    vacuum: bool = True,
) -> dict[str, int]
```

Use this method to prune internal DB data with optional retention criteria.

Behavior details:
- `time=None` means no cutoff filter.
- `time` can be a tmpreaper-like age string (`2d`, `12h`, `1w2d`), a `datetime.timedelta`, or a `datetime.datetime` cutoff.
- `what` accepts `all`, `logs`, `tokens`, `executions`.
- Logs cleanup uses `created_at`.
- Executions cleanup uses `end_time` for non-pending rows.
- Pending executions are preserved by default and included only when `include_pending_executions=True`.
- Tokens cleanup removes only expired rows by default; use `include_active_tokens=True` to remove non-expired rows too.
- On SQLite backends, `checkpoint_truncate=True` and `vacuum=True` are enabled by default and run `PRAGMA wal_checkpoint(TRUNCATE)` and `VACUUM` after cleanup.

### run

Signature:

```python
run() -> None
```

Use this method to execute the simulation workflow.

## Integration Note

Current CLI support is designed around this class so custom applications can inject their own AmisimApplication implementation during testing or embedding.

## Logging

AMISim uses `loguru` for runtime logging.

The application logger class extends `ga-tictoc` `TicToc`, so timing, progress and named timer features are available directly on logger instances.

- Console sink: logs are emitted to stderr.
- Database sink: logs are also persisted in the internal `logs` table when the DB has been initialized.

The runtime logging setup is configured from the `LOGGING` section in settings:
- `LOG_USE` enables/disables logging sinks.
- `LOG_LEVEL`, `LOG_ON_CONSOLE`, `LOG_ON_DATABASE`, `LOG_ON_FILE`, `LOG_NAME`, `LOG_DIR` configure sink behavior.
- `LOG_FORMAT` accepts legacy `%` placeholders and is translated to loguru format, with colorized console output.

Use section-aware loggers with optional execution context:

```python
from amisim import get_logger

log = get_logger(section="assignment", execution_id=42)
log.info("Step started")
```

Each record includes:
- `execution_id`: current execution identifier (if provided).
- `elapsed`: time from first log of that section/execution pair.
- `last_elapsed`: time from previous message in the same section/execution pair.
