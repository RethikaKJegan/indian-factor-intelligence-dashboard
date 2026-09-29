"""Data freshness check (spec section 24, verification).

A daily job that quietly stops working is worse than one that crashes, because
the dashboard keeps rendering and nobody notices the numbers stopped moving.
This module answers one question -- *is the data current?* -- and answers it
loudly.

Three separate things can be stale, and they fail differently:

1. **The EOD daily tables have stopped advancing.** `stock_prices_daily` is what
   the scheduled refresh writes. If its max date is behind the last trading
   day, the refresh is failing or not running.

2. **The monthly tables are labelled ahead of the data in them.** The pipeline
   keys months by calendar month-end, so an in-progress month is labelled
   `2026-09-30` even when the last available close is 2026-09-25. Every table
   therefore advertises a date the data has not reached. A reader comparing a
   table's month column against the header will see a contradiction that is
   really just an unstated convention.

3. **The refresh ran but found nothing, and the job said so quietly.**
   `daily_eod_refresh.py --allow-no-data` exits 0 on an empty fetch, so a
   failing refresh and a working one are indistinguishable from the exit code
   alone.

None of these are visible in the rendered numbers. All of them change what the
numbers mean.
"""

from __future__ import annotations

import datetime as dt
import sqlite3

#: NSE trading hours end at 15:30 IST. A refresh running before that on a
#: trading day will legitimately find no file for today, so "behind by one
#: trading day" is not automatically a fault.
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

#: NSE holidays. A full trading calendar is not available offline, so this
#: covers the fixed-date closures and the lunar-solar blocks that recur. It is
#: deliberately incomplete: a date treated as a trading day when it is a
#: holiday only makes the staleness count one day conservative.
FIXED_HOLIDAYS = {
    (1, 26), (8, 15), (10, 2), (12, 25),
}


def is_trading_day(d: dt.date) -> bool:
    """Best-effort NSE trading-day test.

    Weekends and the known fixed-date closures are excluded. Diwali and other
    lunar holidays are not modelled, so this returns True for some genuine
    holidays -- which makes the staleness count conservative rather than
    alarmist.
    """
    if d.weekday() >= 5:
        return False
    if (d.month, d.day) in FIXED_HOLIDAYS:
        return False
    return True


def last_trading_day(on_or_before: dt.date) -> dt.date:
    """Most recent trading day at or before `on_or_before`."""
    d = on_or_before
    for _ in range(30):
        if is_trading_day(d):
            return d
        d -= dt.timedelta(days=1)
    return d


def expected_eod_date(now: dt.datetime | None = None) -> dt.date:
    """The EOD date a healthy daily refresh should have delivered.

    EOD files for a trading day appear after the close, so before ~16:00 IST
    the correct expectation is the *previous* trading day. Between 16:00 IST
    and midnight it is today. Before the market opens, the previous trading day
    is right. This is the one place a "stale" verdict can be wrong purely
    because of the clock, so it errs toward expecting the older date.
    """
    now = now or dt.datetime.now(IST)
    today = now.date()
    if is_trading_day(today) and now.hour >= 16:
        return today
    return last_trading_day(today - dt.timedelta(days=1))


def assess(db_path: str, now: dt.datetime | None = None) -> dict:
    """Measure how current the database is, in every way that can be measured."""
    now = now or dt.datetime.now(IST)
    today = now.date()
    result: dict = {
        "checked_at": now.isoformat(),
        "database": db_path,
        "today": today.isoformat(),
        "expected_eod_date": expected_eod_date(now).isoformat(),
        "trading_calendar_note": (
            "Weekends and fixed-date NSE closures are excluded. Diwali and "
            "other lunar holidays are not modelled, so a genuine holiday may be "
            "counted as a missed trading day. The count errs conservative."
        ),
        "issues": [],
    }

    if not db_path:
        result["status"] = "unknown"
        result["issues"].append({
            "id": "no_database",
            "severity": "high",
            "detail": "No database path supplied, so freshness cannot be measured.",
        })
        return result

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        result["status"] = "unreadable"
        result["issues"].append({
            "id": "database_unreadable",
            "severity": "high",
            "detail": f"Could not open the database: {exc}",
        })
        return result

    try:
        present = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }

        # 1. Is the EOD daily table advancing?
        eod_date = None
        eod_rows = 0
        if "stock_prices_daily" in present:
            eod_rows = conn.execute(
                "SELECT COUNT(*) FROM stock_prices_daily"
            ).fetchone()[0]
            if eod_rows:
                eod_date = conn.execute(
                    "SELECT MAX(date) FROM stock_prices_daily"
                ).fetchone()[0]
        result["eod"] = {
            "table": "stock_prices_daily",
            "rows": eod_rows,
            "latest_date": eod_date,
            "distinct_dates": conn.execute(
                "SELECT COUNT(DISTINCT date) FROM stock_prices_daily"
            ).fetchone()[0] if "stock_prices_daily" in present else 0,
        }

        expected = result["expected_eod_date"]
        behind = None
        if eod_date:
            try:
                have = dt.date.fromisoformat(str(eod_date)[:10])
                behind = 0
                cursor = have + dt.timedelta(days=1)
                while cursor <= today and behind < 30:
                    if is_trading_day(cursor):
                        behind += 1
                    cursor += dt.timedelta(days=1)
                # Do not count today itself when the market has not closed yet.
                if is_trading_day(today) and today == have and now.hour < 16:
                    behind = 0
            except ValueError:
                behind = None
        result["eod"]["trading_days_behind"] = behind
        result["eod"]["expected_date"] = expected

        if behind is None:
            result["issues"].append({
                "id": "eod_date_unreadable",
                "severity": "high",
                "detail": "Could not read a date from stock_prices_daily.",
            })
        elif behind == 0:
            result["issues"].append({
                "id": "eod_current",
                "severity": "ok",
                "detail": f"EOD data is current through {eod_date}.",
            })
        elif behind == 1:
            result["issues"].append({
                "id": "eod_one_day_behind",
                "severity": "low",
                "detail": (
                    f"EOD data stops at {eod_date}, one trading day behind "
                    f"{expected}. Usually the refresh has not run yet today."
                ),
            })
        elif behind <= 3:
            result["issues"].append({
                "id": "eod_falling_behind",
                "severity": "medium",
                "detail": (
                    f"EOD data stops at {eod_date}, {behind} trading days behind "
                    f"{expected}. The daily refresh is missing runs."
                ),
            })
        else:
            result["issues"].append({
                "id": "eod_stale",
                "severity": "high",
                "detail": (
                    f"EOD data stops at {eod_date}, {behind} trading days behind "
                    f"{expected}. The daily refresh has not been working. Every "
                    f"current-month figure on the dashboard is out of date."
                ),
            })

        # 2. Do the monthly labels run ahead of the data inside them?
        monthly: dict = {}
        for table in ("stock_prices_monthly", "market_index_monthly",
                      "fundamentals_monthly"):
            if table not in present:
                continue
            row = conn.execute(
                f"SELECT MIN(month), MAX(month), COUNT(*) FROM {table}"
            ).fetchone()
            monthly[table] = {
                "month_min": row[0],
                "month_max": row[1],
                "rows": row[2],
            }
        result["monthly"] = monthly

        newest_label = None
        for info in monthly.values():
            if info.get("month_max") and (newest_label is None
                                         or info["month_max"] > newest_label):
                newest_label = info["month_max"]
        result["newest_month_label"] = newest_label

        if newest_label and eod_date:
            label_date = str(newest_label)[:10]
            data_date = str(eod_date)[:10]
            if label_date > data_date:
                gap = (
                    dt.date.fromisoformat(label_date)
                    - dt.date.fromisoformat(data_date)
                ).days
                result["issues"].append({
                    "id": "month_label_ahead_of_data",
                    "severity": "medium",
                    "detail": (
                        f"Monthly tables are labelled through {label_date} but the "
                        f"newest close in the database is {data_date}, a gap of "
                        f"{gap} days. Months are keyed by calendar month-end, so an "
                        f"in-progress month always carries a future date. The label "
                        f"is a bucket, not a claim that trading reached it -- but "
                        f"nothing in the table says so."
                    ),
                })

        # 3. Has the refresh been failing while reporting success?
        if "eod_refresh_runs" in present:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(eod_refresh_runs)")]
            recent = conn.execute(
                "SELECT * FROM eod_refresh_runs ORDER BY started_at DESC LIMIT 10"
            ).fetchall()
            runs = [dict(zip(cols, r)) for r in recent]
            statuses: dict = {}
            for r in runs:
                statuses[r.get("status")] = statuses.get(r.get("status"), 0) + 1
            result["recent_refresh_runs"] = {
                "count": len(runs),
                "status_counts": statuses,
                "latest_started_at": runs[0].get("started_at") if runs else None,
                "latest_resolved_date": runs[0].get("resolved_date") if runs else None,
                "latest_status": runs[0].get("status") if runs else None,
                "latest_message": runs[0].get("message") if runs else None,
            }
            silent = statuses.get("no_data", 0) + statuses.get("failed", 0)
            if silent:
                result["issues"].append({
                    "id": "refresh_reported_failure",
                    "severity": "medium",
                    "detail": (
                        f"{silent} of the last {len(runs)} refresh attempts did not "
                        f"find usable data. The scheduled job passes "
                        f"--allow-no-data, so those attempts exit 0 and a failing "
                        f"refresh looks identical to a working one from the exit "
                        f"code. Read eod_refresh_status.json, not the job status."
                    ),
                })
            if runs and behind and behind > 0:
                last_ok = None
                for r in runs:
                    if r.get("status") == "ok":
                        last_ok = r.get("resolved_date")
                        break
                if last_ok and behind > 0:
                    result["issues"].append({
                        "id": "refresh_stalled_after_last_success",
                        "severity": "medium",
                        "detail": (
                            f"The last refresh that actually delivered data resolved "
                            f"{last_ok}. Attempts since then have not extended the "
                            f"series."
                        ),
                    })
    finally:
        conn.close()

    severities = {i["severity"] for i in result["issues"]}
    if "high" in severities:
        result["status"] = "stale"
    elif "medium" in severities:
        result["status"] = "degraded"
    else:
        result["status"] = "current"
    return result


def format_report(a: dict) -> str:
    """Human-readable summary for the pipeline log and a terminal."""
    lines = []
    lines.append("Data freshness")
    lines.append(f"  today              {a.get('today')}")
    lines.append(f"  expected EOD date  {a.get('expected_eod_date')}")
    eod = a.get("eod", {})
    lines.append(
        f"  latest close       {eod.get('latest_date')} "
        f"({eod.get('rows', 0)} daily rows, {eod.get('trading_days_behind')} "
        f"trading days behind)"
    )
    lines.append(f"  newest month label {a.get('newest_month_label')}")
    rr = a.get("recent_refresh_runs") or {}
    if rr:
        lines.append(
            f"  last refresh       {rr.get('latest_status')} at "
            f"{str(rr.get('latest_started_at'))[:19]} "
            f"(counts: {rr.get('status_counts')})"
        )
    lines.append(f"  VERDICT            {a.get('status', '').upper()}")
    for i in a.get("issues", []):
        mark = {"high": "[!]", "medium": "[~]", "low": "[.]", "ok": "[+]"}.get(
            i["severity"], "[ ]"
        )
        lines.append(f"  {mark} {i['detail']}")
    return "\n".join(lines)
