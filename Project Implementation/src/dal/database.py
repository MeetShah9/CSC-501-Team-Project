"""Data layer: connection handling and script execution.

Every connection enables foreign-key enforcement (PRAGMA foreign_keys = ON),
which SQLite requires per connection (manual, section 4.3).
"""
import sqlite3
from pathlib import Path

from src.cmn.config import DB_PATH, SQL_DIR


def connect(db_path: Path | str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if conn.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        raise RuntimeError("SQLite build does not support foreign keys")
    return conn


def run_script(conn: sqlite3.Connection, script: Path | str) -> None:
    """Execute a .sql file (DDL or DML) on an open connection."""
    sql = Path(script).read_text(encoding="utf-8")
    conn.executescript(sql)


def create_schema(conn: sqlite3.Connection) -> None:
    run_script(conn, SQL_DIR / "01_schema.sql")
