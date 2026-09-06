"""Internal database layer for AMISim.

The module exposes a small static facade (`DB`) and ORM models used by the
application runtime.
"""

from __future__ import annotations

import datetime
import json
import logging
import threading
import uuid
from typing import Any

from sqlalchemy import BigInteger, DateTime, Engine, Float, Index, Integer, String, create_engine, event
from sqlalchemy import and_, delete, insert, or_, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, scoped_session, sessionmaker


def _utcnow() -> datetime.datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.datetime.now(datetime.timezone.utc)


class Status(dict):
    """Container for request and simulation status constants."""

    REQ_SUCCESS = "success"
    REQ_ERROR = "error"

    SIM_COMPLETED = "completed"
    SIM_RUNNING = "running"
    SIM_PENDING = "pending"
    SIM_FAILED = "failed"

    def __init__(
        self,
        status: str,
        error: str | None = None,
        details: str | None = None,
        execution_id: int | None = None,
        execution_uuid: str | None = None,
        **kwargs: Any,
    ) -> None:
        self.status = status
        self.error = error
        self.details = details
        self.execution_id = execution_id
        self.execution_uuid = execution_uuid
        self.__dict__.update(kwargs)

    def to_dict(self) -> dict[str, Any]:
        """Return status payload dropping empty fields."""
        ret = self.__dict__.copy()
        for key, value in list(ret.items()):
            if value is None:
                del ret[key]
        return ret


class Base(DeclarativeBase):
    """Base class for ORM models."""


_LOCK = threading.RLock()


class Token(Base):
    """Authentication token persisted in the internal database."""

    __tablename__ = "tokens"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    token: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    user: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), default=_utcnow, nullable=False)
    expires_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True), nullable=True)

    __table_args__ = (Index("idx_token", "token"), {"sqlite_autoincrement": True})

    def is_valid(self) -> bool:
        """Check if the token is still valid according to ``expires_at``."""
        if self.expires_at is None:
            return True
        return _utcnow() < self.expires_at

    @staticmethod
    def create_token(user: str, expires_at: datetime.datetime | None = None) -> Token:
        """Create a token for user or return the still-valid existing one."""
        try:
            with DB.get_engine().begin() as conn:
                row = conn.execute(select(Token.__table__).where(Token.user == user)).mappings().first()
                if row is not None:
                    existing_token = Token(
                        id=int(row["id"]),
                        token=str(row["token"]),
                        user=str(row["user"]) if row["user"] is not None else None,
                        created_at=row["created_at"],
                        expires_at=row["expires_at"],
                    )
                    if existing_token.is_valid():
                        return existing_token

                new_token = Token(token=str(uuid.uuid4()), user=user, expires_at=expires_at)
                result = conn.execute(
                    insert(Token.__table__).values(
                        token=new_token.token,
                        user=new_token.user,
                        created_at=new_token.created_at,
                        expires_at=new_token.expires_at,
                    )
                )
                token_id = result.inserted_primary_key[0]
                if token_id is not None:
                    new_token.id = int(token_id)
                return new_token
        except SQLAlchemyError as exc:
            DB.log.error("Error creating or retrieving token: %s", exc)
            raise

    @staticmethod
    def get_token(user: str) -> Token | None:
        """Retrieve a valid token for user, if present."""
        try:
            with DB.get_engine().begin() as conn:
                row = conn.execute(select(Token.__table__).where(Token.user == user)).mappings().first()
                if row is None:
                    return None

                token = Token(
                    id=int(row["id"]),
                    token=str(row["token"]),
                    user=str(row["user"]) if row["user"] is not None else None,
                    created_at=row["created_at"],
                    expires_at=row["expires_at"],
                )
                if token.is_valid():
                    return token
            return None
        except SQLAlchemyError as exc:
            DB.log.error("Error retrieving token: %s", exc)
            raise

    def refresh(self) -> None:
        """Refresh token expiration by one day if currently valid."""
        if self.expires_at is None or self.expires_at <= _utcnow():
            return

        self.expires_at = _utcnow() + datetime.timedelta(days=1)
        try:
            with DB.get_engine().begin() as conn:
                conn.execute(update(Token.__table__).where(Token.id == self.id).values(expires_at=self.expires_at))
        except SQLAlchemyError as exc:
            DB.log.error("Error refreshing token: %s", exc)
            raise


class Execution(Base):
    """Execution lifecycle row used to track algorithm runs."""

    __tablename__ = "executions"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    uuid: Mapped[str] = mapped_column(String, default=lambda: str(uuid.uuid4()), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default=Status.SIM_PENDING)
    start_time: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, default=_utcnow)
    end_time: Mapped[datetime.datetime | None] = mapped_column(DateTime(True), nullable=True)
    params: Mapped[str] = mapped_column(String, nullable=False, default="{}")
    result: Mapped[str | None] = mapped_column(String, nullable=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    last_message: Mapped[str | None] = mapped_column(String, nullable=True)
    last_message_time: Mapped[datetime.datetime | None] = mapped_column(DateTime(True), nullable=True)

    __table_args__ = (Index("idx_start_time", "start_time"), {"sqlite_autoincrement": True})

    def update_progress(self, progress: float) -> None:
        """Update in-memory progress value."""
        self.progress = progress

    def get_duration(self) -> float:
        """Return elapsed duration in seconds."""
        end = self.end_time if self.end_time is not None else _utcnow()
        return (end - self.start_time).total_seconds()

    @staticmethod
    def create_execution(params: dict[str, Any] | None = None, raise_exception: bool = True) -> Execution | None:
        """Create an execution row and return its in-memory representation."""
        try:
            with DB.get_engine().begin() as conn:
                now = _utcnow()
                uid = str(uuid.uuid4())
                params_json = json.dumps(params or {})
                result = conn.execute(
                    insert(Execution.__table__).values(
                        uuid=uid,
                        status=Status.SIM_PENDING,
                        start_time=now,
                        params=params_json,
                        progress=0.0,
                    )
                )
                execution_id = result.inserted_primary_key[0]
                if execution_id is None:
                    raise RuntimeError("Failed to create execution: missing primary key")

                return Execution(
                    id=int(execution_id),
                    uuid=uid,
                    status=Status.SIM_PENDING,
                    start_time=now,
                    params=params_json,
                    progress=0.0,
                )
        except Exception as exc:
            DB.log.error("Error creating execution: %s", exc)
            if raise_exception:
                raise
            return None

    @staticmethod
    def set_execution_success(execution_id: int, raise_exception: bool = True) -> None:
        """Set execution status to completed."""
        Execution._set_status(execution_id, Status.SIM_COMPLETED, "success", raise_exception)

    @staticmethod
    def set_execution_failed(execution_id: int, ex: Exception | None = None, raise_exception: bool = True) -> None:
        """Set execution status to failed."""
        Execution._set_status(execution_id, Status.SIM_FAILED, str(ex), raise_exception)

    @staticmethod
    def _set_status(execution_id: int, status: str, result_value: str, raise_exception: bool = True) -> None:
        """Persist execution terminal status and result."""
        try:
            with _LOCK:
                with DB.get_engine().begin() as conn:
                    conn.execute(
                        update(Execution.__table__)
                        .where(Execution.id == execution_id)
                        .values(end_time=_utcnow(), status=status, result=result_value)
                    )
        except Exception as exc:
            DB.log.error("Error updating execution status: %s", exc)
            if raise_exception:
                raise

    @staticmethod
    def set_progress(
        execution_id: int,
        progress: float,
        message: str | None = None,
        raise_exception: bool = True,
    ) -> None:
        """Persist progress and optional status message for an execution."""
        try:
            with _LOCK:
                with DB.get_engine().begin() as conn:
                    conn.execute(
                        update(Execution.__table__)
                        .where(Execution.id == execution_id)
                        .values(progress=progress, last_message=message, last_message_time=_utcnow())
                    )
        except Exception as exc:
            DB.log.error("Error updating execution progress: %s", exc)
            if raise_exception:
                raise


class Log(Base):
    """Application log records persisted into the internal DB."""

    __tablename__ = "logs"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    log_level: Mapped[int] = mapped_column(Integer, nullable=False)
    log_levelname: Mapped[str] = mapped_column(String(16), nullable=False)
    log: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, default=_utcnow)
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    execution_id: Mapped[int | None] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), nullable=True)

    __table_args__ = (Index("idx_execution_id", "execution_id"), {"sqlite_autoincrement": True})


class DBHandler(logging.Handler):
    """Standard logging handler that stores logs in DB."""

    def __init__(self, engine: Engine) -> None:
        super().__init__()
        self.engine = engine

    def emit(self, record: logging.LogRecord) -> None:
        """Write one standard-library log record to the ``logs`` table."""
        try:
            with self.engine.begin() as conn:
                conn.execute(
                    insert(Log.__table__).values(
                        execution_id=getattr(record, "execution_id", None),
                        created_at=datetime.datetime.fromtimestamp(record.created, tz=datetime.timezone.utc),
                        log_level=record.levelno,
                        log_levelname=record.levelname,
                        created_by=record.name,
                        log=record.getMessage(),
                    )
                )
        except Exception as exc:
            logging.getLogger("amisim.database.DBHandler").error("Failed to log to DB: %s", exc)


class DB:
    """Shared database facade used by the AMISim runtime."""

    _engine: Engine | None = None
    _session_factory: scoped_session[Session] | None = None
    _schema: str | None = None
    log = logging.getLogger("amisim.database")

    @staticmethod
    def _supports_schema(database_url: str) -> bool:
        """Return whether the configured backend supports named schemas."""
        return not database_url.startswith("sqlite")

    @staticmethod
    def _apply_schema(schema: str | None, database_url: str) -> None:
        """Apply target schema to ORM tables when supported by the backend."""
        normalized_schema = (schema or "").strip() or None
        if normalized_schema is not None and not DB._supports_schema(database_url):
            DB.log.warning("Database backend does not support named schemas; ignoring schema=%s", normalized_schema)
            normalized_schema = None

        DB._schema = normalized_schema
        for table in Base.metadata.tables.values():
            table.schema = normalized_schema

    @staticmethod
    def _build_engine(database_url: str) -> Engine:
        """Build SQLAlchemy engine with safe defaults."""
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        engine = create_engine(database_url, echo=False, pool_pre_ping=True, connect_args=connect_args)

        if database_url.startswith("sqlite"):
            @event.listens_for(engine, "connect")
            def set_sqlite_pragma(dbapi_connection: Any, _connection_record: Any) -> None:
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL;")
                cursor.execute("PRAGMA foreign_keys=ON;")
                cursor.close()

        return engine

    @staticmethod
    def init_db(database_url: str, schema: str | None = None) -> None:
        """Initialize internal database and create required schema."""
        if not database_url.strip():
            raise ValueError("database_url cannot be empty")

        DB._apply_schema(schema=schema, database_url=database_url)
        DB._engine = DB._build_engine(database_url)
        DB._session_factory = scoped_session(sessionmaker(bind=DB._engine, autoflush=True, expire_on_commit=False))

        try:
            Base.metadata.create_all(DB._engine)
            DB.log.info("Database initialized successfully")
        except SQLAlchemyError as exc:
            DB.log.error("Error initializing database: %s", exc)
            raise

    @staticmethod
    def open_db(database_url: str, schema: str | None = None) -> None:
        """Open an existing internal database without creating schema."""
        if not database_url.strip():
            raise ValueError("database_url cannot be empty")

        DB._apply_schema(schema=schema, database_url=database_url)
        DB._engine = DB._build_engine(database_url)
        DB._session_factory = scoped_session(sessionmaker(bind=DB._engine, autoflush=False, expire_on_commit=False))
        DB.log.info("Database opened successfully")

    @staticmethod
    def is_initialized() -> bool:
        """Return whether the DB engine has been initialized."""
        return DB._engine is not None

    @staticmethod
    def get_engine() -> Engine:
        """Return current SQLAlchemy engine or raise if uninitialized."""
        if DB._engine is None:
            raise RuntimeError("Database engine is not initialized")
        return DB._engine

    @staticmethod
    def get_session() -> Session:
        """Create a new ORM session bound to the configured engine."""
        if DB._session_factory is None:
            raise RuntimeError("Database session factory is not initialized")
        return DB._session_factory()

    @staticmethod
    def write_log(
        *,
        level_no: int,
        level_name: str,
        message: str,
        created_by: str,
        execution_id: int | None = None,
        created_at: datetime.datetime | None = None,
    ) -> None:
        """Persist a log row when DB is initialized.

        The method is intentionally best-effort and should not raise on logging
        failures to avoid cascading runtime errors.
        """
        if DB._engine is None:
            return

        try:
            with DB._engine.begin() as conn:
                conn.execute(
                    insert(Log.__table__).values(
                        execution_id=execution_id,
                        created_at=created_at or _utcnow(),
                        log_level=level_no,
                        log_levelname=level_name,
                        created_by=created_by,
                        log=message,
                    )
                )
        except Exception as exc:
            logging.getLogger("amisim.database.DB").debug("Failed to write log row to DB: %s", exc)

    @staticmethod
    def clean_db(
        *,
        what: str = "all",
        cutoff: datetime.datetime | None = None,
        include_pending_executions: bool = False,
        include_active_tokens: bool = False,
        checkpoint_truncate: bool = True,
        vacuum: bool = True,
    ) -> dict[str, int]:
        """Delete records from internal tables according to cleanup criteria.

        :param what: Cleanup target: all, logs, tokens, executions.
        :param cutoff: Optional cutoff instant used for time-based pruning.
        :param include_pending_executions: If True, also remove pending executions.
        :param include_active_tokens: If True, also remove tokens that are not expired.
        :param checkpoint_truncate: If True, run SQLite ``wal_checkpoint(TRUNCATE)``.
        :param vacuum: If True, run SQLite ``VACUUM``.
        :return: Deleted rows count per target table.
        :raises ValueError: If ``what`` has an unsupported value.
        """
        normalized_what = what.strip().lower()
        targets_map = {
            "all": {"logs", "tokens", "executions"},
            "logs": {"logs"},
            "tokens": {"tokens"},
            "executions": {"executions"},
        }
        if normalized_what not in targets_map:
            raise ValueError(f"Unsupported clean target: {what!r}")

        deleted = {"logs": 0, "tokens": 0, "executions": 0}
        targets = targets_map[normalized_what]
        now = _utcnow()
        engine = DB.get_engine()

        with engine.begin() as conn:
            if "logs" in targets:
                logs_stmt = delete(Log.__table__)
                if cutoff is not None:
                    logs_stmt = logs_stmt.where(Log.created_at <= cutoff)
                result = conn.execute(logs_stmt)
                deleted["logs"] = int(result.rowcount or 0)

            if "tokens" in targets:
                if include_active_tokens:
                    tokens_stmt = delete(Token.__table__)
                else:
                    tokens_stmt = delete(Token.__table__).where(
                        and_(Token.expires_at.is_not(None), Token.expires_at <= now)
                    )
                result = conn.execute(tokens_stmt)
                deleted["tokens"] = int(result.rowcount or 0)

            if "executions" in targets:
                non_pending = Execution.status != Status.SIM_PENDING
                pending = Execution.status == Status.SIM_PENDING

                execution_stmt = delete(Execution.__table__)
                if cutoff is None:
                    if not include_pending_executions:
                        execution_stmt = execution_stmt.where(non_pending)
                else:
                    non_pending_filter = and_(
                        non_pending,
                        Execution.end_time.is_not(None),
                        Execution.end_time <= cutoff,
                    )
                    if include_pending_executions:
                        pending_filter = and_(pending, Execution.start_time <= cutoff)
                        execution_stmt = execution_stmt.where(or_(non_pending_filter, pending_filter))
                    else:
                        execution_stmt = execution_stmt.where(non_pending_filter)

                result = conn.execute(execution_stmt)
                deleted["executions"] = int(result.rowcount or 0)

        if checkpoint_truncate or vacuum:
            if engine.dialect.name != "sqlite":
                DB.log.warning(
                    "SQLite maintenance requested on non-SQLite backend: checkpoint_truncate=%s vacuum=%s",
                    checkpoint_truncate,
                    vacuum,
                )
                return deleted

            with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                if checkpoint_truncate:
                    conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
                if vacuum:
                    conn.exec_driver_sql("VACUUM")

        return deleted
