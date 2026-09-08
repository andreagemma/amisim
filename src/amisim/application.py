"""Public application API for library integrations."""

from __future__ import annotations

import datetime
from pathlib import Path
from urllib.parse import quote_plus
from collections.abc import Iterable
from configreader import ConfigReader, ConfigSource
import importlib.metadata

from .app_logger import configure_logging, configure_logging_from_typed_settings, get_logger
from .database import DB
from .ini_model import IniModel
from .utils import parse_age_to_timedelta, parse_section_option_overrides


class AmisimApplication:
    """Library entrypoint exposing the core AMISim operations.

    ``init_db`` is implemented and initializes the internal persistence layer.
    ``load_settings``, ``load_params`` and ``run`` keep their public contracts
    while business logic is being completed.
    """

    APP_NAME: str = importlib.metadata.metadata(__package__ if __package__ else "")["Name"].upper()

    def __init__(self) -> None:
        """Initialize application integration state."""
        self.settings_reader: ConfigReader = ConfigReader(
            dictionary={}, providers=[ConfigSource.DICT, ConfigSource.ENV], env_default_section=self.APP_NAME
        )
        self.ini: IniModel = IniModel.from_config(self.settings_reader)
        self.log = get_logger(section="application")

    @staticmethod
    def _build_database_url(
        *,
        url: str | None,
        host: str | None,
        port: int | None,
        user: str | None,
        password: str | None,
        name: str | None,
        db_type: str | None,
        driver: str | None,
    ) -> str:
        """Build an internal DB URL from structured options.

        Defaults to a local SQLite file when no explicit URL/type is provided.
        """
        if url and url.strip():
            return url.strip()

        resolved_db_type = (db_type or "sqlite").strip().lower()
        resolved_driver = (driver or "").strip()
        dialect = f"{resolved_db_type}+{resolved_driver}" if resolved_driver else resolved_db_type

        if resolved_db_type == "sqlite":
            db_name = (name or "amisim.db").strip() or "amisim.db"
            if db_name == ":memory:":
                return "sqlite+pysqlite:///:memory:"

            db_path = Path(db_name)
            if not db_path.is_absolute():
                db_path = Path.cwd() / db_path
            return f"sqlite+pysqlite:///{db_path.as_posix()}"

        db_name = (name or "").strip()
        if not db_name:
            raise ValueError("Database name is required for non-sqlite databases")

        auth = ""
        db_user = (user or "").strip()
        if db_user:
            auth = quote_plus(db_user)
            db_password = (password or "").strip()
            if db_password:
                auth = f"{auth}:{quote_plus(db_password)}"
            auth = f"{auth}@"

        db_host = (host or "localhost").strip() or "localhost"
        db_port = f":{port}" if port is not None else ""
        return f"{dialect}://{auth}{db_host}{db_port}/{db_name}"

    def init_db(
        self,
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
    ) -> None:
        """Create and initialize the internal AMISim database.

        :param url: SQLAlchemy connection URL, if already available.
        :param schema: Optional schema name for table creation, when supported.
        :param host: Database host.
        :param port: Database port.
        :param user: Database user.
        :param password: Database password.
        :param name: Internal database name.
        :param db_type: Database type, e.g. postgresql/mysql/sqlite.
        :param driver: Optional SQLAlchemy driver suffix.
        :raises ValueError: If the provided options cannot build a valid DB URL.
        """
        database_url = self._build_database_url(
            url=url,
            host=host,
            port=port,
            user=user,
            password=password,
            name=name,
            db_type=db_type,
            driver=driver,
        )
        DB.init_db(database_url, schema=schema)
        configure_logging()
        self.log.info("Internal database initialized")

    def load_settings(
        self,
        settings_path: Path | str | None = None,
        overrides: dict[str, dict[str, str]] | Iterable[str] | None = None,
    ) -> None:
        """Load base software configuration.

        :param settings_path: Path to an INI file with base software configuration.
        :param overrides: Optional section/key overrides from runtime options.
        If ``settings_path`` is ``None``, default typed settings are created.
        """
        if isinstance(settings_path, str):
            settings_path = Path(settings_path)
        if isinstance(overrides, Iterable) and not isinstance(overrides, dict):
            overrides = parse_section_option_overrides(overrides)
        merged_overrides = overrides or {}
        if settings_path is None:
            self.settings_reader = ConfigReader(
                dictionary=merged_overrides,
                providers=[ConfigSource.DICT, ConfigSource.ENV],
                env_default_section=self.APP_NAME,
            )
            self.ini = IniModel.from_config(self.settings_reader)
            configure_logging_from_typed_settings(self.ini.LOGGING)
            self.log.info("Default settings model loaded")
            return

        reader = ConfigReader(
            file=settings_path,
            dictionary=merged_overrides,
            providers=[ConfigSource.DICT, ConfigSource.ENV, ConfigSource.INI],
            env_default_section=self.APP_NAME,
        )

        use_db_settings = reader.getboolean("DB_SETTINGS_USE", section="DATABASE_SETTINGS", default=False)
        if use_db_settings:
            db_url = reader.get("DB_SETTINGS_URL", section="DATABASE_SETTINGS")
            db_query = reader.get("DB_SETTINGS_QUERY", section="DATABASE_SETTINGS")
            if not db_query:
                table_name = reader.get("DB_SETTINGS_TABLE_NAME", section="DATABASE_SETTINGS", default="settings")
                db_query = f"SELECT value FROM {table_name} WHERE name = :name and section = :section"

            if db_url:
                reader = ConfigReader(
                    file=settings_path,
                    dictionary=merged_overrides,
                    db_url=db_url,
                    db_query=db_query,
                    providers=[ConfigSource.DICT, ConfigSource.ENV, ConfigSource.DB, ConfigSource.INI],
                    env_default_section=self.APP_NAME,
                )

        self.settings_reader = reader
        self.ini = IniModel.from_config(reader)
        configure_logging_from_typed_settings(self.ini.LOGGING)
        self.log.info("Settings loaded")

    def load_params(self, params_path: Path | None = None) -> None:
        """Load algorithm execution parameters.

        :param params_path: Path to a JSON file with algorithm execution parameters.
        :raises NotImplementedError: Always, until business logic is provided.
        """
        raise NotImplementedError("load_params is not implemented yet")

    def clean_db(
        self,
        *,
        time: str | datetime.timedelta | datetime.datetime | None = None,
        what: str = "all",
        include_pending_executions: bool = False,
        include_active_tokens: bool = False,
        checkpoint_truncate: bool = True,
        vacuum: bool = True,
    ) -> dict[str, int]:
        """Clean internal database records using target and retention filters.

        :param time: Optional retention selector; accepts tmpreaper-like strings,
            ``datetime.timedelta``, ``datetime.datetime``, or ``None``.
        :param what: Cleanup target: ``all``, ``logs``, ``tokens``, ``executions``.
        :param include_pending_executions: Include pending executions in deletion.
        :param include_active_tokens: Include non-expired tokens in deletion.
        :param checkpoint_truncate: Run SQLite WAL checkpoint truncate after cleanup.
        :param vacuum: Run SQLite VACUUM after cleanup.
        :return: Deleted rows count for logs, tokens and executions.
        :raises ValueError: If ``time`` string cannot be parsed.
        :raises TypeError: If ``time`` has an unsupported type.
        """
        cutoff: datetime.datetime | None = None
        if isinstance(time, str):
            delta = parse_age_to_timedelta(time)
            cutoff = datetime.datetime.now(datetime.timezone.utc) - delta
        elif isinstance(time, datetime.timedelta):
            cutoff = datetime.datetime.now(datetime.timezone.utc) - time
        elif isinstance(time, datetime.datetime):
            cutoff = (
                time.replace(tzinfo=datetime.timezone.utc)
                if time.tzinfo is None
                else time.astimezone(datetime.timezone.utc)
            )
        elif time is None:
            cutoff = None
        else:
            raise TypeError("time must be str, datetime.timedelta, datetime.datetime, or None")

        deleted = DB.clean_db(
            what=what,
            cutoff=cutoff,
            include_pending_executions=include_pending_executions,
            include_active_tokens=include_active_tokens,
            checkpoint_truncate=checkpoint_truncate,
            vacuum=vacuum,
        )
        self.log.info(
            "Database cleanup completed: what=%s cutoff=%s include_pending_executions=%s include_active_tokens=%s checkpoint_truncate=%s vacuum=%s deleted=%s",
            what,
            cutoff.isoformat() if cutoff is not None else "None",
            include_pending_executions,
            include_active_tokens,
            checkpoint_truncate,
            vacuum,
            deleted,
        )
        return deleted

    def run(self) -> None:
        """Run the simulation workflow.

        :raises NotImplementedError: Always, until business logic is provided.
        """
        raise NotImplementedError("run is not implemented yet")
