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
- load_params
- run

All methods currently raise NotImplementedError by design.

## Method Reference

### init_db

Signature:

```python
init_db(
    *,
    url: str | None = None,
    host: str | None = None,
    port: int | None = None,
    user: str | None = None,
    password: str | None = None,
    name: str | None = None,
    db_type: str | None = None,
    driver: str | None = None,
) -> None
```

Use this method to initialize database resources. It accepts either a ready SQLAlchemy URL or components required to build one.

### load_settings

Signature:

```python
load_settings(settings_path: Path | None = None) -> None
```

Use this method to load runtime settings from an INI file.

### load_params

Signature:

```python
load_params(params_path: Path | None = None) -> None
```

Use this method to load runtime parameters from a JSON file.

### run

Signature:

```python
run() -> None
```

Use this method to execute the simulation workflow.

## Integration Note

Current CLI support is designed around this class so custom applications can inject their own AmisimApplication implementation during testing or embedding.
