"""Public application API for library integrations."""

from __future__ import annotations

import datetime
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from configreader import ConfigReader, ConfigSource
from gataframe import Engine as GataframeEngine
from parallel import Engine, Parallel
from serializer import Serializer

from ._version import __app_name__
from .app_logger import configure_logging, configure_logging_from_typed_settings, get_logger
from .config.ini_model import IniModel
from .config.params_parser import ParamsParser
from .database import DB, Execution
from .functions.day_type import day_type
from .model.workspace import Workspace
from .utils import parse_age_to_timedelta, parse_section_option_overrides

__all__ = ["AmisimApp"]


class AmisimApp:
    """Library entrypoint exposing the core AMISim operations.

    ``init_db`` is implemented and initializes the internal persistence layer.
    ``load_settings`` and ``load_params`` configure application inputs, while
    ``run`` provides the simulation entry point.
    """

    APP_NAME: str = __app_name__.upper()

    singleton_instance: AmisimApp | None = None

    def __init__(
        self,
        settings_path: str | Path | None = None,
        params_or_path: str | Path | dict[str, Any] | None = None,
        overrides_ini: dict[str, Any] | Iterable[str] | None = None,
        overrides_params: list[dict[str, Any] | str | Path | None] | dict[str, Any] | str | Path | None | None = None,
    ) -> None:
        if AmisimApp.singleton_instance is not None:
            raise RuntimeError("An instance of AmisimApp already exists.")

        self._engine_initialized: bool = False
        self._engine: GataframeEngine | None = None
        self._parallel: Parallel | None = None
        self._parallel_initialized: bool = False
        # Initialize application integration state.
        providers: list[ConfigSource | str] = []
        providers.extend([ConfigSource.DICT, ConfigSource.ENV])
        self.ini_settings_reader: ConfigReader = ConfigReader(
            dictionary={}, providers=providers, env_default_section=self.APP_NAME
        )
        self.parser: ParamsParser = ParamsParser(params_or_path)
        if overrides_params is not None:
            if isinstance(overrides_params, list):
                for item in overrides_params:
                    self.parser.merge(item)
            else:
                self.parser.merge(overrides_params)
        overrides_ini_from_params = self.parser.get("settings")
        if overrides_ini_from_params is not None:
            if overrides_ini is not None:
                overrides_ini_from_params.update(overrides_ini)
            else:
                overrides_ini = overrides_ini_from_params
        self.load_settings(settings_path=settings_path, overrides=overrides_ini)

        self.log = get_logger(section=__app_name__)
        AmisimApp.singleton_instance = self
        self.init_db(url=self.ini.DATABASE.DATABASE_URL, schema=self.ini.DATABASE.DATABASE_SCHEMA)
        # self._initialize_parallel()
        self.serializer: Serializer = Serializer(
            compression=self.ini.OUTPUT.OUTPUT_STATE_COMPRESSION, level=self.ini.OUTPUT.OUTPUT_STATE_COMPRESSION_LEVEL
        )

    def get_new_execution(self) -> Execution:
        """Get a new execution instance."""
        e = Execution.create_execution(self.parser.get_all())
        if e is None:
            raise RuntimeError("Failed to create a new execution instance.")
        self.log.extra["execution_id"] = e.id
        return e

    def save_settings(self) -> None:
        """Save the current settings to the designated output location."""
        if params := self.parser.get(self.ini.PARAMS.SETTINGS_RESULTS):
            self.log.debug("Saving settings...")
            try:
                path = Path(params)
                path.parent.mkdir(parents=True, exist_ok=True)
                self.log.debug("Write: %s" % path)
                self.ini.save(path)
                self.log.info("Settings saved in %.2f seconds" % self.log.toc()).toc()
            except Exception as e:
                self.log.error("Failed to save settings:", exc_info=e, stack_info=True)

    def save_params(self) -> None:
        """Save the current parameters to the designated output location."""
        if params := self.parser.get(self.ini.PARAMS.PARAMS_RESULTS):
            self.log.debug("Saving parameters...").tic()
            try:
                path = Path(params)
                path.parent.mkdir(parents=True, exist_ok=True)
                self.log.debug("Write: %s" % path)
                self.parser.save(path)
                self.log.info("Parameters saved in %.2f seconds" % self.log.toc()).toc()
            except Exception as e:
                self.log.error("Failed to save parameters:", exc_info=e, stack_info=True)

    @property
    def workspace(self) -> Workspace:
        """Workspace of the application."""
        if not hasattr(self, "_workspace"):
            self._workspace = Workspace()
        return self._workspace

    @property
    def engine(self) -> GataframeEngine:
        """Gataframe engine of the application."""
        if not self._engine_initialized:
            self._initialize_engine()
        if self._engine is None:
            self._engine_initialized = False
            raise RuntimeError("Failed to initialize Gataframe engine.")
        return self._engine

    @property
    def parallel(self) -> Parallel:
        """Parallel runtime of the application, initialized on first access."""
        if not self._parallel_initialized:
            self._initialize_parallel()
        if self._parallel is None:
            self._parallel_initialized = False
            raise RuntimeError("Failed to initialize parallel runtime.")
        return self._parallel

    def close(self) -> None:
        """Close the application and release resources."""
        if self._parallel_initialized and self._parallel:
            self._parallel.shutdown(force=True)
            self._parallel_initialized = False
        if self._engine_initialized and self._engine:
            self._engine.close()
            self._engine_initialized = False

    def __del__(self) -> None:
        """Clean up resources on application deletion."""
        self.close()

    @staticmethod
    def open(*args, **kwargs) -> AmisimApp:
        """Open the singleton application, creating it if needed."""
        return AmisimApp.get_instance(*args, **kwargs)

    def __enter__(self) -> AmisimApp:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        """Clean up resources on application exit."""
        self.close()

    @staticmethod
    def get_instance(*args, **kwargs) -> AmisimApp:
        """Return the singleton application, creating it if needed.

        Args:
            *args: Positional arguments used when creating the instance.
            **kwargs: Keyword arguments used when creating the instance.

        Returns:
            The singleton `AmisimApp` instance.
        """
        if AmisimApp.singleton_instance is None:
            AmisimApp(*args, **kwargs)
        if AmisimApp.singleton_instance is None:
            raise ValueError("Failed to create AmisimApp instance")
        return AmisimApp.singleton_instance

    def _initialize_engine(self) -> None:
        """Initialize the Gataframe engine."""
        self._engine = GataframeEngine(
            logger=self.log.getChild("IO") if self.log else None,  # type: ignore
        )  # type: ignore
        self._engine.create_function(
            name="day_type", function=day_type, parameters=["TIMESTAMP"], return_type="VARCHAR"
        )
        self._engine_initialized = True
        self.log.debug("Gataframe engine initialized.") if self.log else None

    def _initialize_parallel(self) -> None:
        """Initialize the parallel runtime from the current INI settings."""
        settings = self.ini.PARALLEL
        engine_str = settings.PARALLEL_ENGINE if settings.PARALLEL_USE else Engine.NONE
        engine = Engine.parse(engine_str)
        if self._parallel_initialized and self._parallel:
            self._parallel.shutdown(force=True)
            self._parallel_initialized = False

        engine_options = {}
        if engine is Engine.RAY:
            engine_options["address"] = settings.PARALLEL_CLUSTER_ADDRESS

        self._parallel = Parallel(
            num_cpus=settings.PARALLEL_NUMCPUS,
            engine=engine,
            log=self.log.getChild("parallel"),  # type: ignore
            **engine_options,
        )
        self._parallel_initialized = True

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
        # Internal helper: build database url.
        if url is None or not url.strip():
            # in memory db
            return "sqlite+pysqlite:///:memory:"
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

        Args:
            url: SQLAlchemy connection URL, if already available.
            schema: Optional schema name for table creation, when supported.
            host: Database host.
            port: Database port.
            user: Database user.
            password: Database password.
            name: Internal database name.
            db_type: Database type, for example postgresql/mysql/sqlite.
            driver: Optional SQLAlchemy driver suffix.

        Raises:
            ValueError: If the provided options cannot build a valid DB URL.
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

        Args:
            settings_path: Path to an INI file with base software configuration.
            overrides: Optional section/key overrides from runtime options.

        If ``settings_path`` is ``None``, default typed settings are created.
        """
        if isinstance(settings_path, str):
            settings_path = Path(settings_path)
        if isinstance(overrides, Iterable) and not isinstance(overrides, dict):
            overrides = parse_section_option_overrides(overrides)
        merged_overrides: dict[str, dict[str, str | float | bool | None]] = {
            section: dict(options) for section, options in (overrides or {}).items()
        }
        providers: list[ConfigSource | str] = [ConfigSource.DICT, ConfigSource.ENV]
        if settings_path is None:
            reader = ConfigReader(
                dictionary=merged_overrides,
                providers=providers,
                env_default_section=self.APP_NAME,
            )
            self.ini_settings_reader = reader
            self.ini = IniModel.from_config(self.ini_settings_reader)
            configure_logging_from_typed_settings(self.ini.LOGGING)
            self.log = get_logger(__app_name__)
            self.log.info("Default settings model loaded")
        else:
            providers.append(ConfigSource.INI)
            reader = ConfigReader(
                file=settings_path,
                dictionary=merged_overrides,
                providers=providers,
                env_default_section=self.APP_NAME,
            )
            self.ini_settings_reader = reader
            self.ini = IniModel.from_config(reader)
            configure_logging_from_typed_settings(self.ini.LOGGING)
            self.log = get_logger(__app_name__)
            self.log.info("File settings loaded")

        use_db_settings = reader.getboolean("DB_SETTINGS_USE", section="DATABASE_SETTINGS", default=False)
        if use_db_settings:
            db_url = reader.get("DB_SETTINGS_URL", section="DATABASE_SETTINGS")
            db_query = reader.get("DB_SETTINGS_QUERY", section="DATABASE_SETTINGS")
            if not db_query:
                table_name = reader.get("DB_SETTINGS_TABLE_NAME", section="DATABASE_SETTINGS", default="settings")
                db_query = f"SELECT value FROM {table_name} WHERE name = :name and section = :section"

            if db_url:
                providers.append(ConfigSource.DB)
                reader = ConfigReader(
                    file=settings_path,
                    dictionary=merged_overrides,
                    db_url=db_url,
                    db_query=db_query,
                    providers=providers,
                    env_default_section=self.APP_NAME,
                )

                self.ini_settings_reader = reader
                self.ini = IniModel.from_config(reader)
                configure_logging_from_typed_settings(self.ini.LOGGING)
                self.log = get_logger(__app_name__)
                self.log.info("DB settings loaded")
        self.log.info("Settings loading complete")

    def load_params(self, params_path: Path | None = None) -> None:
        """Load algorithm execution parameters.

        Args:
            params_path: Path to a JSON or YAML file with execution parameters.
        """
        if params_path is None:
            return
        self.parser.update(params_path)

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

        Args:
            time: Optional retention selector; accepts tmpreaper-like strings,
                ``datetime.timedelta``, ``datetime.datetime``, or ``None``.
            what: Cleanup target: ``all``, ``logs``, ``tokens``, ``executions``.
            include_pending_executions: Include pending executions in deletion.
            include_active_tokens: Include non-expired tokens in deletion.
            checkpoint_truncate: Run SQLite WAL checkpoint truncate after cleanup.
            vacuum: Run SQLite VACUUM after cleanup.

        Returns:
            Deleted rows count for logs, tokens and executions.

        Raises:
            ValueError: If ``time`` string cannot be parsed.
            TypeError: If ``time`` has an unsupported type.
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

    def run(self, operation: str) -> None:
        """Run the simulation workflow.

        Raises:
            NotImplementedError: Always, until business logic is provided.
        """
        op: str | None = operation
        if not bool(operation):
            op = self.parser.get("op") if self.parser else None

        if not op:
            raise ValueError("Operation must be specified")
        else:
            from .algorithms.dispatcher import Dispatcher

            dispatcher = Dispatcher(app=self)
            return dispatcher.dispatch(op)
