"""Merge the database's historical news features into the live RSS features.

The pipeline built its news features entirely from the live RSS fetch, which
returns seven months. `news_features_monthly` in the source database already
holds 56 months inside the backtest window, and `regime_features_monthly`
carries a `news_sentiment` column for the same 56. That data was collected,
stored, and then ignored.

The merged view prefers the live fetch for the months it covers, because it is
the same source the pipeline already used and is refreshed daily, and falls back
to the database for every earlier month. Each row keeps its own confidence
weight, so a month backed by one article is still discounted relative to one
backed by 271 -- merging the rows does not launder a thin month into a thick
one.
"""

from __future__ import annotations

import sqlite3

#: Columns the pipeline's news lookup expects.
_LOOKUP_FIELDS = (
    "news_sentiment",
    "negative_news_ratio",
    "risk_event_count",
    "article_count",
)


def load_historical(db_path: str, exclude_months: set[str] | None = None) -> list[dict]:
    """Read `news_features_monthly` in the shape the pipeline already uses.

    Months listed in `exclude_months` are skipped so a live RSS observation is
    never overwritten by a stored one.
    """
    if not db_path:
        return []
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return []
    try:
        present = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "news_features_monthly" not in present:
            return []
        cols = {r[1] for r in conn.execute("PRAGMA table_info(news_features_monthly)")}
        required = {
            "month", "monthly_news_sentiment", "monthly_negative_news_ratio",
            "monthly_risk_event_count", "news_article_count", "news_confidence",
        }
        if not required.issubset(cols):
            return []
        out: list[dict] = []
        for m, sent, neg, risk, count, conf in conn.execute(
            "SELECT month, monthly_news_sentiment, monthly_negative_news_ratio, "
            "       monthly_risk_event_count, news_article_count, news_confidence "
            "FROM news_features_monthly ORDER BY month"
        ):
            month = str(m)[:7]
            if exclude_months and month in exclude_months:
                continue
            if sent is None and neg is None and risk is None:
                continue
            out.append({
                "month": month,
                "sentiment_score": round(float(sent or 0.0), 4),
                "negative_ratio": round(float(neg or 0.0), 4),
                "risk_event_count": int(risk or 0),
                "article_count": int(count or 0),
                "news_confidence": round(float(conf or 0.0), 4),
            })
        return out
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def merge(live_rows: list[dict], historical_rows: list[dict]) -> tuple[list[dict], dict]:
    """Combine the two sources, live taking precedence for shared months.

    Returns the merged rows and a summary of what came from where, so the
    provenance is reported rather than assumed.
    """
    live_months = {str(r.get("month", ""))[:7] for r in live_rows}
    merged: dict[str, dict] = {}
    for r in historical_rows:
        merged[str(r.get("month", ""))[:7]] = dict(r)
    for r in live_rows:
        merged[str(r.get("month", ""))[:7]] = dict(r)

    rows = [merged[m] for m in sorted(merged)]
    from_hist = sum(1 for r in rows if str(r.get("month", ""))[:7] not in live_months)
    return rows, {
        "live_months": len(live_months),
        "historical_months": from_hist,
        "total_months": len(rows),
        "overlap_months": len(live_months & set(merged)),
        "precedence": "live RSS wins for any month both sources cover",
    }
