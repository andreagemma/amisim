# amisim
Meso-scopic Traffic Assignment Model

## CLI

The console command is `amisim` and supports these command modes:

- `amisim run [-s SETTINGS] [-p PARAMS] [-e KEY=VALUE ...]`
- `amisim server [-H HOST] [-P PORT] [-D]`
- `amisim init_db [-u URL] [-H HOST] [-P PORT] [-U USER] [-W PASSWORD] [-N NAME] [-t TYPE] [-D DRIVER]`

Behavior notes:

- If no command is provided, arguments are parsed as `run`.
- In `run`, `-s/--settings` defaults to empty; when empty and `settings.ini` exists in the current working directory, that file is used.
- In `run`, `-p/--params` defaults to empty; when empty and `parmas.json` exists in the current working directory, that file is used.
- In `run`, `-e/--env` can be passed multiple times as `KEY=VALUE` to override environment variables for the execution scope.

Detailed CLI documentation is available in `docs/cli.md`.

## Library Usage

The package now exposes `AmisimApplication` as a library-facing integration class.

```python
from amisim import AmisimApplication

app = AmisimApplication()
```

The methods `init_db`, `load_settings`, `load_params`, and `run` are currently prepared as stubs and intentionally raise `NotImplementedError` until the internal logic is implemented.

Detailed library API documentation is available in `docs/library.md`.
