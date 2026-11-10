"""SQLite connection + schema setup. The DB file is the single source of truth."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = REPO_ROOT / "data" / "clipper.db"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
SCHEMA_VERSION = 1


def db_path() -> Path:
    return Path(os.environ.get("CLIPPER_DB", DEFAULT_DB))


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = Path(path) if path else db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init(conn)
    return conn


def init(conn: sqlite3.Connection) -> None:
    """Create tables if missing. Idempotent; safe to call on every connect."""
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version >= SCHEMA_VERSION:
        return
    conn.executescript(SCHEMA_PATH.read_text())
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_ts(value: str | None) -> str | None:
    """Accept 'YYYY-MM-DD', 'YYYY-MM-DD HH:MM' or full ISO; return ISO UTC text.

    Naive times are treated as local time and converted to UTC.
    """
    if value is None:
        return None
    s = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError as e:
        raise ValueError(f"bad timestamp {value!r}; use YYYY-MM-DD or YYYY-MM-DD HH:MM") from e
    if dt.tzinfo is None:
        dt = dt.astimezone()  # assume local
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
