"""Populate `macro_monthly.monthly_fii_flow` / `monthly_dii_flow` from the scrape.

## The gap this closes

`macro_monthly` carried the FII and DII columns as empty for all 414 months,
and the JSON exporter published them as null with a note saying the database
columns were empty. That was true, and it was an ingestion gap rather than a
missing source: the scraped CSV carries `fii_net` and `dii_net` for every
trading day it covers.

## What it cannot do, stated plainly

The source file is named `fii-dii-history-full-...csv` and is not a full
history. It holds 158 trading days covering **April to July 2026 only** --
roughly nine month-ends out of the 414 the table spans. Filling it therefore
populates a small tail of the series and leaves the earlier years empty.

Those months are left null rather than back-filled, interpolated or carried
forward. A macro series that reads plausibly back to 2014 but was actually
synthesised would be worse than an obviously short one, and the regime model
has a coverage floor precisely so a thinly-populated feature cannot enter as if
it had a history.

## Safety

`regime_model.MIN_FEATURE_COVERAGE` is 0.10, and nine months of 153 is about
6 percent, so `fii_dii_trend` stays below the floor and is still dropped. The
model's inputs and every reported figure are unchanged by this script; it
populates two published columns that nothing currently consumes.

## Idempotent

A pure function of the source file: the same input always produces the same
table, so re-running is safe and cannot accumulate.

## Usage

    python scripts/repair_fii_dii.py [--source <csv>]

The source defaults to the scrape directory. If the file is absent the script
reports that and exits 0, because a colleague cloning the repository has no
`Downloads/data` folder and the pipeline must not fail without it.
"""
from __future__ import annotations

import argparse
import calendar
import csv
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import date, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data_input", "processed_financial_data.sqlite")
DEFAULT_SOURCE = os.path.join(
    os.path.expanduser("~"), "Downloads", "data",
    "FIIDII Flow Data", "fii-dii-history-full-mrchartist.csv",
)
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def parse_day(value: str):
    """Parse `22-Sep-2026`, the format the source uses.

    `datetime.strptime` with `%d-%b-%Y` is locale-dependent: it reads the
    month name in the running locale, so a machine set to a non-English locale
    rejects every row. The month names are mapped explicitly so the parse does
    not depend on the environment.
    """
    value = (value or "").strip()
    for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    parts = value.split("-")
    if len(parts) == 3 and parts[1][:3].title() in MONTHS:
        try:
            return date(int(parts[2]), MONTHS.index(parts[1][:3].title()) + 1, int(parts[0]))
        except ValueError:
            return None
    return None


def month_end(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}-{calendar.monthrange(d.year, d.month)[1]:02d}"


def load_flows(path: str):
    """Return {month_end: (fii_net_sum, dii_net_sum, days)}.

    Daily net flows are summed within the month, which is the conventional
    reading of "monthly FII net flow". Taking the last day instead would be a
    cumulative level rather than a flow, and would silently mix the two.
    """
    fii = defaultdict(float)
    dii = defaultdict(float)
    days = defaultdict(int)
    skipped = 0
    with open(path, newline="", encoding="utf-8", errors="ignore") as fh:
        for row in csv.DictReader(fh):
            d = parse_day(row.get("date", ""))
            if d is None:
                skipped += 1
                continue
            try:
                f = float(row.get("fii_net") or 0.0)
                i = float(row.get("dii_net") or 0.0)
            except (TypeError, ValueError):
                skipped += 1
                continue
            key = month_end(d)
            fii[key] += f
            dii[key] += i
            days[key] += 1
    return dict(fii), dict(dii), dict(days), skipped


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", default=DEFAULT_SOURCE)
    ap.add_argument("--db", default=DB)
    args = ap.parse_args()

    if not os.path.exists(args.source):
        print(f"source not present: {args.source}")
        print("  The scrape directory is not part of the repository. Nothing to do;")
        print("  this is not an error and must not fail a scheduled run.")
        return 0
    if not os.path.exists(args.db):
        print(f"database not found: {args.db}")
        return 1

    fii, dii, days, skipped = load_flows(args.source)
    if not fii:
        print("source parsed to zero usable rows; leaving the table untouched")
        return 0
    print(f"parsed {len(fii)} month(s) from {os.path.basename(args.source)}"
          + (f", {skipped} row(s) skipped" if skipped else ""))

    conn = sqlite3.connect(args.db)
    cur = conn.cursor()
    known = {r[0] for r in cur.execute("SELECT month FROM macro_monthly")}

    written = skipped_missing = 0
    for key in sorted(fii):
        if key not in known:
            skipped_missing += 1
            continue
        cur.execute(
            "UPDATE macro_monthly SET monthly_fii_flow=?, monthly_dii_flow=? WHERE month=?",
            (round(fii[key], 4), round(dii[key], 4), key),
        )
        written += 1
    conn.commit()

    total, filled = cur.execute(
        "SELECT COUNT(*), COUNT(monthly_fii_flow) FROM macro_monthly").fetchone()
    print(f"  wrote {written} month(s)" + (f", skipped {skipped_missing} not in the table" if skipped_missing else ""))
    print(f"  macro_monthly: {filled}/{total} months now carry FII/DII")

    if filled < total:
        print()
        print("  The source covers a fraction of the table, so the earlier years are")
        print("  still empty. They are left null on purpose: back-filling a flow")
        print("  series that was never observed would make the published table look")
        print("  complete when it is not. The regime model drops fii_dii_trend below")
        print("  its 10 percent coverage floor, so nothing downstream changes.")

    print()
    print("  sample of the written months:")
    for key in sorted(fii)[:6]:
        if key in known:
            print(f"    {key}  days={days[key]:2d}  fii_net={fii[key]:>12,.1f}  dii_net={dii[key]:>12,.1f}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
