"""Observation completeness and delivery regressions using the actual pipeline."""
import csv
from contextlib import closing
import json
from pathlib import Path
import subprocess
import sys

import pytest

from web_data_pipeline.pipeline import run
from web_data_pipeline.sources import BOOKS_URL, QUOTES_URL, collect_books, parse_books, parse_quotes
from web_data_pipeline.store import connect, current_records

FIXTURE = Path(__file__).parent / "fixtures" / "books_page1.html"


def books():
    return parse_books(FIXTURE.read_text(encoding="utf-8"), BOOKS_URL)[0]


def collector(rows, pages=2):
    def collect(limit, on_page):
        for _ in range(pages):
            on_page("books")
        return rows
    return collect


@pytest.mark.parametrize("case", ["invalid", "pagination", "business_markup"])
def test_incomplete_observation_preserves_missing_record(tmp_path, case):
    original = books()
    run(tmp_path, collectors={"books": collector(original)})
    pages = 2
    if case == "invalid":
        observed = [original[0], {**original[1], "price": "bad"}]
    elif case == "pagination":
        observed, pages = [original[0]], 1
    else:
        html = FIXTURE.read_text(encoding="utf-8").replace(
            "instock availability", "soldout availability", 1)
        observed = parse_books(html, BOOKS_URL)[0]
    # Valid observations can advance even though the source is incomplete.
    observed = [{**row, "price": "£13.30"} if row["title"] == original[0]["title"]
                and case != "business_markup" else row for row in observed]
    summary = run(tmp_path, collectors={"books": collector(observed, pages)})
    assert summary["removed"] == 0
    assert summary["source_status"]["books"] == "incomplete"
    assert summary["status"] == "partial"
    assert summary["warnings"][0]["source"] == "books"
    with closing(connect(tmp_path / "state.sqlite")) as db:
        snapshot = {row["title"]: row for row in current_records(db)}
    assert set(snapshot) == {"Alpha Book", "Beta Book"}
    if case != "business_markup":
        assert summary["changed"] == 1
        assert snapshot["Alpha Book"]["numeric_value"] == 13.3
        assert snapshot["Beta Book"]["numeric_value"] == 20.0
    else:
        assert snapshot["Alpha Book"]["numeric_value"] == 12.3
    assert json.loads((tmp_path / "run_summary.json").read_text())["status"] == "partial"


def test_complete_observation_can_remove_and_add(tmp_path):
    original = books()
    run(tmp_path, collectors={"books": collector(original)})
    added = {**original[1], "source_url": "catalogue/gamma_3/index.html", "title": "Gamma"}
    result = run(tmp_path, collectors={"books": collector([original[0], added])})
    assert result["source_status"] == {"books": "complete"}
    assert (result["new"], result["unchanged"], result["removed"]) == (1, 1, 1)
    snapshot = json.loads((tmp_path / "latest.json").read_text())
    assert {row["title"] for row in snapshot} == {"Alpha Book", "Gamma"}


def test_actual_collector_missing_next_link_preserves_prior_scope(tmp_path, monkeypatch):
    # Seed a complete two-page scope, then remove the real parser's next link.
    original = books()
    run(tmp_path, collectors={"books": collector(original)})
    html = FIXTURE.read_text(encoding="utf-8")
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    soup.select("ol.row > li")[1].decompose()
    soup.select_one("li.next").decompose()

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, url):
            import httpx
            return httpx.Response(200, text=str(soup), request=httpx.Request("GET", url))

    monkeypatch.setattr("web_data_pipeline.sources.httpx.Client", Client)
    result = run(tmp_path, collectors={"books": collect_books})
    assert result["pages_fetched"] == {"books": 1}
    assert result["source_status"] == {"books": "incomplete"}
    assert result["removed"] == 0
    assert len(json.loads((tmp_path / "latest.json").read_text())) == 2


@pytest.mark.parametrize("source", ["books", "quotes"])
def test_parser_refuses_partially_unrecognized_cards(source):
    if source == "books":
        html = FIXTURE.read_text(encoding="utf-8").replace("product_pod", "new_card", 1)
        parse = lambda: parse_books(html, BOOKS_URL)
    else:
        html = (FIXTURE.parent / "quotes_rendered.html").read_text(encoding="utf-8")
        html += html.replace('class="quote"', 'class="new_card"')
        parse = lambda: parse_quotes(html, QUOTES_URL)
    with pytest.raises(ValueError, match="count mismatch"):
        parse()


@pytest.mark.parametrize("status,expected_exit", [("complete", 0), ("partial", 2), ("failed", 1)])
def test_cli_collection_status_exit(tmp_path, monkeypatch, capsys, status, expected_exit):
    from web_data_pipeline import __main__ as cli
    monkeypatch.setattr(sys, "argv", ["web_data_pipeline", "run", "--output", str(tmp_path)])

    def failed(limit, on_page):
        raise OSError("source unavailable")

    collect = (failed if status == "failed" else
               collector(books(), pages=1 if status == "partial" else 2))
    monkeypatch.setattr(cli, "run", lambda output, pages: run(output, pages, {"books": collect}))
    if expected_exit:
        with pytest.raises(SystemExit) as result:
            cli.main()
        assert result.value.code == expected_exit
    else:
        cli.main()
    assert json.loads(capsys.readouterr().out)["status"] == status


def test_replace_failure_recovers_committed_history(tmp_path, monkeypatch):
    original = books()[:1]
    run(tmp_path, collectors={"books": collector(original)})
    changed = [{**original[0], "price": "£13.30"}]
    import os
    replace = os.replace

    def locked(src, dst):
        if Path(dst).name == "changes.csv":
            raise PermissionError("simulated Windows sharing violation")
        return replace(src, dst)

    with monkeypatch.context() as patch:
        patch.setattr("web_data_pipeline.pipeline.os.replace", locked)
        with pytest.raises(PermissionError, match="sharing violation"):
            run(tmp_path, collectors={"books": collector(changed)})
    with closing(connect(tmp_path / "state.sqlite")) as db:
        assert db.execute("SELECT classification FROM changes WHERE run_id=2").fetchone()[0] == "CHANGED"
        assert current_records(db)[0]["numeric_value"] == 13.3
    result = run(tmp_path, collectors={"books": collector(changed)})
    assert result["unchanged"] == 1
    with (tmp_path / "change_history.csv").open(encoding="utf-8-sig") as handle:
        history = list(csv.DictReader(handle))
    assert [(row["run_id"], row["classification"]) for row in history] == [
        ("1", "NEW"), ("2", "CHANGED"), ("3", "UNCHANGED")]
    assert history[1]["numeric_value"] == "13.3"


def test_real_windows_open_csv_recovers_history(tmp_path):
    original = books()[:1]
    run(tmp_path, collectors={"books": collector(original)})
    changed = [{**original[0], "price": "£13.30"}]
    with (tmp_path / "changes.csv").open("rb"):
        with pytest.raises(PermissionError) as failure:
            run(tmp_path, collectors={"books": collector(changed)})
    # MoveFileEx may report access denied or sharing violation for the held file.
    assert failure.value.winerror in {5, 32}
    assert failure.value.filename2 == str(tmp_path / "changes.csv")
    run(tmp_path, collectors={"books": collector(changed)})
    with (tmp_path / "change_history.csv").open(encoding="utf-8-sig") as handle:
        missed = [row for row in csv.DictReader(handle) if row["run_id"] == "2"]
    assert len(missed) == 1
    assert (missed[0]["classification"], missed[0]["numeric_value"]) == ("CHANGED", "13.3")


def test_committed_event_survives_unfinished_run(tmp_path, monkeypatch):
    original = books()[:1]
    run(tmp_path, collectors={"books": collector(original)})
    changed = [{**original[0], "price": "£13.30"}]

    def interrupted(*args):
        raise OSError("interrupted after state commit, before run summary")

    with monkeypatch.context() as patch:
        patch.setattr("web_data_pipeline.pipeline.finish_run", interrupted)
        with pytest.raises(OSError, match="after state commit"):
            run(tmp_path, collectors={"books": collector(changed)})
    with closing(connect(tmp_path / "state.sqlite")) as db:
        assert db.execute("SELECT summary_json FROM runs WHERE id=2").fetchone()[0] is None
    run(tmp_path, collectors={"books": collector(changed)})
    with (tmp_path / "change_history.csv").open(encoding="utf-8-sig") as handle:
        missed = [row for row in csv.DictReader(handle) if row["run_id"] == "2"]
    assert missed[0]["classification"] == "CHANGED"


def test_process_exit_releases_lock(tmp_path):
    script = """
import os, sys
from pathlib import Path
from web_data_pipeline.pipeline import output_lock
with output_lock(Path(sys.argv[1])):
    os._exit(7)
"""
    process = subprocess.run([sys.executable, "-c", script, str(tmp_path)], timeout=15)
    assert process.returncode == 7
    assert run(tmp_path, collectors={"books": collector(books())})["status"] == "complete"


def test_second_process_rejected_during_export(tmp_path, monkeypatch):
    original = books()[:1]
    run(tmp_path, collectors={"books": collector(original)})
    import os
    replace = os.replace
    attempted = []

    def interleave(src, dst):
        replace(src, dst)
        if Path(dst).name == "latest.json":
            script = """
import sys
from pathlib import Path
from web_data_pipeline.pipeline import run
def collector(limit, on_page):
    raise AssertionError('second collector must not start')
try:
    run(Path(sys.argv[1]), collectors={'books': collector})
except RuntimeError as exc:
    assert 'another run' in str(exc), str(exc)
    print('second run rejected')
else:
    raise AssertionError('second run must be rejected')
"""
            process = subprocess.run([sys.executable, "-c", script, str(tmp_path)],
                                     capture_output=True, text=True, timeout=15)
            assert process.returncode == 0, process.stdout + process.stderr
            assert "second run rejected" in process.stdout
            attempted.append(True)

    monkeypatch.setattr("web_data_pipeline.pipeline.os.replace", interleave)
    run(tmp_path, collectors={"books": collector([{**original[0], "price": "£13.30"}])})
    assert attempted == [True]
    assert json.loads((tmp_path / "latest.json").read_text())[0]["numeric_value"] == 13.3
    with (tmp_path / "latest.csv").open(encoding="utf-8-sig") as handle:
        assert next(csv.DictReader(handle))["numeric_value"] == "13.3"
    with closing(connect(tmp_path / "state.sqlite")) as db:
        assert db.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 2
    # The operating system releases the lock after normal exit and after failure.
    monkeypatch.setattr("web_data_pipeline.pipeline.os.replace", replace)
    assert run(tmp_path, collectors={"books": collector(original)})["run_id"] == 3
