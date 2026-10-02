# Test and collection observations

## Offline checks

On Windows 11, Python 3.12.10, `python -m pytest -q` completed with **39 passed**. These tests use local fixtures; live availability is checked separately below.

The regressions in [test_integrity.py](../tests/test_integrity.py) check invalid rows, a missing next-page link through the actual book collector, availability markup drift, card structure mismatches, complete-scope removals, change-history recovery, CLI status, and overlapping processes. Existing tests still cover all four classifications, source failure isolation, page-limit protection, CSV formula escaping, and refusal of foreign state/output files.

| Reproduced before repair | Result after repair |
| --- | --- |
| One invalid price, early pagination, or missing availability each produced one false removal. | No removal; prior records remain. Valid observations can still change. |
| A committed changed price vanished from the next run's comparison after export failed. | The next successful cumulative history export includes that original `CHANGED` with its run identity. |
| Two overlapping exports both succeeded with JSON price 14.3 and CSV price 13.3. | A second process is refused while the first is publishing its files. |

Export recovery covers both injected write/replacement failures and an actual CSV held open on Windows. The held-file replacement raised `PermissionError` (Windows error 5); closing it allowed recovery. A committed event is also recovered when the run stops before storing its summary. A subprocess exiting while holding the output lock does not leave a stale operating-system lock.

`python scripts/build_demo.py --check` rebuilt the two fixture runs and byte-compared all five exports. The existing current-data and latest-change files stayed unchanged. The summary now declares its actual one-page fixture scope and collection status; cumulative history is an additional file. The fixed fixture times are demonstration inputs, not measured timings.

`python -m compileall -q src scripts tests` and `git diff --check` passed. Both updated portfolio images were rendered and visually inspected.

CLI status tests pass actual pipeline results through the command entry point for complete, partial, and failed collection. Formula-prefix cases check current CSV, this-run CSV, and cumulative history CSV; JSON keeps the original normalized text.

## Live observations

Two normal CLI executions used a new local output directory and the configured two-page scope. Both returned exit 0 with both sources complete, no rejected rows, no warnings, and no source errors.

| UTC start | Books pages | Quotes pages | Accepted | NEW | UNCHANGED | CHANGED / REMOVED |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 2026-10-01 15:29:31 | 2 | 2 | 60 | 60 | 0 | 0 / 0 |
| 2026-10-01 15:31:41 | 2 | 2 | 60 | 0 | 60 | 0 / 0 |

These observations show that both collection paths worked at those times. They do not demonstrate a live-site deletion or future availability. Failure and deletion behavior is checked with controlled offline inputs.

Environment: Python 3.12.10; httpx 0.28.1; Beautiful Soup 4.15.0; Playwright 1.63.0; pytest 8.4.2; Chromium 153.0.8010.12.

## Fresh environment

A new local clone of the baseline received the reviewed working-tree changes before the local commit. It used a separate virtual environment: editable installation with test dependencies, `pip check`, and `playwright install chromium` all completed successfully. The browser installation reused the available Chromium cache.

The full suite passed again with **39 passed**, the five-file fixture comparison passed, and compile checks passed. A normal CLI live run started at 2026-10-01 15:35:12 UTC and returned exit 0 with both sources complete. The Python and package versions matched those listed above; pip was 25.0.1. This checks Windows only, with package/browser caches available.

The final source changes were reviewed for snapshot preservation, atomic state/change commits, recovery of unfinished runs, and lock coverage from collection through export. No schema migration, scheduler, or external delivery service was added.

## Practical limits

Completeness means the configured page scope and known parser/validation checks passed. It is not full-site coverage or a guarantee against every future markup change. A natural early pagination end conservatively suppresses removals. SQLite run summaries describe collection; they are not delivery acknowledgements. A successful CLI exit confirms local export, not receipt by a person. Failed multi-file replacement can leave mixed exports until a successful rerun.
