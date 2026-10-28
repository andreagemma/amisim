# amisim Library API

AMISim can be used as a Python library through the `AmisimApp` class.

## Public Entry Point

```python
from amisim import AmisimApp
```

## Class: AmisimApp

This class is prepared for integration and keeps method signatures stable while internal behavior is being developed.

Available methods:
- init_db
- load_settings
- clean_db
- load_params
- run

`init_db` is implemented and creates the internal AMISim database schema.
`load_settings`, `clean_db`, and `load_params` are implemented.
`run` currently raises NotImplementedError by design.

Typed settings model:
- `AmisimApp.settings_reader` is the active `ConfigReader` instance.
- `AmisimApp.ini` provides typed access to configuration sections through `IniBase`/`IniModel`.
- The model is defined in `src/amisim/config/ini_model.py` with uppercase section and field names.
- Values are read on-demand at runtime from `settings_reader` (for example `ini.GENERAL.DEBUG` or `ini.get("GENERAL", "DEBUG", default=False)`).
- Unknown sections and fields discovered from active providers are created dynamically at runtime and are exposed as string fields.
- If `load_settings(None)` is called, a default `ConfigReader` is created and the typed default structure remains available.

The application initializes its `parallel` runtime from the `PARALLEL` settings section:
- `PARALLEL_USE` enables or disables parallel execution.
- `PARALLEL_NUMCPUS` sets the requested CPU count.
- `PARALLEL_ENGINE` selects the execution engine.
- `PARALLEL_CLUSTER_ADDRESS` is passed to the Ray engine.

Calling `load_settings` again closes and recreates the runtime using the updated settings.

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

Use this method to load runtime parameters from a JSON or YAML file. The resulting `ParamsParser` is available as `app.parser`.

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

Current CLI support is designed around this class so custom applications can inject their own `AmisimApp` implementation during testing or embedding.

## Model

The `amisim.model` package holds the domain objects shared by the algorithms.

- `Workspace`: loads and keeps `graph`, `modes`, `matrices` and `links_sets`, with `load_graph`, `load_modes`, `load_matrices` and `load_links_sets` (each supports `force=True` to reload).
- `Graph`: time dependent network built from the nodes, links and turns sources through `Graph.read` or `read_params`; exposes `nodes`, `links`, `turns`, `centroids`, `get_timestamps`, `reset_flows` and `reset_costs`.
- `Modes`: transport modes indexed by code; `parse` resolves `"all"`, `"none"`, a single code or a set of codes.
- `Matrices`: demand matrices per mode plus the equivalent matrix obtained weighting each mode by its `eq_factor`.
- `LinksSet`: named sets of links used to group results.
- `Paths`: multimodal paths keyed by mode, built with `from_dict`/`from_pandas` and persisted with `write`.

Sources are described by `InputParameters` (or plain dictionaries/paths) and destinations by `OutputParameters`; the loaders in `amisim.model.loaders` normalize the fields declared in their `field_definition`.

## Algorithms

The `amisim.algorithms` package exposes the computations available on a workspace.

- `Dispatcher(app).dispatch("shortest_path")` runs an algorithm by operation name.
- `ShortestPath(app, parallel=False).run(...)` computes the time dependent shortest paths for every mode and timestamp and returns a `Paths` instance. Missing arguments default to the workspace content: `graph`, `nodes` (graph centroids), `modes` and `timestamps`.
- `StaticAON(app, workspace).run(tstart, tend)` performs a static all-or-nothing assignment through `StaticSimulator`, loading the path flows on the links and updating the link costs with a BPR function.

### Parallel shortest paths

```python
from amisim.algorithms import ShortestPath

paths = ShortestPath(app=app, parallel=True).run()
```

With `parallel=True` the algorithm builds one task per mode, timestamp and origin node through `get_tasks`, and distributes the chunks on `app.parallel` (configured from the `[PARALLEL]` settings). Each worker builds its own router per mode, so results are merged by mode and are equivalent to the sequential execution.

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
