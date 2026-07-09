import sqlite3
from contextlib import contextmanager

from app.config import DB_PATH


def _row_factory(cursor, row):
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


@contextmanager
def get_connection():
    if not DB_PATH.exists():
        raise RuntimeError(
            f"Database not found at {DB_PATH}. Run `python preprocess.py` first."
        )
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = _row_factory
    conn.execute("PRAGMA query_only = ON")
    try:
        yield conn
    finally:
        conn.close()
