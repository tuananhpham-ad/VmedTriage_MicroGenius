from collections.abc import Generator
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.config import get_settings


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None
_database_url: str | None = None


def _ensure_sqlite_directory(database_url: str) -> None:
    prefixes = ("sqlite:///", "sqlite+pysqlite:///")
    prefix = next((item for item in prefixes if database_url.startswith(item)), None)
    if prefix is None or database_url.endswith(":memory:"):
        return

    database_path = Path(database_url.removeprefix(prefix))
    if database_path.parent != Path("."):
        database_path.parent.mkdir(parents=True, exist_ok=True)


def configure_database(database_url: str | None = None) -> Engine:
    global _engine, _session_factory, _database_url

    resolved_url = database_url or get_settings().database_url
    if _engine is not None and _database_url == resolved_url:
        return _engine

    if _engine is not None:
        _engine.dispose()

    _ensure_sqlite_directory(resolved_url)
    engine_options: dict[str, object] = {"pool_pre_ping": True}
    if resolved_url.startswith("sqlite"):
        engine_options["connect_args"] = {"check_same_thread": False}
    if resolved_url.endswith(":memory:"):
        engine_options["poolclass"] = StaticPool

    _engine = create_engine(resolved_url, **engine_options)
    _session_factory = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    _database_url = resolved_url
    return _engine


def create_tables() -> None:
    from src.models import password_reset, user  # noqa: F401 - registers ORM models with Base metadata

    engine = _engine or configure_database()
    Base.metadata.create_all(bind=engine)


def get_db_session() -> Generator[Session, None, None]:
    global _session_factory

    if _session_factory is None:
        configure_database()
        create_tables()
    assert _session_factory is not None

    session = _session_factory()
    try:
        yield session
    finally:
        session.close()


def dispose_database() -> None:
    global _engine, _session_factory, _database_url

    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
    _database_url = None
