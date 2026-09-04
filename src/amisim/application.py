"""Public application API for library integrations."""

from __future__ import annotations

from pathlib import Path


class AmisimApplication:
    """Library entrypoint exposing the core AMISim operations.

    The methods are intentionally left as stubs so CLI and library integrations
    can be wired before business logic is implemented.
    """

    def init_db(
        self,
        *,
        url: str | None = None,
        host: str | None = None,
        port: int | None = None,
        user: str | None = None,
        password: str | None = None,
        name: str | None = None,
        db_type: str | None = None,
        driver: str | None = None,
    ) -> None:
        """Initialize database resources.

        :param url: SQLAlchemy connection URL, if already available.
        :param host: Database host.
        :param port: Database port.
        :param user: Database user.
        :param password: Database password.
        :param name: Database name.
        :param db_type: Database type, e.g. postgresql/mysql/sqlite.
        :param driver: Optional SQLAlchemy driver suffix.
        :raises NotImplementedError: Always, until business logic is provided.
        """
        raise NotImplementedError("init_db is not implemented yet")

    def load_settings(self, settings_path: Path | None = None) -> None:
        """Load runtime settings.

        :param settings_path: Path to an INI settings file.
        :raises NotImplementedError: Always, until business logic is provided.
        """
        raise NotImplementedError("load_settings is not implemented yet")

    def load_params(self, params_path: Path | None = None) -> None:
        """Load runtime parameters.

        :param params_path: Path to a JSON params file.
        :raises NotImplementedError: Always, until business logic is provided.
        """
        raise NotImplementedError("load_params is not implemented yet")

    def run(self) -> None:
        """Run the simulation workflow.

        :raises NotImplementedError: Always, until business logic is provided.
        """
        raise NotImplementedError("run is not implemented yet")
