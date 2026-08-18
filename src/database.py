from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine, inspect
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


class SchemaDriftError(RuntimeError):
    """Bảng đã tồn tại trong DB nhưng thiếu cột so với ORM model."""


def _check_schema_drift(engine: Engine) -> None:
    """Phát hiện bảng cũ thiếu cột so với model hiện tại.

    `create_all` chỉ chạy `CREATE TABLE IF NOT EXISTS` - bảng đã tồn tại thì nó BỎ QUA hoàn toàn,
    không thêm cột mới. Khi model thêm cột (vd `users.username`), file SQLite cũ vẫn giữ schema cũ và
    mọi truy vấn sẽ chết bằng `OperationalError: no such column` ở tầng route, hiện ra ngoài thành
    HTTP 500 với body plain-text - rất khó lần ra nguyên nhân.

    Kiểm tra ngay lúc khởi động để báo lỗi đúng chỗ, kèm hướng xử lý.
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    problems: list[str] = []

    for table_name, table in Base.metadata.tables.items():
        if table_name not in existing_tables:
            continue  # create_all vừa tạo mới -> chắc chắn đúng schema
        actual = {column["name"] for column in inspector.get_columns(table_name)}
        missing = [column.name for column in table.columns if column.name not in actual]
        if missing:
            problems.append(f"  - {table_name}: thiếu cột {', '.join(missing)}")

    if problems:
        raise SchemaDriftError(
            "Schema database đang cũ hơn ORM model:\n"
            + "\n".join(problems)
            + "\n\nDự án chưa dùng migration tool. Với SQLite ở môi trường dev, xoá (hoặc đổi tên)"
            " file database rồi chạy lại để tạo mới:\n"
            "  Remove-Item data/app.db        # PowerShell\n"
            "  rm data/app.db                 # bash\n"
            "Dữ liệu trong file cũ sẽ mất - sao lưu trước nếu cần giữ."
        )


def _apply_additive_sqlite_migrations(engine: Engine) -> None:
    """Apply safe nullable-column additions for local SQLite development databases."""
    if not engine.url.drivername.startswith("sqlite"):
        return
    additions = {
        "address": "VARCHAR(240)",
        "emergency_contact_name": "VARCHAR(120)",
        "emergency_contact_relationship": "VARCHAR(80)",
        "emergency_contact_phone": "VARCHAR(32)",
    }
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("users")}
    with engine.begin() as connection:
        for column, sql_type in additions.items():
            if column not in columns:
                connection.exec_driver_sql(f"ALTER TABLE users ADD COLUMN {column} {sql_type}")


def create_tables() -> None:
    from src.models import case_record, password_reset, user  # noqa: F401 - registers ORM models with Base metadata

    engine = _engine or configure_database()
    Base.metadata.create_all(bind=engine)
    _apply_additive_sqlite_migrations(engine)
    _check_schema_drift(engine)


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


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Session cho code chạy NGOÀI phạm vi một request (các store singleton).

    `get_db_session` là dependency của FastAPI: nó không commit và để framework lo vòng đời. Store
    thì được gọi từ mọi nơi - kể cả threadpool của endpoint SSE và script CLI - nên cần một phạm vi
    tự đóng và tự commit. Rollback khi có exception là bắt buộc chứ không phải lịch sự: một case ghi
    dở dang là một case điều dưỡng nhìn thấy sai."""
    global _session_factory

    if _session_factory is None:
        configure_database()
        create_tables()
    assert _session_factory is not None

    session = _session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def dispose_database() -> None:
    global _engine, _session_factory, _database_url

    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
    _database_url = None
