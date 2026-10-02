# Revisiting web listings without losing the changes

A recurring research task often starts with opening the same pages, copying prices or text, cleaning the spreadsheet, and comparing it with last week's file. This project puts that loop into a local command. Books to Scrape supplies ordinary HTML; Quotes to Scrape JS needs a rendered browser page. Both are public practice sites, and the example is synthetic portfolio work.

## One small pipeline

Each source collects its configured pages before updating SQLite. Book cards and rendered quote cards become normalized records. Required fields are validated, whitespace is collapsed, prices become numbers, and tags are sorted. Books use their product URL as identity. Quotes have no stable per-quote identifier, so author and text form their identity.

A content hash compares meaningful fields while ignoring collection time. SQLite stores the current known records and a classification for each observed record in each run. The exports provide a spreadsheet, structured JSON, this run's comparison, cumulative history, and a collection summary.

## Missing observations need care

A missing record can mean a deletion, a broken price field, an unexpected availability class, or a missing next-page link. Treating all of those as deletion would make the comparison misleading.

The program permits removals only when the fixed page scope was collected, the parser returned normally, and no extracted row was rejected. Otherwise it preserves unobserved prior records and explicitly marks the source incomplete. Valid records can still be new or changed. A source exception preserves that source's snapshot while the other source continues. Old records keep their old collection timestamps, so retained data is not presented as freshly observed.

Known card/container mismatches fail parsing rather than silently omit cards. These checks are specific to the two sample sites; they cannot identify every possible future markup change. A removal describes absence within the configured listing pages. Reordering an item beyond that boundary does not prove deletion from the entire site.

## State and files have different failure boundaries

SQLite can commit a changed price before Windows refuses to replace a CSV held open in a spreadsheet. A later collection then sees the same price as unchanged. Exporting only that later comparison would hide the original change from the delivered files.

`change_history.csv` solves this using the already stored per-run rows. Every successful export includes all committed classifications and their run identities, including rows from a failed export or interrupted run. `latest.*` remains the current snapshot, and `changes.csv` remains the latest comparison. The program does not claim exactly-once delivery to a person or service.

A Windows file lock covers collection, database updates, and file publication. A second process using the same output directory is refused. Files are rendered in a temporary directory before replacement, but a replacement failure can still leave a mixed file set. Close the blocking file and rerun; do not use exports from a failed command.

## Inspect the example

The [fixture demonstration](demo/README.md) shows all four classifications with controlled inputs. The [validation record](VALIDATION.md) separates offline regression tests from live site observations. No customer results or full-site monitoring are implied.
