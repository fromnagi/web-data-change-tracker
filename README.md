# Public Web Data & Change Tracking

Stop copying the same web listings into a spreadsheet every week. This small Python program revisits public pages, cleans their records, compares them with the last known data, and exports the current dataset plus a history of changes.

It demonstrates **Books to Scrape** (static book listings) and **Quotes to Scrape JS** (browser-rendered quotes). This is a synthetic portfolio demonstration, not commissioned client work. Development, tests and documentation used AI assistance.

| Result | Meaning |
| --- | --- |
| `NEW` | A validated record has an identity we have not stored before. |
| `CHANGED` | The same identity has different meaningful fields. |
| `UNCHANGED` | Its meaningful fields are the same; collection time does not count. |
| `REMOVED` | A stored identity is absent from a complete observation of the configured page scope. |

**A failed observation is not a deletion.** Fewer pages than configured, rejected rows, or a source error suppress removals for that source. Valid observations can still update its records; unobserved prior records stay in the current dataset with their original collection times. The summary identifies incomplete or failed sources, and the CLI reports partial success with exit code 2.

## What comes out

Files share a dedicated local output directory:

| File | Use |
| --- | --- |
| `latest.csv`, `latest.json` | Current known records, including prior records retained during incomplete collection. |
| `changes.csv` | This run's classifications, including the previous values for removed records. |
| `change_history.csv` | All committed classifications across runs, identified by `run_id`. |
| `run_summary.json` | Collection status, page counts, rejected rows, warnings, errors, and this run's change counts. |
| `state.sqlite` | Persistent records, run summaries, and change history. |

If export fails, close any spreadsheet holding an output file and rerun the same command. The next successful export rebuilds `change_history.csv` from SQLite, including the missed change even if the new run calls that record `UNCHANGED`. This is local file generation; it does not track whether a person received a file. History is cumulative, so consumers can use `(run_id, source, external_id)` to identify an event.

See the [fixture outputs](docs/demo/README.md), [pipeline image](docs/assets/pipeline-overview.png), and [comparison image](docs/assets/change-detection-proof.png) for a quick example. The [implementation notes](docs/CASE_STUDY.md) explain the design.

## Run on Windows

Tested with Python 3.12 and PowerShell. In the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m web_data_pipeline run
```

Installation downloads Python packages and Chromium. The final command reads the two public practice sites and writes local `output/` files. Run it again to compare against the same state. Exit 0 means complete collection and successful export; exit 2 means partial collection with exported results; exit 1 means all sources failed or a run/export error occurred. After an interruption, rerun with the same directory to regenerate files and recover committed history.

The default scope is the first two pages of each source. `--output PATH` selects another dedicated directory; `--max-pages N` sets the scope for a new state. A different page limit requires a separate directory. A second concurrent run against the same directory is rejected before collection starts. Leave `.run.lock` in place; the operating system releases its lock when the process exits.

For the offline demo, run `python scripts/build_demo.py --check` after installation. [Test and live observations](docs/VALIDATION.md) are recorded separately.

## How it works and where it stops

Public pages → collect → parse and validate → compare in SQLite → current CSV/JSON and change history.

Books use the absolute product URL as identity. Quotes use normalized author and text, so editing quote text produces a new identity and, on a complete collection, a removal of the old one. `httpx` and Beautiful Soup handle books; Playwright Chromium renders quotes. CSV formula prefixes are escaped; JSON retains normalized text.

Completeness is deliberately conservative: every configured page must be collected, the source parser must return normally, and every extracted row must validate without a duplicate key. Even a natural early end is incomplete if it falls short of that page count. The parsers check the known listing/card structure; unknown markup changes still need source-specific maintenance. `REMOVED` means absent from this bounded listing scope, not proof that an item disappeared from the entire website.

Multiple file replacements are not one filesystem transaction. An export error can leave mixed files; treat that run as failed and rerun before using them. SQLite commits preserve the event history. Unrelated SQLite files and existing exports without pipeline state are refused.

Only these two practice sites are configured. Scheduling, alerts, cloud deployment, arbitrary websites, access-control bypass, and continuous production monitoring are outside this demonstration.
