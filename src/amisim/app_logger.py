"""Application logging configuration based on loguru."""

from __future__ import annotations

import datetime
import logging
import threading
import time
import sys
from typing import Any

from loguru import logger
from tictoc import TicToc

from .database import DB

_CONFIGURED = False
_LOGGER = logger
_TIMING_LOCK = threading.Lock()
_TIMINGS: dict[tuple[str, str], tuple[float, float]] = {}

_DEFAULT_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan> | "
    "<magenta>{extra[last_elapsed]:.2f}</magenta>/<yellow>{extra[elapsed]:.2f}</yellow>s | "
    "<blue>{extra[execution_id]}</blue> -> "
    "<level>{message}</level>"
)


class _LoguruBridgeHandler(logging.Handler):
    """Forward stdlib logging records to configured loguru sinks."""

    def emit(self, record: logging.LogRecord) -> None:
        level: str | int
        try:
            level = logger.level(record.levelname).name
        except Exception:
            level = record.levelno

        log = _LOGGER.bind(execution_id=getattr(record, "execution_id", "-"))
        log.patch(lambda rec: rec.update(name=record.name)).log(level, record.getMessage())


class AmisimLogger(TicToc):
    """Application logger that extends TicToc timing/logging features."""

    def __init__(
        self,
        *,
        section: str = "app",
        execution_id: int | str | None = None,
    ) -> None:
        std_logger = logging.getLogger(f"amisim.{section}")
        super().__init__(logger=std_logger, extra={"execution_id": execution_id if execution_id is not None else "-"})
        # Start timer immediately so elapsed/last_elapsed metrics are meaningful from first log.
        self.tic(reset_origin=True)


def _record_timing(record: dict[str, Any]) -> None:
    """Attach elapsed and delta times to each log record."""
    section = str(record.get("name", "app"))
    execution_id = str(record["extra"].get("execution_id", "-"))
    key = (section, execution_id)
    now = time.perf_counter()

    with _TIMING_LOCK:
        start, last = _TIMINGS.get(key, (now, now))
        _TIMINGS[key] = (start, now)

    record["extra"].setdefault("execution_id", execution_id)
    record["extra"]["elapsed"] = now - start
    record["extra"]["last_elapsed"] = now - last


def _normalize_format(raw_format: str | None) -> str:
    """Convert legacy %-style logging format to loguru format string."""
    if not raw_format:
        return _DEFAULT_FORMAT

    normalized = raw_format
    # Support legacy interpolation-escaped values from INI (%%(...)s).
    normalized = normalized.replace("%%", "%")

    replacements = {
        "%(asctime)s": "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green>",
        "%(levelname)s": "<level>{level: <8}</level>",
        "%(name)s": "<cyan>{name}</cyan>",
        "%(message)s": "<level>{message}</level>",
        "%(execution_id)s": "<blue>{extra[execution_id]}</blue>",
        "%(elapsed).2fs": "<yellow>{extra[elapsed]:.2f}</yellow>s",
        "%(last_elapsed).2f": "<magenta>{extra[last_elapsed]:.2f}</magenta>",
    }
    for old, new in replacements.items():
        normalized = normalized.replace(old, new)

    if "{message}" not in normalized:
        normalized = f"{normalized} <level>{{message}}</level>"
    return normalized


def _db_sink(message: Any) -> None:
    """Persist loguru messages in the internal DB log table."""
    record = message.record
    log_time = record.get("time")
    created_at: datetime.datetime | None = log_time if isinstance(log_time, datetime.datetime) else None

    DB.write_log(
        level_no=record["level"].no,
        level_name=record["level"].name,
        message=record["message"],
        created_by=record["name"],
        execution_id=int(record["extra"]["execution_id"])
        if str(record["extra"].get("execution_id", "")).isdigit()
        else None,
        created_at=created_at,
    )


def configure_logging(
    *,
    level: str = "INFO",
    log_format: str | None = None,
    log_on_console: bool = True,
    log_on_db: bool = True,
    log_on_file: bool = False,
    log_name: str = "amisim",
    log_dir: str = "log",
    force: bool = False,
) -> None:
    """Configure process-level loguru sinks once.

    One sink prints to stderr and one sink persists logs to the internal DB.
    """
    global _CONFIGURED
    if _CONFIGURED and not force:
        return

    logger.remove()
    with _TIMING_LOCK:
        _TIMINGS.clear()

    normalized_format = _normalize_format(log_format)
    global _LOGGER
    _LOGGER = logger.patch(_record_timing)

    if log_on_console:
        _LOGGER.add(
            sys.stderr,
            level=level,
            format=normalized_format,
            colorize=True,
            enqueue=True,
            backtrace=False,
            diagnose=False,
        )

    if log_on_file:
        from pathlib import Path

        output_dir = Path(log_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        _LOGGER.add(
            output_dir / f"{log_name}.log",
            level=level,
            format=normalized_format,
            colorize=False,
            enqueue=True,
            backtrace=False,
            diagnose=False,
        )

    if log_on_db:
        _LOGGER.add(_db_sink, level=level, enqueue=False, catch=True)

    # Route stdlib logging (used by TicToc) through loguru sinks.
    root_logger = logging.getLogger("amisim")
    root_logger.handlers = [h for h in root_logger.handlers if not isinstance(h, _LoguruBridgeHandler)]
    root_logger.addHandler(_LoguruBridgeHandler())
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    root_logger.propagate = False

    _CONFIGURED = True


def configure_logging_from_settings(settings: Any) -> None:
    """Configure logger according to LOGGING section read by ConfigReader."""
    log_use = settings.getboolean("LOG_USE", section="LOGGING", default=True)
    if not log_use:
        configure_logging(log_on_console=False, log_on_db=False, log_on_file=False, force=True)
        return

    configure_logging(
        level=settings.get("LOG_LEVEL", section="LOGGING", default="INFO") or "INFO",
        log_format=settings.get("LOG_FORMAT", section="LOGGING", default=_DEFAULT_FORMAT),
        log_on_console=settings.getboolean("LOG_ON_CONSOLE", section="LOGGING", default=True) is True,
        log_on_db=settings.getboolean("LOG_ON_DATABASE", section="LOGGING", default=True) is True,
        log_on_file=settings.getboolean("LOG_ON_FILE", section="LOGGING", default=False) is True,
        log_name=settings.get("LOG_NAME", section="LOGGING", default="amisim") or "amisim",
        log_dir=settings.get("LOG_DIR", section="LOGGING", default="log") or "log",
        force=True,
    )


def configure_logging_from_typed_settings(settings: Any) -> None:
    """Configure logger from typed ``LoggingSettings`` values."""
    if not bool(getattr(settings, "LOG_USE", True)):
        configure_logging(log_on_console=False, log_on_db=False, log_on_file=False, force=True)
        return

    configure_logging(
        level=str(getattr(settings, "LOG_LEVEL", "INFO") or "INFO"),
        log_format=str(getattr(settings, "LOG_FORMAT", _DEFAULT_FORMAT) or _DEFAULT_FORMAT),
        log_on_console=bool(getattr(settings, "LOG_ON_CONSOLE", True)),
        log_on_db=bool(getattr(settings, "LOG_ON_DATABASE", True)),
        log_on_file=bool(getattr(settings, "LOG_ON_FILE", False)),
        log_name=str(getattr(settings, "LOG_NAME", "amisim") or "amisim"),
        log_dir=str(getattr(settings, "LOG_DIR", "log") or "log"),
        force=True,
    )


def get_logger(section: str | None = None, execution_id: int | str | None = None) -> AmisimLogger:
    """Return a TicToc-based application logger.

    The logger routes through loguru sinks and includes execution context.
    """
    if not _CONFIGURED:
        configure_logging()
    return AmisimLogger(section=section or "app", execution_id=execution_id)
