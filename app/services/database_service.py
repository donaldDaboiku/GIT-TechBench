"""SQLite session history."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS diagnostic_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    computer_name TEXT,
    serial_number TEXT,
    technician_name TEXT,
    overall_status TEXT NOT NULL,
    results_json TEXT NOT NULL,
    identity_json TEXT,
    notes TEXT,
    repair_needed TEXT,
    parts_required TEXT,
    further_testing TEXT
);
"""

_EXTRA_COLUMNS = {
    "identity_json": "TEXT",
    "notes": "TEXT",
    "repair_needed": "TEXT",
    "parts_required": "TEXT",
    "further_testing": "TEXT",
}


class DatabaseService:
    """Local history store for diagnostic sessions."""

    def __init__(self, db_path: Path | None = None) -> None:
        root = Path(__file__).resolve().parents[2]
        self.db_path = db_path or (root / "database" / "techbench.db")

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        try:
            conn.executescript(SCHEMA)
            existing = {row[1] for row in conn.execute("PRAGMA table_info(diagnostic_sessions)")}
            for name, spec in _EXTRA_COLUMNS.items():
                if name not in existing:
                    conn.execute(f"ALTER TABLE diagnostic_sessions ADD COLUMN {name} {spec}")
            conn.commit()
        finally:
            conn.close()

    def save(self, session: dict[str, Any]) -> int:
        self.initialize()
        created = str(session.get("created_at") or datetime.now().isoformat(timespec="seconds"))
        tests = session.get("tests") or []
        identity = session.get("identity") or {}
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                """
                INSERT INTO diagnostic_sessions (
                    created_at, computer_name, serial_number, technician_name,
                    overall_status, results_json, identity_json, notes,
                    repair_needed, parts_required, further_testing
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    created,
                    str(session.get("computer_name") or ""),
                    str(session.get("serial_number") or ""),
                    str(session.get("technician_name") or ""),
                    str(session.get("overall_status") or "UNKNOWN"),
                    json.dumps(tests, ensure_ascii=False),
                    json.dumps(identity, ensure_ascii=False),
                    str(session.get("notes") or ""),
                    str(session.get("repair_needed") or ""),
                    str(session.get("parts_required") or ""),
                    str(session.get("further_testing") or ""),
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)
        finally:
            conn.close()

    def list_sessions(self, search: str = "") -> list[dict[str, Any]]:
        self.initialize()
        needle = f"%{search.strip()}%" if search.strip() else "%"
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT id, created_at, computer_name, serial_number, technician_name, overall_status
                FROM diagnostic_sessions
                WHERE computer_name LIKE ? OR serial_number LIKE ?
                ORDER BY id DESC
                """,
                (needle, needle),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get(self, session_id: int) -> dict[str, Any] | None:
        self.initialize()
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM diagnostic_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        data = dict(row)
        try:
            data["tests"] = json.loads(data.get("results_json") or "[]")
        except json.JSONDecodeError:
            data["tests"] = []
        try:
            data["identity"] = json.loads(data.get("identity_json") or "{}")
        except json.JSONDecodeError:
            data["identity"] = {}
        return data
