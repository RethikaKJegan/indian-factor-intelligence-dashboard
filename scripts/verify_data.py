#!/usr/bin/env python3
"""Check whether the database is current. Safe to run any time; read-only.

    python scripts/verify_data.py            # human-readable, exit 0 if current
    python scripts/verify_data.py --json     # machine-readable
    python scripts/verify_data.py --strict   # exit 1 on medium severity too

Exit codes:
    0  current, or only a one-day lag that the refresh has not reached yet
    1  degraded -- something is behind but the pipeline can still run
    2  stale -- the daily refresh is not working
    3  the check itself could not run

This is the check to run before trusting anything the dashboard says about the
current month. It touches nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import data_freshness  # noqa: E402

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_DB = SCRIPT_DIR.parent / "data_input" / "processed_financial_data.sqlite"

EXIT_CODES = {"current": 0, "degraded": 1, "stale": 2, "unreadable": 3, "unknown": 3}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Path to the SQLite database")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    parser.add_argument(
        "--strict", action="store_true",
        help="Treat a medium-severity finding as a failure",
    )
    args = parser.parse_args()

    db = args.db if Path(args.db).exists() else None
    if db is None:
        print(f"Database not found at {args.db}", file=sys.stderr)
        print("Nothing to verify.", file=sys.stderr)
        return 3

    result = data_freshness.assess(db)
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(data_freshness.format_report(result))

    code = EXIT_CODES.get(result.get("status"), 3)
    if args.strict and result.get("status") == "degraded":
        code = 1
    return code


if __name__ == "__main__":
    raise SystemExit(main())
