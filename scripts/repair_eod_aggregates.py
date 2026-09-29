"""One-off repair of the accumulated `daily_count` / `monthly_volume` values.

The EOD refresh now derives both from `stock_prices_daily`, so the next
scheduled run would correct the current month on its own. This applies the same
recomputation to the months already written, because the inflated figures are
committed to the database snapshot and the dashboard publishes them today.

Idempotent: re-running produces the same values, because it is a pure function
of the daily table.
"""
from __future__ import annotations
import sqlite3, os, sys

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                  "data_input", "processed_financial_data.sqlite")

conn = sqlite3.connect(DB)
cur = conn.cursor()

months = [r[0] for r in cur.execute(
    "SELECT DISTINCT month FROM stock_prices_monthly ORDER BY month")]
print(f"recomputing aggregates for {len(months)} months")

changed_days = changed_vol = 0
for month in months:
    prefix = str(month)[:7]
    rows = cur.execute(
        "SELECT symbol, COUNT(DISTINCT date), SUM(COALESCE(volume,0)) "
        "FROM stock_prices_daily WHERE substr(date,1,7)=? GROUP BY symbol",
        (prefix,)).fetchall()
    if not rows:
        continue
    for sym, days, vol in rows:
        old = cur.execute(
            "SELECT daily_count, monthly_volume FROM stock_prices_monthly "
            "WHERE month=? AND symbol=?", (month, sym)).fetchone()
        if not old:
            continue
        od, ov = int(old[0] or 0), float(old[1] or 0)
        nd, nv = int(days), float(vol)
        if od != nd or abs(ov - nv) > 0.5:
            cur.execute(
                "UPDATE stock_prices_monthly SET daily_count=?, monthly_volume=? "
                "WHERE month=? AND symbol=?", (nd, nv, month, sym))
            changed_days += od != nd
            changed_vol += abs(ov - nv) > 0.5

conn.commit()
print(f"  daily_count corrected on {changed_days} symbol-months")
print(f"  monthly_volume corrected on {changed_vol} symbol-months")

print("\nverifying:")
bad = 0
for month in months:
    prefix = str(month)[:7]
    real = cur.execute(
        "SELECT COUNT(DISTINCT date) FROM stock_prices_daily WHERE substr(date,1,7)=?",
        (prefix,)).fetchone()[0]
    if not real:
        continue
    hi = cur.execute("SELECT MAX(daily_count) FROM stock_prices_monthly WHERE month=?",
                     (month,)).fetchone()[0]
    flag = "" if (hi or 0) <= real else "  <-- STILL OVER"
    if flag: bad += 1
    if month in months[-4:]:
        print(f"    {month}: stored days={real:2d}  max daily_count={hi}{flag}")
print(f"\n  months still over-reporting: {bad}")
conn.close()
sys.exit(1 if bad else 0)
