"""
Database engine, session factory, FastAPI dependency.
"""
import os
import logging
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger("movie_rec.db")

# ==============================
# PATHS
# ==============================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR}/movies.db")
IS_SQLITE = DATABASE_URL.startswith("sqlite")

# ==============================
# ENGINE
# ==============================
_engine_kwargs = {
    "pool_pre_ping": True,
    "future": True,
}

if IS_SQLITE:
    # check_same_thread=False нужен, чтобы FastAPI-воркеры могли
    # переиспользовать соединения между потоками.
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **_engine_kwargs)

# SQLite-specific pragmas
if IS_SQLITE:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA cache_size=-64000")  # 64 MB
        cursor.close()

# ==============================
# SESSION
# ==============================
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,
)


# ==============================
# FASTAPI DEPENDENCY
# ==============================
def get_db() -> Iterator:
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ==============================
# UTILS
# ==============================
def healthcheck() -> dict:
    try:
        db = SessionLocal()
        db.execute("SELECT 1")
        db.close()
        return {"status": "ok", "url": DATABASE_URL}
    except Exception as e:
        return {"status": "error", "error": str(e)}