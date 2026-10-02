"""Bounded run orchestration, source isolation, and client exports."""
import csv
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic

from .records import normalize
from .sources import collect_books, collect_quotes
from .store import apply_source, change_history, connect, current_records, finish_run, run_changes, start_run

RECORD_FIELDS = ["source", "source_url", "external_id", "title", "category", "numeric_value",
                 "availability", "rating", "author", "tags", "collected_at", "content_hash"]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_outputs(output: Path, records: list[dict], changes: list[dict], summary: dict,
                  history: list[dict] | None = None) -> None:
    output.mkdir(parents=True, exist_ok=True)
    # Render all files before replacing prior exports. The summary is published last.
    with TemporaryDirectory(prefix=".export-", dir=output) as staging_dir:
        staging = Path(staging_dir)
        (staging / "latest.json").write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for filename, rows, fields in (("latest.csv", records, RECORD_FIELDS),
                                       ("changes.csv", changes, ["classification", *RECORD_FIELDS]),
                                       ("change_history.csv", history or [], ["run_id", "classification", *RECORD_FIELDS])):
            with (staging / filename).open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                for row in rows:
                    cells = {**row, "tags": "; ".join(row["tags"])}
                    writer.writerow({key: csv_safe(value) for key, value in cells.items()})
        (staging / "run_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for filename in ("latest.json", "latest.csv", "changes.csv", "change_history.csv", "run_summary.json"):
            os.replace(staging / filename, output / filename)


def csv_safe(value):
    # Spreadsheet applications may evaluate untrusted cells starting with these characters.
    return "'" + value if isinstance(value, str) and value.startswith(("=", "+", "-", "@")) else value


@contextmanager
def output_lock(output: Path):
    # Windows releases the byte lock when this handle closes, including process exit.
    # Keep the file: removing it could let two processes lock different file objects.
    import msvcrt

    output.mkdir(parents=True, exist_ok=True)
    with (output / ".run.lock").open("a+b") as handle:
        if handle.seek(0, os.SEEK_END) == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise RuntimeError("another run is using this output directory; retry after it exits") from exc
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def run(output: Path, max_pages: int = 2, collectors: dict | None = None) -> dict:
    if max_pages < 1:
        raise ValueError("max_pages must be positive")
    with output_lock(output):
        return _run_locked(output, max_pages, collectors)


def _run_locked(output: Path, max_pages: int, collectors: dict | None) -> dict:
    if not (output / "state.sqlite").exists() and any(
        (output / name).exists() for name in ("latest.csv", "latest.json", "changes.csv", "change_history.csv", "run_summary.json")
    ):
        raise ValueError("output directory contains existing export files but no pipeline state")
    collectors = collectors or {"books": collect_books, "quotes": collect_quotes}
    started_at = now()
    timer = monotonic()
    summary = dict(started_at=started_at, sources_attempted=list(collectors), sources_succeeded=[],
                   pages_fetched={source: 0 for source in collectors}, records_extracted=0,
                   records_accepted=0, records_rejected=0, rejection_reasons=[],
                   new=0, changed=0, unchanged=0, removed=0, errors=[], warnings=[],
                   source_status={}, page_limit=max_pages)
    db = connect(output / "state.sqlite")
    try:
        run_id = start_run(db, started_at, max_pages)
        summary["run_id"] = run_id

        def on_page(source: str) -> None:
            summary["pages_fetched"][source] += 1

        for source, collect in collectors.items():
            try:
                rejected_before = summary["records_rejected"]
                raw_rows = collect(max_pages, on_page)
                summary["records_extracted"] += len(raw_rows)
                accepted = {}
                for index, raw in enumerate(raw_rows):
                    try:
                        record = normalize(raw, started_at)
                        if record.source != source:
                            raise ValueError("source mismatch")
                        if record.external_id in accepted:
                            raise ValueError("duplicate deterministic key")
                        accepted[record.external_id] = record
                    except (ValueError, TypeError) as exc:
                        summary["records_rejected"] += 1
                        summary["rejection_reasons"].append({"source": source, "index": index, "reason": str(exc)})
                if raw_rows and not accepted:
                    raise ValueError("all extracted records were rejected; previous snapshot preserved")
                reasons = []
                if summary["pages_fetched"][source] != max_pages:
                    reasons.append(f"collected {summary['pages_fetched'][source]} of {max_pages} required pages")
                if summary["records_rejected"] > rejected_before:
                    reasons.append("one or more extracted records were rejected")
                complete = not reasons
                summary["source_status"][source] = "complete" if complete else "incomplete"
                if reasons:
                    summary["warnings"].append({"source": source, "reason": "; ".join(reasons),
                                                "action": "unobserved prior records preserved; removals suppressed"})
                counts = apply_source(db, run_id, source, list(accepted.values()), complete=complete)
                summary["records_accepted"] += len(accepted)
                for label, count in counts.items():
                    summary[label.lower()] += count
                summary["sources_succeeded"].append(source)
            except Exception as exc:
                # Source-level failure leaves that source's previous SQLite snapshot intact.
                summary["errors"].append({"source": source, "error": f"{type(exc).__name__}: {exc}"[:300]})
                summary["source_status"][source] = "failed"
        summary["status"] = ("failed" if not summary["sources_succeeded"] else
                             "partial" if any(s != "complete" for s in summary["source_status"].values()) else "complete")
        summary["finished_at"] = now()
        summary["duration_seconds"] = round(monotonic() - timer, 3)
        finish_run(db, run_id, summary["finished_at"], summary)
        write_outputs(output, current_records(db), run_changes(db, run_id), summary, change_history(db))
        return summary
    finally:
        db.close()
