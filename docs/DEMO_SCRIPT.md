# A short walkthrough

Show the terminal and the fixture outputs. Say that the data comes from public practice sites and that the controlled changes are synthetic.

| Screen | Narration |
| --- | --- |
| Books to Scrape and Quotes to Scrape JS | "This replaces repeatedly copying public listings into a spreadsheet. One source is plain HTML; the other renders with JavaScript." |
| Run the command in the repository's PowerShell window | "It revisits a fixed page scope, cleans the records, and compares them with the last known data." |
| `latest.csv` and `latest.json` | "These are the current known records in spreadsheet and structured formats." |
| Fixture `changes.csv` | "This controlled example shows a new record, a changed price, an unchanged quote, and an item absent from a complete fixture collection." |
| `run_summary.json` | "Missing pages or invalid rows are incomplete observations. The program preserves earlier records instead of calling them deleted." |
| `change_history.csv` | "Changes stay tied to their run. If an export fails, the next successful export includes the missed event." |

The command reads the two public sites and writes the dedicated local output directory. If live access fails, show the offline fixture files and say so. After an export failure or interruption, rerun with the same state directory before presenting the files.
