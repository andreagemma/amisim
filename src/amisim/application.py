"""Public application API for library integrations."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote_plus
from collections.abc import Iterable
from configreader import ConfigReader, ConfigSource

from .app_logger import configure_logging, configure_logging_from_settings, get_logger
from .database import DB
from .utils import parse_section_option_overrides


class AmisimApplication:
    """Library entrypoint exposing the core AMISim operations.

    ``init_db`` is implemented and initializes the internal persistence layer.
    ``load_settings``, ``load_params`` and ``run`` keep their public contracts
    while business logic is being completed.
    """

    def __init__(self) -> None:
        """Initialize application integration state."""
        self.settings: ConfigReader | None = None

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
        get_logger().info("Internal database initialized")

    def load_settings(
        self,
        settings_path: Path | None = None,
        overrides: dict[str, dict[str, str]] | Iterable[str] | None = None,
    ) -> None:
        """Load base software configuration.

        :param settings_path: Path to an INI file with base software configuration.
        :param overrides: Optional section/key overrides from runtime options.
        :raises ValueError: If settings_path is not provided.
        """
        if settings_path is None:
            raise ValueError("settings_path is required")
        if isinstance(overrides, Iterable) and not isinstance(overrides, dict):
            overrides = parse_section_option_overrides(overrides)
        merged_overrides = overrides or {}
        reader = ConfigReader(
            file=settings_path,
            dictionary=merged_overrides,
            providers=[ConfigSource.DICT, ConfigSource.INI, ConfigSource.ENV],
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
                    providers=[ConfigSource.DICT, ConfigSource.DB, ConfigSource.INI, ConfigSource.ENV],
                )

        self.settings = reader
        configure_logging_from_settings(self.settings)
        get_logger(section="settings").info("Settings loaded")

    def load_params(self, params_path: Path | None = None) -> None:
        """Load algorithm execution parameters.

        :param params_path: Path to a JSON file with algorithm execution parameters.
        :raises NotImplementedError: Always, until business logic is provided.
        """
        raise NotImplementedError("load_params is not implemented yet")

    def run(self) -> None:
        """Run the simulation workflow.

        :raises NotImplementedError: Always, until business logic is provided.
        """
        raise NotImplementedError("run is not implemented yet")
