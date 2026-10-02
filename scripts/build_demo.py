"""Regenerate or verify the small fixture-only portfolio exports."""
import argparse
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from web_data_pipeline.pipeline import run
from web_data_pipeline.sources import BOOKS_URL, QUOTES_URL, parse_books, parse_quotes

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "docs" / "demo"
FILES = ("latest.csv", "latest.json", "changes.csv", "change_history.csv", "run_summary.json")


def fixture(name: str) -> str:
    return (ROOT / "tests" / "fixtures" / name).read_text(encoding="utf-8")


def collector(source: str, rows: list[dict]):
    def collect(max_pages, on_page):
        on_page(source)
        return rows
    return collect


def build(check: bool) -> None:
    first_books, _ = parse_books(fixture("books_page1.html"), BOOKS_URL)
    second_books, _ = parse_books(fixture("books_page2.html"), "https://books.toscrape.com/catalogue/page-2.html")
    quotes, _ = parse_quotes(fixture("quotes_rendered.html"), QUOTES_URL)
    with TemporaryDirectory() as temporary:
        output = Path(temporary)
        times = ["2026-01-01T00:00:00+00:00", "2026-01-01T00:00:01+00:00",
                 "2026-01-02T00:00:00+00:00", "2026-01-02T00:00:01+00:00"]
        with patch("web_data_pipeline.pipeline.now", side_effect=times), patch(
            "web_data_pipeline.pipeline.monotonic", side_effect=[0, 1, 2, 3]
        ):
            run(output, max_pages=1, collectors={"books": collector("books", first_books),
                                    "quotes": collector("quotes", quotes)})
            changed_books = [{**first_books[0], "price": first_books[0]["price"][0] + "13.30"},
                             second_books[1]]
            result = run(output, max_pages=1, collectors={"books": collector("books", changed_books),
                                            "quotes": collector("quotes", quotes)})
        actual = tuple(result[name] for name in ("new", "changed", "unchanged", "removed"))
        if actual != (1, 1, 1, 1):
            raise AssertionError(f"fixture change classifications: {actual}")
        if check:
            for name in FILES:
                if (TARGET / name).read_bytes() != (output / name).read_bytes():
                    raise AssertionError(f"demo file differs: {name}")
        else:
            TARGET.mkdir(parents=True, exist_ok=True)
            for name in FILES:
                (TARGET / name).write_bytes((output / name).read_bytes())
    print("Fixture demo: NEW 1, CHANGED 1, UNCHANGED 1, REMOVED 1; files " + ("verified" if check else "written"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="verify tracked demo files without changing them")
    build(parser.parse_args().check)
