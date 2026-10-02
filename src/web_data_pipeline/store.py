"""SQLite state and per-run classifications."""
import json
import sqlite3
from pathlib import Path

from .records import Record


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.exists()
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    if existing:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if not {"runs", "records", "changes"}.issubset(tables):
            db.close()
            raise ValueError("existing state.sqlite is not a pipeline database")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT,
            max_pages INTEGER NOT NULL, summary_json TEXT
        );
        CREATE TABLE IF NOT EXISTS records (
            source TEXT NOT NULL, external_id TEXT NOT NULL,
            content_hash TEXT NOT NULL, record_json TEXT NOT NULL,
            PRIMARY KEY (source, external_id)
        );
        CREATE TABLE IF NOT EXISTS changes (
            run_id INTEGER NOT NULL, source TEXT NOT NULL, external_id TEXT NOT NULL,
            classification TEXT NOT NULL, record_json TEXT NOT NULL,
            PRIMARY KEY (run_id, source, external_id)
        );
    """)
    return db


def start_run(db: sqlite3.Connection, started_at: str, max_pages: int) -> int:
    prior = db.execute("SELECT max_pages FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    if prior and prior[0] != max_pages:
        raise ValueError("page limit differs from stored snapshot; use a separate output directory")
    cursor = db.execute("INSERT INTO runs(started_at, max_pages) VALUES (?, ?)", (started_at, max_pages))
    db.commit()
    return cursor.lastrowid


def apply_source(db: sqlite3.Connection, run_id: int, source: str, records: list[Record],
                 *, complete: bool) -> dict[str, int]:
    counts = {k: 0 for k in ("NEW", "CHANGED", "UNCHANGED", "REMOVED")}
    incoming = {record.external_id: record for record in records}
    with db:
        previous = {row["external_id"]: row for row in db.execute(
            "SELECT * FROM records WHERE source = ?", (source,))}
        for key, record in incoming.items():
            old = previous.get(key)
            classification = ("NEW" if old is None else
                              "UNCHANGED" if old["content_hash"] == record.content_hash else "CHANGED")
            counts[classification] += 1
            payload = json.dumps(record.data(), ensure_ascii=False, sort_keys=True)
            db.execute("INSERT OR REPLACE INTO records VALUES (?, ?, ?, ?)",
                       (source, key, record.content_hash, payload))
            db.execute("INSERT INTO changes VALUES (?, ?, ?, ?, ?)",
                       (run_id, source, key, classification, payload))
        for key in (previous.keys() - incoming.keys()) if complete else ():
            counts["REMOVED"] += 1
            db.execute("DELETE FROM records WHERE source = ? AND external_id = ?", (source, key))
            db.execute("INSERT INTO changes VALUES (?, ?, ?, ?, ?)",
                       (run_id, source, key, "REMOVED", previous[key]["record_json"]))
    return counts


def finish_run(db: sqlite3.Connection, run_id: int, finished_at: str, summary: dict) -> None:
    with db:
        db.execute("UPDATE runs SET finished_at = ?, summary_json = ? WHERE id = ?",
                   (finished_at, json.dumps(summary, ensure_ascii=False), run_id))


def current_records(db: sqlite3.Connection) -> list[dict]:
    return [json.loads(row[0]) for row in db.execute(
        "SELECT record_json FROM records ORDER BY source, external_id")]


def run_changes(db: sqlite3.Connection, run_id: int) -> list[dict]:
    return [dict(classification=row[0], **json.loads(row[1])) for row in db.execute(
        "SELECT classification, record_json FROM changes WHERE run_id = ? ORDER BY source, external_id", (run_id,))]


def change_history(db: sqlite3.Connection) -> list[dict]:
    # Include committed rows even if their run never reached export or finish_run.
    return [dict(run_id=row[0], classification=row[1], **json.loads(row[2])) for row in db.execute(
        "SELECT run_id, classification, record_json FROM changes ORDER BY run_id, source, external_id")]
