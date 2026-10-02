# Deterministic fixture demonstration

These five exports come from the small HTML fixtures in `tests/fixtures/`. They are synthetic portfolio examples, not a live-site data dump or a client dataset.

Run 1 stores Alpha Book, Beta Book, and one Example Writer quote. Run 2 changes Alpha's price, adds Gamma Book, keeps the quote, and omits Beta Book. The second run therefore reports **NEW 1 · CHANGED 1 · UNCHANGED 1 · REMOVED 1**. `latest.*` contains the three current records; `changes.csv` also retains Beta's prior snapshot for the `REMOVED` row. `change_history.csv` includes both runs with their run identities.

From the repository root, `python scripts/build_demo.py --check` regenerates both runs in a temporary SQLite database and compares all five tracked exports byte for byte. Both fixture collectors explicitly cover a one-page scope; this is separate from the two-page live default. Timestamps and duration are fixed demonstration values for reproducibility, not measured live timings.
