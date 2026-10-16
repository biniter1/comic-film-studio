from collections.abc import Generator
from pathlib import Path
from typing import Optional

from sqlalchemy import Engine, event
from sqlmodel import Session, SQLModel, create_engine

from app.config import settings


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record) -> None:  # type: ignore
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def get_engine(db_path: Optional[Path] = None) -> Engine:
    path = db_path or (settings.data_dir / "cfs.db")
    path.parent.mkdir(parents=True, exist_ok=True)
    # Using SQLite with check_same_thread=False for async FastAPI / multiple threads
    sqlite_url = f"sqlite:///{path.as_posix()}"
    return create_engine(
        sqlite_url,
        echo=False,
        connect_args={"check_same_thread": False},
    )


engine: Engine = get_engine()


def init_db(custom_engine: Optional[Engine] = None) -> None:
    eng = custom_engine or engine
    SQLModel.metadata.create_all(eng)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
