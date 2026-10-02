from pathlib import Path
import json

import pytest

from web_data_pipeline.pipeline import run, write_outputs
from web_data_pipeline.records import normalize
from web_data_pipeline.sources import BOOKS_URL, QUOTES_URL, collect_books, handle_quote_route, parse_books, parse_quotes, require_approved_url
from web_data_pipeline.store import connect, current_records

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_books_parser_and_pagination():
    rows, next_url = parse_books(fixture("books_page1.html"), BOOKS_URL)
    assert len(rows) == 2
    assert rows[0]["title"] == "  Alpha   Book  "
    assert next_url == "https://books.toscrape.com/catalogue/page-2.html"
    second, end = parse_books(fixture("books_page2.html"), next_url)
    assert len(second) == 2 and end is None
    assert normalize(rows[0], "t").external_id == normalize(second[0], "t").external_id


def test_rendered_quote_parser_boundary():
    rows, next_url = parse_quotes(fixture("quotes_rendered.html"), QUOTES_URL)
    assert len(rows) == 1
    assert rows[0]["tags"] == ["example", "simple"]
    assert next_url == "https://quotes.toscrape.com/js/page/2/"
    assert normalize(rows[0], "t").title == "“A short quote.”"


def test_static_collector_follows_next_page(monkeypatch):
    requested = []

    class Response:
        def __init__(self, url, html):
            self.url = url
            self.text = html

        def raise_for_status(self):
            return None

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def get(self, url):
            requested.append(url)
            name = "books_page1.html" if len(requested) == 1 else "books_page2.html"
            return Response(url, fixture(name))

    monkeypatch.setattr("web_data_pipeline.sources.httpx.Client", Client)
    pages = []
    rows = collect_books(2, pages.append)
    assert len(rows) == 4
    assert requested == [BOOKS_URL, "https://books.toscrape.com/catalogue/page-2.html"]
    assert pages == ["books", "books"]


def test_pagination_rejects_unapproved_site():
    with pytest.raises(ValueError, match="outside approved source"):
        require_approved_url("https://unrelated.example/page/2/", "books.toscrape.com")


def test_static_collector_does_not_fetch_unapproved_next(monkeypatch):
    requested = []

    class Response:
        url = BOOKS_URL
        text = fixture("books_page1.html").replace("catalogue/page-2.html", "https://unrelated.example/")

        def raise_for_status(self):
            return None

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def get(self, url):
            requested.append(url)
            return Response()

    monkeypatch.setattr("web_data_pipeline.sources.httpx.Client", Client)
    with pytest.raises(ValueError, match="outside approved source"):
        collect_books(2, lambda source: None)
    assert requested == [BOOKS_URL]


def test_normalization_hash_ignores_collection_time():
    raw = parse_books(fixture("books_page1.html"), BOOKS_URL)[0][0]
    first = normalize(raw, "time-one")
    second = normalize({**raw, "title": "Alpha Book", "availability": "In stock"}, "time-two")
    assert first.numeric_value == 12.30 and first.rating == 3
    assert first.content_hash == second.content_hash
    assert first.collected_at != second.collected_at


@pytest.mark.parametrize("field,value,reason", [
    ("source_url", "", "identity"), ("title", " ", "title/text"),
    ("price", "£oops", "price"), ("availability", "", "availability")])
def test_validation_rejects_bad_book(field, value, reason):
    raw = parse_books(fixture("books_page1.html"), BOOKS_URL)[0][0]
    with pytest.raises(ValueError, match=reason):
        normalize({**raw, field: value}, "t")


def test_quote_requires_author_identity():
    raw = parse_quotes(fixture("quotes_rendered.html"), QUOTES_URL)[0][0]
    with pytest.raises(ValueError, match="author/identity"):
        normalize({**raw, "author": ""}, "t")


def book(title="Alpha Book", price="£12.30"):
    return dict(source="books", page_url=BOOKS_URL, source_url="catalogue/alpha_1/index.html",
                title=title, price=price, availability="In stock", rating=3)


def quote(tags=None):
    return dict(source="quotes", page_url=QUOTES_URL, source_url=QUOTES_URL,
                title="A short quote", author="Example Writer", tags=tags or ["simple"])


def collector(rows, source):
    def collect(max_pages, on_page):
        for _ in range(max_pages):
            on_page(source)
        return rows
    return collect


def test_change_classifications_persistence_and_exports(tmp_path):
    output = tmp_path / "output"
    first = run(output, collectors={"books": collector([book(), book()], "books"),
                                    "quotes": collector([quote()], "quotes")})
    assert (first["new"], first["records_rejected"], first["records_accepted"]) == (2, 1, 2)
    assert first["rejection_reasons"][0]["reason"] == "duplicate deterministic key"
    second = run(output, collectors={"books": collector([book(price="£13.30")], "books"),
                                     "quotes": collector([quote(tags=["simple", "new"])], "quotes")})
    assert (second["changed"], second["new"], second["unchanged"], second["removed"]) == (2, 0, 0, 0)
    third = run(output, collectors={"books": collector([book(price="£13.30")], "books"),
                                    "quotes": collector([quote(tags=["simple", "new"])], "quotes")})
    assert third["unchanged"] == 2
    fourth = run(output, collectors={"books": collector([], "books"),
                                     "quotes": collector([quote(tags=["simple", "new"])], "quotes")})
    assert (fourth["removed"], fourth["unchanged"]) == (1, 1)
    assert {row["classification"] for row in __import__("csv").DictReader(
        (output / "changes.csv").open(encoding="utf-8-sig"))} == {"REMOVED", "UNCHANGED"}
    removed = next(row for row in __import__("csv").DictReader(
        (output / "changes.csv").open(encoding="utf-8-sig")) if row["classification"] == "REMOVED")
    assert removed["numeric_value"] == "13.3"
    latest = json.loads((output / "latest.json").read_text(encoding="utf-8"))
    assert len(latest) == 1 and latest[0]["source"] == "quotes"
    assert latest[0]["tags"] == ["new", "simple"]
    assert latest[0]["numeric_value"] is None
    with connect(output / "state.sqlite") as db:
        assert len(current_records(db)) == 1
        assert db.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 4


def test_source_failure_preserves_prior_snapshot(tmp_path):
    output = tmp_path / "output"
    run(output, collectors={"books": collector([book()], "books"),
                            "quotes": collector([quote()], "quotes")})

    def fail(max_pages, on_page):
        on_page("books")
        raise OSError("simulated fetch failure" + "x" * 1000)

    result = run(output, collectors={"books": fail, "quotes": collector([quote()], "quotes")})
    assert result["sources_succeeded"] == ["quotes"]
    assert result["errors"][0]["source"] == "books"
    assert result["errors"][0]["error"].startswith("OSError: simulated fetch failure")
    assert len(result["errors"][0]["error"]) == 300
    assert result["removed"] == 0 and result["unchanged"] == 1
    with connect(output / "state.sqlite") as db:
        assert {row["source"] for row in current_records(db)} == {"books", "quotes"}


def test_page_scope_cannot_silently_change(tmp_path):
    run(tmp_path, max_pages=2, collectors={"books": collector([book()], "books")})
    with pytest.raises(ValueError, match="page limit differs"):
        run(tmp_path, max_pages=3, collectors={"books": collector([book()], "books")})


def test_all_invalid_rows_do_not_remove_previous_state(tmp_path):
    run(tmp_path, collectors={"books": collector([book()], "books")})
    result = run(tmp_path, collectors={"books": collector([book(price="bad")], "books")})
    assert result["removed"] == 0 and result["records_rejected"] == 1
    assert result["sources_succeeded"] == []
    with connect(tmp_path / "state.sqlite") as db:
        assert len(current_records(db)) == 1


@pytest.mark.parametrize("prefix", ["=", "+", "-", "@"])
def test_csv_escapes_untrusted_formula_prefixes(tmp_path, prefix):
    raw = quote(tags=[prefix + "SUM(1,1)"])
    raw["title"] = prefix + "1+1"
    raw["author"] = prefix + "Author"
    record = normalize(raw, "fixed-time").data()
    write_outputs(tmp_path, [record], [{"classification": "NEW", **record}], {"run_id": 1},
                  [{"run_id": 1, "classification": "NEW", **record}])
    import csv
    for filename in ("latest.csv", "changes.csv", "change_history.csv"):
        with (tmp_path / filename).open(encoding="utf-8-sig", newline="") as handle:
            csv_row = next(csv.DictReader(handle))
        for field in ("title", "author", "tags"):
            assert csv_row[field].startswith("'" + prefix)
    json_row = json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))[0]
    assert json_row["title"] == prefix + "1+1"


def test_quote_navigation_blocks_external_redirect_before_browser_follows():
    class Request:
        url = QUOTES_URL

        def is_navigation_request(self):
            return True

    class Response:
        status = 302
        headers = {"location": "https://unrelated.example/"}

    class Route:
        request = Request()

        def __init__(self):
            self.calls = []

        def fetch(self, **kwargs):
            self.calls.append(("fetch", kwargs))
            return Response()

        def abort(self):
            self.calls.append(("abort", None))

        def fulfill(self, **kwargs):
            self.calls.append(("fulfill", kwargs))

    route = Route()
    handle_quote_route(route)
    assert route.calls == [("fetch", {"max_redirects": 0}), ("abort", None)]
    route.calls.clear()
    route.request.url = "https://unrelated.example/"
    handle_quote_route(route)
    assert route.calls == [("abort", None)]
    route.calls.clear()
    route.request.url = QUOTES_URL
    Response.status = 200
    handle_quote_route(route)
    assert route.calls[0] == ("fetch", {"max_redirects": 0})
    assert route.calls[1][0] == "fulfill"


def test_export_failure_keeps_prior_files_and_next_run_recovers(tmp_path, monkeypatch):
    output = tmp_path / "output"
    run(output, collectors={"books": collector([book()], "books")})
    old_json = (output / "latest.json").read_bytes()
    original_open = Path.open

    def fail_changes(self, *args, **kwargs):
        if self.name == "changes.csv":
            raise OSError("simulated export failure")
        return original_open(self, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", fail_changes)
        with pytest.raises(OSError, match="simulated export failure"):
            run(output, collectors={"books": collector([book(price="£13.30")], "books")})
    assert (output / "latest.json").read_bytes() == old_json
    with connect(output / "state.sqlite") as db:
        assert db.execute("SELECT classification FROM changes WHERE run_id = 2").fetchone()[0] == "CHANGED"
    recovered = run(output, collectors={"books": collector([book(price="£13.30")], "books")})
    assert recovered["unchanged"] == 1
    assert json.loads((output / "latest.json").read_text(encoding="utf-8"))[0]["numeric_value"] == 13.3
    import csv
    with (output / "change_history.csv").open(encoding="utf-8-sig") as handle:
        history = list(csv.DictReader(handle))
    assert [(row["run_id"], row["classification"]) for row in history] == [
        ("1", "NEW"), ("2", "CHANGED"), ("3", "UNCHANGED")]
    assert history[1]["numeric_value"] == "13.3"


def test_unknown_output_files_are_not_overwritten(tmp_path):
    output = tmp_path / "candidate"
    output.mkdir()
    sentinel = output / "latest.csv"
    sentinel.write_text("owner data", encoding="utf-8")
    with pytest.raises(ValueError, match="existing export"):
        run(output, collectors={"books": collector([book()], "books")})
    assert sentinel.read_text(encoding="utf-8") == "owner data"
    assert not (output / "state.sqlite").exists()


def test_unrelated_sqlite_file_is_not_modified(tmp_path):
    import sqlite3
    db = sqlite3.connect(tmp_path / "state.sqlite")
    db.execute("CREATE TABLE owner_data (value TEXT)")
    db.commit()
    db.close()
    with pytest.raises(ValueError, match="not a pipeline database"):
        run(tmp_path, collectors={"books": collector([book()], "books")})
    db = sqlite3.connect(tmp_path / "state.sqlite")
    try:
        assert [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")] == ["owner_data"]
    finally:
        db.close()


def test_duplicate_variant_does_not_change_existing_record(tmp_path):
    run(tmp_path, collectors={"books": collector([book()], "books")})
    result = run(tmp_path, collectors={"books": collector([book(), book(price="£99.99")], "books")})
    assert (result["unchanged"], result["changed"], result["removed"], result["records_rejected"]) == (1, 0, 0, 1)
