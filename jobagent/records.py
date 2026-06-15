"""Keeps a persistent record of every job application attempt.

Stored in a local SQLite database (``data/applications.db``) so you always have
a searchable history, and can be exported to CSV for spreadsheets.
"""

from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import DATA_DIR

DB_PATH = DATA_DIR / "applications.db"


@dataclass
class Application:
    url: str
    company: str
    title: str
    status: str  # "submitted", "filled_pending_review", "skipped", "failed"
    notes: str = ""
    applied_at: str = ""
    id: int | None = None


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS applications (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                url        TEXT NOT NULL,
                company    TEXT,
                title      TEXT,
                status     TEXT NOT NULL,
                notes      TEXT,
                applied_at TEXT NOT NULL
            )
            """
        )


def already_applied(url: str) -> Application | None:
    """Return a prior successful application for this URL, if any."""
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM applications
            WHERE url = ? AND status IN ('submitted', 'filled_pending_review')
            ORDER BY applied_at DESC LIMIT 1
            """,
            (url,),
        ).fetchone()
    return _row_to_app(row) if row else None


def record(app: Application) -> int:
    init_db()
    applied_at = app.applied_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO applications (url, company, title, status, notes, applied_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (app.url, app.company, app.title, app.status, app.notes, applied_at),
        )
        return int(cur.lastrowid)


def list_all(limit: int | None = None) -> list[Application]:
    init_db()
    query = "SELECT * FROM applications ORDER BY applied_at DESC"
    if limit:
        query += f" LIMIT {int(limit)}"
    with _connect() as conn:
        rows = conn.execute(query).fetchall()
    return [_row_to_app(r) for r in rows]


def export_csv(path: Path) -> int:
    apps = list_all()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["id", "applied_at", "company", "title", "status", "url", "notes"])
        for a in apps:
            writer.writerow([a.id, a.applied_at, a.company, a.title, a.status, a.url, a.notes])
    return len(apps)


def _row_to_app(row: sqlite3.Row) -> Application:
    return Application(
        id=row["id"],
        url=row["url"],
        company=row["company"] or "",
        title=row["title"] or "",
        status=row["status"],
        notes=row["notes"] or "",
        applied_at=row["applied_at"],
    )
