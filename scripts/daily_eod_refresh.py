#!/usr/bin/env python3
"""
Daily NSE EOD refresh for the Indian Factor Intelligence dashboard.

No mock data is generated. If official NSE/Nifty data is unavailable, the script
records the failure and exits non-zero unless --allow-no-data is supplied.

What it updates:
  - stock_prices_daily
  - market_index_daily
  - stock_prices_monthly for the affected current month
  - market_index_monthly for fetched index rows
  - factor_scores_monthly for the affected month
  - regime_features_monthly for the affected month
  - public/data/eod_refresh_status.json
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import math
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from urllib.error import HTTPError, URLError

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
DB_PATH = PROJECT_DIR / "data_input" / "processed_financial_data.sqlite"
JSON_DIR = PROJECT_DIR / "public" / "data"
RAW_DATA_DIR = PROJECT_DIR.parent.parent / "data"
RAW_EOD_DIR = RAW_DATA_DIR / "Daily EOD Refresh"
STATUS_PATH = JSON_DIR / "eod_refresh_status.json"

CUTOFF_NEW_BHAVCOPY = dt.date(2024, 7, 8)
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/123 Safari/537.36"
EXCLUDED = {"ENRIN", "GROWW", "HDFCLIFE", "ICICIAMC", "ICICIGI", "LENSKART", "LGEINDIA", "MCX", "SBILIFE", "TATACAP", "TMCV"}

INDEX_API_URL = "https://www.niftyindices.com/Backpage.aspx/getHistoricaldatatabletoString"
INDEX_PAGE_URL = "https://www.niftyindices.com/reports/historical-data"
INDEX_NAMES = ["NIFTY 200", "INDIA VIX"]
YAHOO_INDEX_SYMBOLS = {
    "NIFTY 200": "^CNX200",
    "INDIA VIX": "^INDIAVIX",
}


def month_end(date_value: dt.date) -> str:
    first_next = dt.date(date_value.year + int(date_value.month == 12), 1 if date_value.month == 12 else date_value.month + 1, 1)
    return (first_next - dt.timedelta(days=1)).isoformat()


def parse_date(value: str) -> dt.date:
    return dt.datetime.strptime(value, "%Y-%m-%d").date()


def daterange(start: dt.date, end: dt.date):
    cur = start
    while cur <= end:
        yield cur
        cur += dt.timedelta(days=1)


def request_bytes(url: str, *, referer: str = "https://www.nseindia.com/", timeout: int = 35) -> bytes | None:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/csv,application/zip,application/json,text/html,*/*",
            "Referer": referer,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = response.read()
        if data[:1] == b"<" and b"<html" in data[:200].lower():
            return None
        return data
    except (HTTPError, URLError, TimeoutError):
        return None


def old_pr_url(date_value: dt.date) -> str:
    return f"https://nsearchives.nseindia.com/archives/equities/bhavcopy/pr/PR{date_value:%d%m%y}.zip"


def new_full_csv_url(date_value: dt.date) -> str:
    return f"https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{date_value:%d%m%Y}.csv"


def new_udiff_url(date_value: dt.date) -> str:
    return f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{date_value:%Y%m%d}_F_0000.csv.zip"


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().upper().replace(" ", "_") for c in df.columns]
    rename = {
        "SECURITY_NAME": "SECURITY",
        "PREVIOUS_CLOSE_PRICE": "PREV_CL_PR",
        "OPEN": "OPEN_PRICE",
        "HIGH": "HIGH_PRICE",
        "LOW": "LOW_PRICE",
        "CLOSE": "CLOSE_PRICE",
        "NO_OF_SHRS": "NET_TRDQTY",
        "TOTAL_TRADED_QUANTITY": "NET_TRDQTY",
        "TOTAL_TRADED_VALUE": "NET_TRDVAL",
        "TOTAL_TRADES": "TRADES",
        "NO_OF_TRADES": "TRADES",
        "TOTTRDVAL": "NET_TRDVAL",
        "TTL_TRD_QNTY": "NET_TRDQTY",
    }
    return df.rename(columns={k: v for k, v in rename.items() if k in df.columns})


def read_csv_bytes(data: bytes) -> pd.DataFrame | None:
    try:
        return normalize_columns(pd.read_csv(io.BytesIO(data)))
    except Exception:
        return None


def read_udiff_zip(data: bytes) -> pd.DataFrame | None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            target = next((n for n in zf.namelist() if n.lower().endswith(".csv")), "")
            if not target:
                return None
            with zf.open(target) as fh:
                return normalize_columns(pd.read_csv(fh))
    except Exception:
        return None


def read_old_pr_zip(data: bytes, date_value: dt.date) -> pd.DataFrame | None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            target = f"Pd{date_value:%d%m%y}.csv"
            if target not in zf.namelist():
                target = next((n for n in zf.namelist() if n.lower().startswith("pd") and n.lower().endswith(".csv")), "")
            if not target:
                return None
            with zf.open(target) as fh:
                return normalize_columns(pd.read_csv(fh))
    except Exception:
        return None


def download_bhavcopy(date_value: dt.date) -> tuple[pd.DataFrame | None, str]:
    if date_value < CUTOFF_NEW_BHAVCOPY:
        url = old_pr_url(date_value)
        data = request_bytes(url)
        return (read_old_pr_zip(data, date_value) if data else None), url

    url = new_full_csv_url(date_value)
    data = request_bytes(url)
    if data:
        df = read_csv_bytes(data)
        if df is not None and not df.empty:
            return df, url

    url = new_udiff_url(date_value)
    data = request_bytes(url)
    return (read_udiff_zip(data) if data else None), url


def clean_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.astype(str).str.replace(",", "", regex=False).str.strip(), errors="coerce")


def load_universe(conn: sqlite3.Connection) -> pd.DataFrame:
    rows = pd.read_sql_query(
        """
        SELECT symbol, MAX(company_name) AS company_name, MAX(sector) AS sector
        FROM stock_prices_monthly
        GROUP BY symbol
        ORDER BY symbol
        """,
        conn,
    )
    rows["symbol"] = rows["symbol"].astype(str).str.upper().str.strip()
    rows = rows[~rows["symbol"].isin(EXCLUDED)].copy()
    return rows


def filter_nifty200(df: pd.DataFrame, universe: pd.DataFrame, date_value: dt.date, source_url: str) -> pd.DataFrame:
    if df is None or df.empty or "SYMBOL" not in df.columns:
        return pd.DataFrame()
    df = df.copy()
    df["SYMBOL"] = df["SYMBOL"].astype(str).str.upper().str.strip()
    if "SERIES" in df.columns:
        df = df[df["SERIES"].astype(str).str.upper().str.strip().isin(["EQ", ""])]
    df = df[df["SYMBOL"].isin(set(universe["symbol"]))].copy()
    if df.empty:
        return df
    for col in ["OPEN_PRICE", "HIGH_PRICE", "LOW_PRICE", "CLOSE_PRICE", "NET_TRDQTY", "NET_TRDVAL", "TRADES"]:
        if col not in df.columns:
            df[col] = np.nan
        df[col] = clean_numeric(df[col])
    out = pd.DataFrame({
        "date": date_value.isoformat(),
        "symbol": df["SYMBOL"],
        "open": df["OPEN_PRICE"],
        "high": df["HIGH_PRICE"],
        "low": df["LOW_PRICE"],
        "close": df["CLOSE_PRICE"],
        "volume": df["NET_TRDQTY"],
        "turnover": df["NET_TRDVAL"],
        "trades": df["TRADES"],
        "source": source_url,
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    })
    out = out.dropna(subset=["symbol", "close"]).sort_values("symbol")
    return out


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS stock_prices_daily (
          date TEXT NOT NULL,
          symbol TEXT NOT NULL,
          open REAL,
          high REAL,
          low REAL,
          close REAL,
          volume REAL,
          turnover REAL,
          trades REAL,
          source TEXT,
          fetched_at TEXT,
          PRIMARY KEY(date, symbol)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS market_index_daily (
          date TEXT NOT NULL,
          index_name TEXT NOT NULL,
          open REAL,
          high REAL,
          low REAL,
          close REAL,
          source TEXT,
          fetched_at TEXT,
          PRIMARY KEY(date, index_name)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS eod_refresh_runs (
          run_id TEXT PRIMARY KEY,
          requested_date TEXT,
          resolved_date TEXT,
          status TEXT,
          stock_rows INTEGER,
          index_rows INTEGER,
          message TEXT,
          started_at TEXT,
          finished_at TEXT
        )
        """
    )
    conn.commit()


def upsert_dataframe(conn: sqlite3.Connection, table: str, df: pd.DataFrame, key_cols: list[str]) -> int:
    if df.empty:
        return 0
    cols = list(df.columns)
    placeholders = ",".join(["?"] * len(cols))
    updates = ",".join([f"{c}=excluded.{c}" for c in cols if c not in key_cols])
    sql = f"""
        INSERT INTO {table} ({",".join(cols)})
        VALUES ({placeholders})
        ON CONFLICT({",".join(key_cols)}) DO UPDATE SET {updates}
    """
    conn.executemany(sql, df[cols].where(pd.notna(df[cols]), None).itertuples(index=False, name=None))
    conn.commit()
    return len(df)


def download_latest_stock_eod(conn: sqlite3.Connection, target_date: dt.date, lookback_days: int, sleep: float) -> tuple[pd.DataFrame, dt.date | None, str]:
    universe = load_universe(conn)
    attempts = []
    for date_value in sorted(list(daterange(target_date - dt.timedelta(days=lookback_days), target_date)), reverse=True):
        if date_value.weekday() >= 5:
            continue
        raw, source_url = download_bhavcopy(date_value)
        attempts.append({"date": date_value.isoformat(), "source": source_url, "raw_rows": 0 if raw is None else len(raw)})
        if raw is None or raw.empty:
            time.sleep(sleep)
            continue
        filtered = filter_nifty200(raw, universe, date_value, source_url)
        if not filtered.empty:
            RAW_EOD_DIR.mkdir(parents=True, exist_ok=True)
            filtered.to_csv(RAW_EOD_DIR / f"nifty200_eod_{date_value:%Y%m%d}.csv", index=False)
            return filtered, date_value, source_url
        time.sleep(sleep)
    return pd.DataFrame(), None, json.dumps(attempts)


def fetch_nifty_index(index_name: str, date_value: dt.date) -> dict | None:
    start = date_value.strftime("%d-%b-%Y")
    end = start
    payloads = [
        {"cinfo": json.dumps({"name": index_name, "startDate": start, "endDate": end})},
        {"name": index_name, "startDate": start, "endDate": end},
    ]
    for payload in payloads:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            INDEX_API_URL,
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json; charset=UTF-8",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": INDEX_PAGE_URL,
                "Origin": "https://www.niftyindices.com",
                "User-Agent": USER_AGENT,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                text = response.read().decode("utf-8", errors="replace")
            obj = json.loads(text)
            rows = json.loads(obj.get("d", "[]")) if isinstance(obj.get("d"), str) else obj.get("d", [])
            if not rows:
                continue
            row = rows[-1]
            return {
                "date": date_value.isoformat(),
                "index_name": index_name,
                "open": to_float(row.get("OPEN") or row.get("Open")),
                "high": to_float(row.get("HIGH") or row.get("High")),
                "low": to_float(row.get("LOW") or row.get("Low")),
                "close": to_float(row.get("CLOSE") or row.get("Close")),
                "source": INDEX_API_URL,
                "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
        except Exception:
            time.sleep(0.2)
    return fetch_yahoo_index(index_name, date_value)


def fetch_yahoo_index(index_name: str, date_value: dt.date) -> dict | None:
    """Fallback real index source when the Nifty Indices endpoint is unavailable."""
    symbol = YAHOO_INDEX_SYMBOLS.get(index_name)
    if not symbol:
        return None

    start_dt = dt.datetime.combine(date_value - dt.timedelta(days=2), dt.time.min, tzinfo=dt.timezone.utc)
    end_dt = dt.datetime.combine(date_value + dt.timedelta(days=1), dt.time.min, tzinfo=dt.timezone.utc)
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{urllib.parse.quote(symbol, safe='')}?period1={int(start_dt.timestamp())}"
        f"&period2={int(end_dt.timestamp())}&interval=1d"
    )
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json,text/plain,*/*",
            "Referer": "https://finance.yahoo.com/",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            obj = json.loads(response.read().decode("utf-8", errors="replace"))
        result = (obj.get("chart", {}).get("result") or [None])[0]
        if not result:
            return None
        timestamps = result.get("timestamp") or []
        quote = (result.get("indicators", {}).get("quote") or [{}])[0]
        for idx, timestamp in enumerate(timestamps):
            row_date = dt.datetime.fromtimestamp(timestamp, tz=dt.timezone.utc).date()
            if row_date != date_value:
                continue
            close = list_value(quote.get("close"), idx)
            if close is None:
                continue
            return {
                "date": date_value.isoformat(),
                "index_name": index_name,
                "open": list_value(quote.get("open"), idx),
                "high": list_value(quote.get("high"), idx),
                "low": list_value(quote.get("low"), idx),
                "close": close,
                "source": url,
                "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
    except Exception:
        return None
    return None


def list_value(values, idx: int):
    if not isinstance(values, list) or idx >= len(values):
        return None
    return to_float(values[idx])


def to_float(value):
    try:
        if value is None:
            return None
        v = float(str(value).replace(",", "").strip())
        return None if math.isnan(v) or math.isinf(v) else v
    except Exception:
        return None


def refresh_market_index_daily(conn: sqlite3.Connection, date_value: dt.date) -> pd.DataFrame:
    rows = []
    for index_name in INDEX_NAMES:
        row = fetch_nifty_index(index_name, date_value)
        if row and row.get("close"):
            rows.append(row)
        time.sleep(0.25)
    df = pd.DataFrame(rows)
    if not df.empty:
        upsert_dataframe(conn, "market_index_daily", df, ["date", "index_name"])
        RAW_EOD_DIR.mkdir(parents=True, exist_ok=True)
        df.to_csv(RAW_EOD_DIR / f"market_index_eod_{date_value:%Y%m%d}.csv", index=False)
    return df


def replace_rows(conn: sqlite3.Connection, table: str, month_value: str, rows: pd.DataFrame) -> None:
    if rows.empty:
        return
    conn.execute(f"DELETE FROM {table} WHERE month = ?", (month_value,))
    rows.to_sql(table, conn, if_exists="append", index=False)
    conn.commit()


def refresh_stock_month(conn: sqlite3.Connection, date_value: dt.date, baseline_eod: dt.date | None) -> int:
    month_value = month_end(date_value)
    month_prefix = month_value[:7]
    daily = pd.read_sql_query(
        "SELECT * FROM stock_prices_daily WHERE substr(date,1,7)=? ORDER BY symbol,date",
        conn,
        params=(month_prefix,),
    )
    if daily.empty:
        return 0
    base = pd.read_sql_query("SELECT * FROM stock_prices_monthly WHERE month=?", conn, params=(month_value,))
    universe = load_universe(conn)
    prev_months = pd.read_sql_query("SELECT month,symbol,monthly_close FROM stock_prices_monthly WHERE month < ? ORDER BY month", conn, params=(month_value,))
    prev_close = prev_months.groupby("symbol")["monthly_close"].last().to_dict() if not prev_months.empty else {}
    existing = {r["symbol"]: r for r in base.to_dict("records")} if not base.empty else {}
    rows = []
    for sym, group in daily.groupby("symbol"):
        group = group.sort_values("date")
        latest = group.iloc[-1]
        old = existing.get(sym, {})
        company = universe.loc[universe["symbol"] == sym, "company_name"]
        sector = universe.loc[universe["symbol"] == sym, "sector"]
        previous = prev_close.get(sym)
        close = float(latest["close"])
        existing_volume = float(old.get("monthly_volume") or 0)
        existing_count = int(old.get("daily_count") or 0)
        if baseline_eod:
            new_group = group[pd.to_datetime(group["date"]).dt.date > baseline_eod]
        else:
            new_group = group
        volume = existing_volume + float(new_group["volume"].fillna(0).sum()) if old else float(group["volume"].fillna(0).sum())
        daily_count = existing_count + len(new_group["date"].unique()) if old else len(group["date"].unique())
        monthly_return = (close / previous - 1) if previous and previous > 0 else old.get("monthly_return")
        rolling_high = max(close, float(old.get("monthly_close") or close))
        drawdown = close / rolling_high - 1 if rolling_high else 0
        row = {
            "month": month_value,
            "symbol": sym,
            "company_name": old.get("company_name") or (company.iloc[0] if not company.empty else sym),
            "sector": old.get("sector") or (sector.iloc[0] if not sector.empty else ""),
            "monthly_close": close,
            "monthly_return": monthly_return,
            "monthly_volume": volume,
            "monthly_volatility": old.get("monthly_volatility"),
            "monthly_drawdown": drawdown,
            "return_3m": old.get("return_3m"),
            "return_6m": old.get("return_6m"),
            "return_12m": old.get("return_12m"),
            "momentum_12_1": old.get("momentum_12_1"),
            "volatility_6m": old.get("volatility_6m"),
            "volatility_12m": old.get("volatility_12m"),
            "max_drawdown_12m": old.get("max_drawdown_12m"),
            "daily_count": daily_count,
            "source_file": f"Daily EOD Refresh/nifty200_eod_{date_value:%Y%m%d}.csv",
        }
        rows.append(row)
    updated = pd.DataFrame(rows)
    keep_existing = base[~base["symbol"].isin(set(updated["symbol"]))] if not base.empty else pd.DataFrame()
    final = pd.concat([keep_existing, updated], ignore_index=True, sort=False)
    replace_rows(conn, "stock_prices_monthly", month_value, final)
    recompute_stock_rolling_features(conn)
    return len(updated)


def recompute_stock_rolling_features(conn: sqlite3.Connection) -> None:
    df = pd.read_sql_query("SELECT * FROM stock_prices_monthly ORDER BY symbol, month", conn)
    if df.empty:
        return
    df["monthly_return"] = df.groupby("symbol")["monthly_close"].pct_change()
    df["return_3m"] = df.groupby("symbol")["monthly_close"].pct_change(3)
    df["return_6m"] = df.groupby("symbol")["monthly_close"].pct_change(6)
    df["return_12m"] = df.groupby("symbol")["monthly_close"].pct_change(12)
    df["momentum_12_1"] = df.groupby("symbol")["monthly_close"].transform(lambda s: s.shift(1) / s.shift(12) - 1)
    df["volatility_6m"] = df.groupby("symbol")["monthly_return"].transform(lambda s: s.rolling(6, min_periods=3).std())
    df["volatility_12m"] = df.groupby("symbol")["monthly_return"].transform(lambda s: s.rolling(12, min_periods=6).std())
    df["monthly_drawdown"] = df["monthly_close"] / df.groupby("symbol")["monthly_close"].cummax() - 1
    df["max_drawdown_12m"] = df.groupby("symbol")["monthly_drawdown"].transform(lambda s: s.rolling(12, min_periods=3).min())
    conn.execute("DELETE FROM stock_prices_monthly")
    df.to_sql("stock_prices_monthly", conn, if_exists="append", index=False)
    conn.commit()


def refresh_market_month(conn: sqlite3.Connection, date_value: dt.date) -> int:
    month_value = month_end(date_value)
    month_prefix = month_value[:7]
    daily = pd.read_sql_query(
        "SELECT * FROM market_index_daily WHERE substr(date,1,7)=? ORDER BY index_name,date",
        conn,
        params=(month_prefix,),
    )
    if daily.empty:
        return 0
    base = pd.read_sql_query("SELECT * FROM market_index_monthly WHERE month=?", conn, params=(month_value,))
    prev = pd.read_sql_query("SELECT month,index_name,monthly_close FROM market_index_monthly WHERE month < ? ORDER BY month", conn, params=(month_value,))
    prev_close = prev.groupby("index_name")["monthly_close"].last().to_dict() if not prev.empty else {}
    existing = {r["index_name"]: r for r in base.to_dict("records")} if not base.empty else {}
    rows = []
    for idx_name, group in daily.groupby("index_name"):
        latest = group.sort_values("date").iloc[-1]
        old = existing.get(idx_name, {})
        close = float(latest["close"])
        previous = prev_close.get(idx_name)
        rows.append({
            "month": month_value,
            "index_name": idx_name,
            "monthly_close": close,
            "monthly_return": (close / previous - 1) if previous and previous > 0 else old.get("monthly_return"),
            "monthly_volume": old.get("monthly_volume"),
            "monthly_volatility": old.get("monthly_volatility"),
            "monthly_drawdown": close / max(close, float(old.get("monthly_close") or close)) - 1,
            "source_file": f"Daily EOD Refresh/market_index_eod_{date_value:%Y%m%d}.csv",
            "vix_avg": float(group["close"].mean()) if idx_name.upper() == "INDIA VIX" else old.get("vix_avg"),
            "vix_max": float(group["close"].max()) if idx_name.upper() == "INDIA VIX" else old.get("vix_max"),
        })
    updated = pd.DataFrame(rows)
    keep_existing = base[~base["index_name"].isin(set(updated["index_name"]))] if not base.empty else pd.DataFrame()
    final = pd.concat([keep_existing, updated], ignore_index=True, sort=False)
    replace_rows(conn, "market_index_monthly", month_value, final)
    return len(updated)


def zscore(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    vals = pd.to_numeric(series, errors="coerce")
    if not higher_is_better:
        vals = -vals
    mean = vals.mean(skipna=True)
    std = vals.std(skipna=True)
    if not std or math.isnan(std):
        return pd.Series([np.nan] * len(vals), index=vals.index)
    return (vals - mean) / std


def refresh_factor_scores(conn: sqlite3.Connection, date_value: dt.date) -> int:
    month_value = month_end(date_value)
    prices = pd.read_sql_query("SELECT * FROM stock_prices_monthly WHERE month=?", conn, params=(month_value,))
    if prices.empty:
        return 0
    fund = pd.read_sql_query("SELECT * FROM fundamentals_monthly WHERE month=?", conn, params=(month_value,))
    df = prices.merge(fund, on=["month", "symbol"], how="left", suffixes=("", "_fund"))
    df = df[~df["symbol"].isin(EXCLUDED)].copy()
    df["momentum_score"] = pd.concat([
        zscore(df.get("momentum_12_1")),
        zscore(df.get("return_6m")),
        zscore(df.get("return_3m")),
    ], axis=1).mean(axis=1, skipna=True)
    df["value_score"] = pd.concat([
        zscore(df.get("monthly_pe"), higher_is_better=False),
        zscore(df.get("monthly_pb"), higher_is_better=False),
        zscore(df.get("ev_ebitda"), higher_is_better=False),
        zscore(df.get("earnings_yield_ttm")),
    ], axis=1).mean(axis=1, skipna=True)
    df["quality_score"] = pd.concat([
        zscore(df.get("monthly_roe")),
        zscore(df.get("monthly_roce")),
        zscore(df.get("debt_equity"), higher_is_better=False),
        zscore(df.get("profit_margin")),
    ], axis=1).mean(axis=1, skipna=True)
    df["low_volatility_score"] = pd.concat([
        zscore(df.get("volatility_6m"), higher_is_better=False),
        zscore(df.get("volatility_12m"), higher_is_better=False),
        zscore(df.get("max_drawdown_12m"), higher_is_better=True),
    ], axis=1).mean(axis=1, skipna=True)
    df["overall_score"] = df[["momentum_score", "value_score", "quality_score", "low_volatility_score"]].mean(axis=1, skipna=True)
    for score_col, rank_col in [
        ("momentum_score", "momentum_rank"),
        ("value_score", "value_rank"),
        ("quality_score", "quality_rank"),
        ("low_volatility_score", "low_vol_rank"),
        ("overall_score", "overall_rank"),
    ]:
        df[rank_col] = df[score_col].rank(ascending=False, method="min")
    out = df[[
        "month", "symbol", "momentum_score", "value_score", "quality_score", "low_volatility_score",
        "overall_score", "momentum_rank", "value_rank", "quality_rank", "low_vol_rank", "overall_rank"
    ]]
    conn.execute("DELETE FROM factor_scores_monthly WHERE month=?", (month_value,))
    out.to_sql("factor_scores_monthly", conn, if_exists="append", index=False)
    conn.commit()
    return len(out)


def refresh_regime_features(conn: sqlite3.Connection, date_value: dt.date) -> int:
    month_value = month_end(date_value)
    market = pd.read_sql_query("SELECT * FROM market_index_monthly ORDER BY month", conn)
    stocks = pd.read_sql_query("SELECT month,symbol,monthly_return FROM stock_prices_monthly ORDER BY month,symbol", conn)
    macro = pd.read_sql_query("SELECT * FROM macro_monthly ORDER BY month", conn)
    news = pd.read_sql_query("SELECT * FROM news_features_monthly ORDER BY month", conn)
    if market.empty:
        return 0
    nifty = market[market["index_name"].str.upper().str.contains("NIFTY 200|NIFTY 50|NIFTY", na=False)].copy()
    if nifty.empty:
        return 0
    nifty = nifty.sort_values("month").drop_duplicates("month", keep="last")
    vix = market[market["index_name"].str.upper().eq("INDIA VIX")][["month", "monthly_close", "monthly_return"]].rename(columns={"monthly_close": "india_vix_level", "monthly_return": "india_vix_change"})
    row = nifty[nifty["month"] == month_value]
    if row.empty:
        return 0
    n = nifty.reset_index(drop=True)
    i = int(n.index[n["month"] == month_value][0])
    close = float(n.loc[i, "monthly_close"])
    def pct(lag):
        if i >= lag and n.loc[i - lag, "monthly_close"]:
            return close / float(n.loc[i - lag, "monthly_close"]) - 1
        return None
    stock_month = stocks[stocks["month"] == month_value]
    breadth = float((stock_month["monthly_return"] > 0).mean()) if not stock_month.empty else None
    macro_latest = macro[macro["month"] <= month_value].tail(1).to_dict("records")
    macro_row = macro_latest[0] if macro_latest else {}
    news_latest = news[news["month"].astype(str).str[:7] == month_value[:7]].tail(1).to_dict("records")
    news_row = news_latest[0] if news_latest else {}
    vix_row = vix[vix["month"] == month_value].tail(1).to_dict("records")
    vrow = vix_row[0] if vix_row else {}
    out = pd.DataFrame([{
        "month": month_value,
        "nifty_1m_return": n.loc[i, "monthly_return"],
        "nifty_drawdown": n.loc[i, "monthly_drawdown"],
        "realized_volatility": n.loc[i, "monthly_volatility"],
        "nifty_3m_return": pct(3),
        "nifty_6m_return": pct(6),
        "nifty_12m_return": pct(12),
        "india_vix_level": vrow.get("india_vix_level"),
        "india_vix_change": vrow.get("india_vix_change"),
        "cpi_trend": macro_row.get("monthly_cpi_inflation"),
        "repo_rate_trend": macro_row.get("repo_rate"),
        "yield_trend": macro_row.get("monthly_yield"),
        "usd_inr_change": macro_row.get("monthly_usd_inr"),
        "crude_change": macro_row.get("monthly_crude"),
        "fii_dii_trend": (macro_row.get("monthly_fii_flow") or 0) + (macro_row.get("monthly_dii_flow") or 0) if macro_row else None,
        "news_sentiment": news_row.get("monthly_news_sentiment"),
        "negative_news_ratio": news_row.get("monthly_negative_news_ratio"),
        "risk_event_count": news_row.get("monthly_risk_event_count"),
        "stock_coverage_x": int(stock_month["symbol"].nunique()) if not stock_month.empty else None,
        "sector_count_x": None,
        "market_breadth": breadth,
        "stock_coverage_y": int(stock_month["symbol"].nunique()) if not stock_month.empty else None,
        "sector_breadth": None,
        "sector_count_y": None,
    }])
    conn.execute("DELETE FROM regime_features_monthly WHERE month=?", (month_value,))
    out.to_sql("regime_features_monthly", conn, if_exists="append", index=False)
    conn.commit()
    return 1


def write_status(status: dict) -> None:
    JSON_DIR.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps(status, indent=2, default=str), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=dt.date.today().isoformat(), help="Target EOD date, YYYY-MM-DD")
    parser.add_argument("--lookback-days", type=int, default=7, help="Look back for latest available trading day")
    parser.add_argument("--baseline-eod", default="2026-09-23", help="Existing DB baseline EOD date used to avoid double-counting old monthly volume")
    parser.add_argument("--allow-no-data", action="store_true", help="Write failure status but exit 0 when no EOD data is found")
    parser.add_argument("--sleep", type=float, default=0.4)
    args = parser.parse_args()

    started = dt.datetime.now(dt.timezone.utc)
    requested = parse_date(args.date)
    baseline = parse_date(args.baseline_eod) if args.baseline_eod else None
    run_id = started.strftime("%Y%m%dT%H%M%SZ")
    status = {
        "run_id": run_id,
        "requested_date": requested.isoformat(),
        "resolved_date": None,
        "status": "running",
        "stock_rows": 0,
        "index_rows": 0,
        "updated_stock_monthly_rows": 0,
        "updated_factor_score_rows": 0,
        "updated_regime_feature_rows": 0,
        "message": "",
        "started_at": started.isoformat(),
        "finished_at": None,
    }
    write_status(status)

    if not DB_PATH.exists():
        status.update({"status": "failed", "message": f"Database not found: {DB_PATH}", "finished_at": dt.datetime.now(dt.timezone.utc).isoformat()})
        write_status(status)
        return 0 if args.allow_no_data else 1

    conn = sqlite3.connect(DB_PATH)
    ensure_tables(conn)
    try:
        stocks_df, resolved_date, source = download_latest_stock_eod(conn, requested, args.lookback_days, args.sleep)
        if stocks_df.empty or resolved_date is None:
            status.update({"status": "no_data", "message": f"No NSE EOD bhavcopy found. Attempts: {source}"})
            return_code = 0 if args.allow_no_data else 2
        else:
            stock_rows = upsert_dataframe(conn, "stock_prices_daily", stocks_df, ["date", "symbol"])
            index_df = refresh_market_index_daily(conn, resolved_date)
            updated_stock = refresh_stock_month(conn, resolved_date, baseline)
            updated_market = refresh_market_month(conn, resolved_date)
            factor_rows = refresh_factor_scores(conn, resolved_date)
            regime_rows = refresh_regime_features(conn, resolved_date)
            status.update({
                "status": "ok",
                "resolved_date": resolved_date.isoformat(),
                "stock_rows": stock_rows,
                "index_rows": len(index_df),
                "updated_stock_monthly_rows": updated_stock,
                "updated_market_monthly_rows": updated_market,
                "updated_factor_score_rows": factor_rows,
                "updated_regime_feature_rows": regime_rows,
                "message": f"Inserted/updated real NSE EOD rows from {source}",
            })
            return_code = 0
    except Exception as exc:
        status.update({"status": "failed", "message": f"{type(exc).__name__}: {exc}"})
        return_code = 1
    finally:
        finished = dt.datetime.now(dt.timezone.utc)
        status["finished_at"] = finished.isoformat()
        conn.execute(
            """
            INSERT OR REPLACE INTO eod_refresh_runs
            (run_id, requested_date, resolved_date, status, stock_rows, index_rows, message, started_at, finished_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                status["run_id"], status["requested_date"], status.get("resolved_date"), status["status"],
                int(status.get("stock_rows") or 0), int(status.get("index_rows") or 0), status["message"],
                status["started_at"], status["finished_at"],
            ),
        )
        conn.commit()
        conn.close()
        write_status(status)
        print(json.dumps(status, indent=2, default=str))
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
