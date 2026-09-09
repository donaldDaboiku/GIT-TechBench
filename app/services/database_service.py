"""SQLite session history.

Phase 5 implements persistence. Phase 1 only locates the database path
and documents the schema so later work does not invent a second store.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS diagnostic_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    computer_name TEXT,
    serial_number TEXT,
    technician_name TEXT,
    overall_status TEXT NOT NULL,
    results_json TEXT NOT NULL
);
"""


class DatabaseService:
    """Local history store. Not used by the UI until Phase 5."""

    def __init__(self, db_path: Path | None = None) -> None:
        root = Path(__file__).resolve().parents[2]
        self.db_path = db_path or (root / "database" / "techbench.db")

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(SCHEMA)
