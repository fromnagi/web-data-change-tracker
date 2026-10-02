import argparse
import json
from pathlib import Path

from .pipeline import run


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect two public demo websites")
    parser.add_argument("command", choices=["run"])
    parser.add_argument("--output", type=Path, default=Path("output"))
    parser.add_argument("--max-pages", type=int, default=2)
    args = parser.parse_args()
    summary = run(args.output, args.max_pages)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if summary["status"] == "failed":
        raise SystemExit(1)
    if summary["status"] == "partial":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
