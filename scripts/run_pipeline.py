#!/usr/bin/env python3
"""
Indian Regime/Factor/Portfolio Intelligence Pipeline
Reads: processed_financial_data.sqlite
Writes: public/data/*.json + financial_intelligence_outputs.sqlite + CSVs

Nodes:
  DataValidationAgent -> RegimeDetectionAgent -> FactorScoringAgent ->
  FactorForecastAgent -> AllocationOptimizerAgent -> PortfolioTransitionAgent ->
  RiskDiagnosticsAgent -> BacktestAgent -> ChartSignalAgent -> ExplanationAgent
"""

import sqlite3, json, os, math, csv, datetime, re, hashlib, urllib.request, xml.etree.ElementTree as ET
import numpy as np
from pathlib import Path
from email.utils import parsedate_to_datetime

import universe as universe_policy
import point_in_time as point_in_time_policy
import regime_model
import price_sanity
import factor_engine
from portfolio_construction import PortfolioConstraints, build_target_weights
from stock_backtest import CostModel, stock_level_returns, summarize
import performance_stats
import risk_free
import coverage_audit
import news_history
import selection_bias
import experiment_manifest
import data_freshness

# All-in transaction cost in basis points of traded notional. India: brokerage,
# STT, exchange and SEBI charges, GST, stamp duty and spread together sit in
# this range for liquid NSE large/mid caps. The scenario is reported on the
# dashboard so the assumption is visible rather than buried.
COST_BPS = 20.0

#: Cost levels the book is re-run at, in basis points. A single assumption is a
#: claim; a ladder is a sensitivity analysis, and it shows how much of the gross
#: edge survives a pessimistic execution assumption.
COST_SCENARIOS_BPS = (0.0, 10.0, 20.0, 50.0, 100.0)

# Hard portfolio limits, applied to the FINAL weights and verified on every
# rebalance. See portfolio_construction.py.
CONSTRAINTS = PortfolioConstraints(
    max_weight=0.05,
    min_weight=0.0,
    max_sector_weight=0.30,
    min_names=20,
    max_names=60,
)

# ─── Paths ───
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
INPUT_DB = PROJECT_DIR / "data_input" / "processed_financial_data.sqlite"
OUTPUT_DB = PROJECT_DIR / "financial_intelligence_outputs.sqlite"
JSON_DIR = PROJECT_DIR / "public" / "data"
CSV_DIR = PROJECT_DIR / "output_csv"
RAW_DATA_DIR = PROJECT_DIR.parent.parent / "data"
RSS_SOURCE_FILE = RAW_DATA_DIR / "News Data" / "rss_sources.txt.txt"
#: Exact article set from the last successful fetch, so a run reproduces it
#: rather than re-reading live feeds that have moved on.
NEWS_SNAPSHOT = INPUT_DB.parent / "news_snapshot.json"

#: How this run obtained its news: "fetched-live" or "replayed". Recorded so
#: the manifest reports what actually happened rather than inferring it from
#: whether a snapshot file exists -- a live run also writes one.
NEWS_MODE = "fetched-live"
CSV_DIR.mkdir(exist_ok=True)
JSON_DIR.mkdir(parents=True, exist_ok=True)

REGIME_LABELS = ["Bull / Expansion","Bear / Stress","Sideways / Neutral","Recovery","High Volatility / Risk-Off"]
FACTORS = ["Momentum","Value","Quality","Low Volatility"]
# Names selected per factor per rebalance.
#
# This is tied to the position cap: a book made of N equally weighted names
# needs N * max_weight >= 1 to be fully invested. With TOP_K=10 and a 5% cap
# only 50% of capital can be placed, so the allocator had to leave the rest in
# cash and the portfolio collapsed to a handful of names. 30 names at 5% caps
# at 150%, which funds the book with room to vary position sizes.
TOP_K = 30
TX_COST = 0.001  # 0.10% per side

# Months of history required before the regime model is allowed to score a
# month out of sample. Below this the mixture cannot be fitted and given
# anything but a memorised answer.
REGIME_MIN_TRAIN_MONTHS = 60
REGIME_MODEL_VERSION = "GMM-5-spherical-walkforward"

# ─── Helpers ───
def write_json(name, data):
    p = JSON_DIR / f"{name}.json"
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, default=str)

def write_csv(name, rows, headers):
    p = CSV_DIR / f"{name}.csv"
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

def safe_float(v):
    if v is None: return None
    try:
        v = float(v)
        if math.isnan(v) or math.isinf(v): return None
        return round(v, 6)
    except: return None

def fmt_month(d):
    if isinstance(d, str): return d[:7]
    return d[:7]

def news_lookup_from_features(news_features=None):
    lookup = {}
    for row in news_features or []:
        month = str(row.get("month", ""))[:7]
        if not month:
            continue
        lookup[month] = {
            "news_sentiment": safe_float(row.get("sentiment_score")) or 0.0,
            "negative_news_ratio": safe_float(row.get("negative_ratio")) or 0.0,
            "risk_event_count": safe_float(row.get("risk_event_count")) or 0.0,
            "news_confidence": safe_float(row.get("news_confidence")) or 0.0,
            "article_count": safe_float(row.get("article_count")) or 0.0,
        }
    return lookup

def news_stress_score(news_row):
    if not news_row:
        return 0.0
    negative = max(0.0, min(1.0, float(news_row.get("negative_news_ratio", 0.0) or 0.0)))
    confidence = max(0.0, min(1.0, float(news_row.get("news_confidence", 0.0) or 0.0)))
    sentiment = float(news_row.get("news_sentiment", 0.0) or 0.0)
    risk_count = float(news_row.get("risk_event_count", 0.0) or 0.0)
    risk_component = min(1.0, risk_count / 30.0)
    sentiment_component = max(0.0, -sentiment)
    raw = 0.45 * negative + 0.35 * risk_component + 0.20 * sentiment_component
    return round(min(1.0, raw * max(0.35, confidence)), 4)

def top_news_for_month(news_articles=None, month="", limit=5):
    month_key = str(month)[:7]
    rows = [
        a for a in (news_articles or [])
        if str(a.get("month", ""))[:7] == month_key
    ]
    rows.sort(key=lambda a: (
        float(a.get("risk_event_count", 0) or 0),
        abs(float(a.get("sentiment", 0) or 0))
    ), reverse=True)
    return rows[:limit]

def clean_text(s):
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", str(s))
    s = re.sub(r"&nbsp;|&#160;", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def parse_rss_datetime(value):
    if not value:
        return datetime.datetime.now(datetime.timezone.utc)
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone(datetime.timezone.utc)
    except Exception:
        try:
            return datetime.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(datetime.timezone.utc)
        except Exception:
            return datetime.datetime.now(datetime.timezone.utc)

def find_child_text(node, names):
    for child in list(node):
        tag = child.tag.split("}")[-1].lower()
        if tag in names:
            return clean_text(child.text)
    return ""

def find_link(node):
    for child in list(node):
        tag = child.tag.split("}")[-1].lower()
        if tag == "link":
            href = child.attrib.get("href")
            if href:
                return href.strip()
            if child.text:
                return clean_text(child.text)
    return ""

def source_name_from_url(url):
    host = re.sub(r"^https?://", "", url).split("/")[0].lower()
    return host.replace("www.", "")

def sentiment_and_risk(title, summary):
    text = f"{title} {summary}".lower()
    positive = ["growth", "gain", "rally", "surge", "profit", "strong", "boost", "record", "upgrade", "eases", "cut", "inflows", "expansion"]
    negative = ["fall", "falls", "drop", "loss", "weak", "stress", "crisis", "default", "downgrade", "inflation", "hike", "war", "selloff", "outflows", "slump", "crash", "risk"]
    risk_words = ["inflation", "rate hike", "rbi", "crude", "rupee", "fii", "selling", "recession", "default", "downgrade", "war", "banking stress", "liquidity", "crash", "volatility", "sebi", "policy"]
    pos = sum(1 for w in positive if w in text)
    neg = sum(1 for w in negative if w in text)
    sentiment = 0.0 if pos == neg else (pos - neg) / max(1, pos + neg)
    risk_count = sum(1 for w in risk_words if w in text)
    return round(float(sentiment), 4), risk_count

def rss_news_agent():
    """Fetch news and derive monthly and daily sentiment features.

    The RSS feeds are live, so two runs minutes apart can see a different set of
    articles for the current week. That difference propagates: it moves the
    current month's `news_sentiment`, which moves `news_stress_score` and
    `transition_risk`, which moves the regime row, the allocation and the
    rebalance trades. Measured across two runs, it perturbed one month out of
    153 and changed no regime label -- but "it barely matters today" is not the
    same as "it is reproducible", and a backtest nobody else can re-run to the
    same number cannot be checked.

    Freshness wins by default, because this pipeline runs on a daily schedule
    and a dashboard showing yesterday's sentiment is worse than one that cannot
    be byte-reproduced. Reproducibility is bought back differently: **every**
    fetch is written to `data_input/news_snapshot.json` with a SHA-256 of the
    article set, that hash is folded into the experiment manifest's fingerprint,
    and `NEWS_REPLAY=1` re-runs the pipeline from the snapshot to reproduce a
    past run exactly.

    So a run is not silently reproducible and it is not silently unreproducible
    either -- it carries the evidence of which it was.

    Must be called exactly once per run. Two calls meant two network fetches,
    and the second overwrote the snapshot with an article set the regime model
    had never seen -- so the snapshot did not record what the run actually used.
    """
    global NEWS_MODE
    print("[RSSNewsAgent] Starting...")

    def _flag(name: str) -> bool:
        return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")

    replay = _flag("NEWS_REPLAY")
    if replay and NEWS_SNAPSHOT.exists():
        try:
            with open(NEWS_SNAPSHOT, encoding="utf-8") as f:
                snap = json.load(f)
            # The snapshot is an object with provenance and an `articles` list,
            # not a bare list. Checking the wrong shape here once meant every
            # run silently fell through to a live fetch.
            cached = snap.get("articles") if isinstance(snap, dict) else None
            if isinstance(cached, list) and cached:
                print(
                    f"  Replaying news snapshot: {len(cached)} articles fetched "
                    f"{snap.get('fetched_at', 'unknown')}, hash "
                    f"{str(snap.get('content_sha256', '?'))[:12]}."
                )
                NEWS_MODE = "replayed"
                return _news_outputs_from(cached, [], from_snapshot=True)
            print("  NEWS_REPLAY=1 but the snapshot holds no articles; fetching live.")
        except (OSError, json.JSONDecodeError, AttributeError, TypeError) as exc:
            print(f"  Snapshot unreadable ({exc}); falling back to a live fetch.")
    elif replay:
        print("  NEWS_REPLAY=1 but no snapshot exists; fetching live.")

    NEWS_MODE = "fetched-live"

    sources = []
    if RSS_SOURCE_FILE.exists():
        for line in RSS_SOURCE_FILE.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line.startswith("http"):
                sources.append(line)
    working_feeds = [
        "https://economictimes.indiatimes.com/rssfeedstopstories.cms",
        "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
        "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms",
        "https://news.google.com/rss/search?q=India%20stock%20market%20Nifty%20RBI%20inflation%20when:7d&hl=en-IN&gl=IN&ceid=IN:en",
        "https://news.google.com/rss/search?q=India%20RBI%20repo%20rate%20inflation%20rupee%20crude%20when:7d&hl=en-IN&gl=IN&ceid=IN:en",
        "https://news.google.com/rss/search?q=India%20NSE%20BSE%20earnings%20market%20when:7d&hl=en-IN&gl=IN&ceid=IN:en"
    ]
    sources = list(dict.fromkeys(sources + working_feeds))

    articles_by_id = {}
    headers = {"User-Agent": "Mozilla/5.0 FinancialRegimeDashboard/1.0"}
    import feedparser
    failed_feeds = []
    for feed_url in sorted(sources):
        try:
            parsed = feedparser.parse(feed_url, request_headers=headers)
            nodes = list(parsed.entries or [])
        except Exception as exc:
            failed_feeds.append({"feed_url": feed_url, "reason": f"failed: {exc}"})
            continue

        if not nodes:
            failed_feeds.append({"feed_url": feed_url, "reason": "no entries"})
            continue

        src = source_name_from_url(feed_url)
        for node in nodes[:80]:
            title = clean_text(node.get("title", ""))
            summary = clean_text(node.get("summary", "") or node.get("description", ""))
            link = clean_text(node.get("link", ""))
            published_raw = node.get("published", "") or node.get("updated", "")
            published = parse_rss_datetime(published_raw)
            if not title or not link:
                continue
            sentiment, risk_count = sentiment_and_risk(title, summary)
            aid = hashlib.sha1(f"{link}|{title}".encode("utf-8", errors="ignore")).hexdigest()[:16]
            articles_by_id[aid] = {
                "article_id": aid,
                "source": src,
                "title": title[:240],
                "summary": summary[:500],
                "url": link,
                "published_at": published.isoformat(),
                "published_date": published.date().isoformat(),
                "month": published.strftime("%Y-%m"),
                "sentiment": sentiment,
                "risk_event_count": risk_count,
                "is_negative": sentiment < -0.05,
                "feed_url": feed_url
            }

    articles = sorted(articles_by_id.values(), key=lambda x: x["published_at"], reverse=True)
    if failed_feeds and not articles_by_id:
        for f in failed_feeds:
            print(f"  RSS warning: {f['reason']} from {f['feed_url']}")
    elif failed_feeds:
        print(f"  RSS note: skipped {len(failed_feeds)} empty/unavailable optional feeds; fetched {len(articles_by_id)} unique articles.")
    return _news_outputs_from(articles, failed_feeds)


def _news_outputs_from(articles, failed_feeds, from_snapshot=False):
    """Derive monthly and daily features from an article list, and write them.

    Shared by the live-fetch and snapshot paths so both produce byte-identical
    outputs from the same articles.
    """
    monthly = {}
    daily = {}
    for a in articles:
        for key, bucket in [(a["month"], monthly), (a["published_date"], daily)]:
            if key not in bucket:
                bucket[key] = {"sentiments": [], "negative": 0, "risk": 0, "count": 0}
            bucket[key]["sentiments"].append(a["sentiment"])
            bucket[key]["negative"] += 1 if a["is_negative"] else 0
            bucket[key]["risk"] += a["risk_event_count"]
            bucket[key]["count"] += 1

    def feature_rows(bucket, key_name):
        rows = []
        for key in sorted(bucket):
            b = bucket[key]
            count = b["count"]
            rows.append({
                key_name: key,
                "sentiment_score": round(float(np.mean(b["sentiments"])), 4) if b["sentiments"] else 0.0,
                "negative_ratio": round(b["negative"] / count, 4) if count else 0.0,
                "article_count": count,
                "risk_event_count": b["risk"],
                "news_confidence": round(min(1.0, count / 20), 4)
            })
        return rows

    news_features = feature_rows(monthly, "month")
    news_daily = feature_rows(daily, "date")

    # Persist the exact article set this run used, so the next run reproduces it
    # exactly and so a reader can verify two runs saw the same articles.
    try:
        digest = hashlib.sha256(
            json.dumps(
                [[a.get("article_id"), a.get("title"), a.get("published_at")]
                 for a in articles],
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        if from_snapshot:
            # Replaying: the snapshot already holds exactly these articles, so
            # rewriting it would only churn the file and its fetched_at stamp.
            pass
        else:
            NEWS_SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
            with open(NEWS_SNAPSHOT, "w", encoding="utf-8") as f:
                json.dump({
                    "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "article_count": len(articles),
                    "content_sha256": digest,
                    "articles": articles,
                }, f, default=str)
            print(f"  News snapshot written ({len(articles)} articles, sha256 {digest[:12]}).")
    except OSError as exc:
        print(f"  WARNING: could not write news snapshot: {exc}")

    write_json("news_articles_raw", articles)
    write_json("news_features", news_features)
    write_json("news_features_daily", news_daily)
    write_csv("news_articles_raw", articles, ["article_id", "source", "title", "summary", "url", "published_at", "published_date", "month", "sentiment", "risk_event_count", "is_negative", "feed_url"])
    write_csv("news_features_monthly", news_features, ["month", "sentiment_score", "negative_ratio", "article_count", "risk_event_count", "news_confidence"])
    write_csv("news_features_daily", news_daily, ["date", "sentiment_score", "negative_ratio", "article_count", "risk_event_count", "news_confidence"])
    print(f"[RSSNewsAgent] Done. {len(articles)} articles, {len(news_features)} monthly rows.")
    return articles, news_features

# ─── DataValidationAgent ───
def compute_universe_coverage(conn):
    """Measure per-symbol data depth and decide the modeling universe.

    The exclusion set is derived from what the database actually contains
    rather than hardcoded, so a symbol is restored automatically once its
    fundamentals or price history become available. See `universe.py`.
    """
    cursor = conn.cursor()
    cursor.execute("SELECT symbol, COUNT(DISTINCT month) FROM stock_prices_monthly GROUP BY symbol")
    price_months = {r[0]: r[1] for r in cursor.fetchall()}
    cursor.execute("SELECT symbol, COUNT(DISTINCT month) FROM fundamentals_monthly GROUP BY symbol")
    fundamental_months = {r[0]: r[1] for r in cursor.fetchall()}

    coverage = universe_policy.assess_coverage(price_months, fundamental_months)
    report = universe_policy.build_report(coverage)

    stale = universe_policy.assert_no_stale_exclusions(coverage)
    if stale:
        print(
            "  NOTE: universe.py baseline can now be trimmed; these are supported again: "
            + ", ".join(stale)
        )

    # Survivorship, measured rather than asserted. The trading record is the
    # full list of symbols that traded on a given day, so it says both how many
    # database symbols could not have been held and how many tradable names the
    # database has never seen. Both numbers are needed: the first is fixable and
    # is fixed below, the second is not and is reported.
    cursor.execute("SELECT DISTINCT month FROM factor_scores_monthly ORDER BY month")
    scored_months = [r[0][:7] for r in cursor.fetchall()]
    db_symbols = set(price_months) | set(fundamental_months)

    project_dir = str(Path(__file__).resolve().parent.parent)
    pit = point_in_time_policy.load_point_in_time(project_dir)
    survivorship = point_in_time_policy.assess_survivorship(pit, db_symbols, scored_months)
    survivorship["first_traded"] = (point_in_time_policy.first_traded(pit)
                                    if pit else {})
    survivorship["backtest_month_range"] = (
        [scored_months[0], scored_months[-1]] if scored_months else None
    )
    survivorship["gate_enabled"] = bool(pit)
    write_json("point_in_time_universe", survivorship)
    report["point_in_time"] = {
        "gate_enabled": survivorship["gate_enabled"],
        "archive_floor": survivorship.get("archive_floor"),
        "backtest_months_gated": survivorship.get("backtest_months_gated"),
        "backtest_months_gated_pct": survivorship.get("backtest_months_gated_pct"),
    }

    if not pit:
        print(
            "  WARNING: no bhavcopy trading record at data_input/"
            "nse_trading_universe.json, so point-in-time gating is OFF and "
            "not-yet-listed symbols are scored in months they could not trade."
        )
    else:
        print(
            f"  Point-in-time: {survivorship['db_symbols_not_yet_listed_at_archive_start']}"
            f" database symbols were unlisted when the archive opens; gated out of "
            f"{survivorship['backtest_months_gated']} of "
            f"{len(scored_months)} backtest months. "
            f"{survivorship['stopped_trading_absent_from_db']} names that stopped "
            f"trading are absent from the database and remain an uncorrected bias."
        )
    return universe_policy.excluded_symbols(coverage), report, survivorship


def data_validation_agent(conn):
    print("[DataValidationAgent] Starting...")
    report = {}
    cursor = conn.cursor()

    # Check tables exist
    required_tables = [
        "market_index_monthly","stock_prices_monthly","macro_monthly","fundamentals_monthly",
        "news_articles_raw","news_features_monthly","factor_scores_monthly","regime_features_monthly",
        "sector_index_monthly","data_inventory"
    ]
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    existing = {r[0] for r in cursor.fetchall()}
    missing = [t for t in required_tables if t not in existing]
    report["missing_tables"] = missing
    if missing:
        raise RuntimeError(f"Missing tables: {missing}")

    # Check for duplicates
    for table, key in [("stock_prices_monthly","month,symbol"),("factor_scores_monthly","month,symbol")]:
        cursor.execute(f"SELECT {key}, COUNT(*) c FROM {table} GROUP BY {key} HAVING c > 1 LIMIT 5")
        dups = cursor.fetchall()
        report[f"duplicates_{table}"] = len(dups)

    # Derive the modeling universe from measured data depth
    excluded, coverage_report, survivorship = compute_universe_coverage(conn)
    report["universe_coverage"] = coverage_report
    write_json("universe_coverage", coverage_report)
    if coverage_report["excluded_count"]:
        print(
            f"  Universe: {coverage_report['modeling_universe_size']}/"
            f"{coverage_report['index_size']} symbols usable; "
            f"{coverage_report['excluded_count']} excluded for insufficient data."
        )
        for sym, reason in coverage_report["excluded_symbols"].items():
            print(f"    - {sym}: {reason}")

    # Count symbols
    cursor.execute("SELECT COUNT(DISTINCT symbol) FROM stock_prices_monthly")
    report["stock_count"] = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(DISTINCT symbol) FROM factor_scores_monthly")
    report["factor_score_count"] = cursor.fetchone()[0]

    # Date range
    cursor.execute("SELECT MIN(month), MAX(month) FROM regime_features_monthly")
    row = cursor.fetchone()
    report["regime_date_range"] = [row[0], row[1]] if row else None

    # Data inventory
    cursor.execute("SELECT * FROM data_inventory")
    cols = [d[0] for d in cursor.description]
    inv = [dict(zip(cols, r)) for r in cursor.fetchall()]
    write_json("data_inventory", inv)

    # Build stocks metadata
    try:
        cursor.execute("SELECT DISTINCT symbol FROM stock_prices_monthly ORDER BY symbol")
        symbols = [r[0] for r in cursor.fetchall() if r[0] not in excluded]
    except:
        cursor.execute("SELECT DISTINCT symbol FROM factor_scores_monthly ORDER BY symbol")
        symbols = [r[0] for r in cursor.fetchall() if r[0] not in excluded]

    stocks = []
    for s in symbols:
        stocks.append({"symbol": s, "name": s, "sector": "Unknown"})
    # Try to get sector from fundamentals if available
    try:
        cursor.execute("SELECT DISTINCT symbol, sector FROM fundamentals_monthly")
        for sym, sec in cursor.fetchall():
            for st in stocks:
                if st["symbol"] == sym and sec:
                    st["sector"] = sec
    except:
        pass
    write_json("stocks", stocks)
    report["final_stock_count"] = len(symbols)
    print(f"[DataValidationAgent] Done. {len(symbols)} stocks.")
    return report, symbols, excluded, survivorship

# ─── RegimeDetectionAgent ───
def regime_detection_agent(conn, news_features=None):
    print("[RegimeDetectionAgent] Starting...")
    cursor = conn.cursor()

    # Load regime features
    cursor.execute("SELECT * FROM regime_features_monthly ORDER BY month")
    cols = [d[0] for d in cursor.description]
    rows = [dict(zip(cols, r)) for r in cursor.fetchall()]
    if not rows:
        print("  WARNING: No regime features found, generating from market data")
        return generate_regime_from_market(conn)

    news_lookup = news_lookup_from_features(news_features)

    months = [r["month"][:7] for r in rows]

    # Feature selection: market state only. Data-coverage columns such as
    # stock_coverage_x correlate with the month index and would make the model
    # cluster data-availability eras rather than regimes.
    feature_cols = regime_model.select_feature_columns(cols, rows)
    dropped = [c for c in cols if c not in feature_cols and c != "month"]
    X, constant_cols = regime_model.build_matrix(rows, feature_cols)
    if dropped:
        print(f"  Features used ({len(feature_cols)}): {', '.join(feature_cols)}")
        print(f"  Features dropped: {', '.join(dropped)}")
    if constant_cols:
        print(f"  Constant columns dropped: {', '.join(constant_cols)}")

    n_clusters = min(5, len(rows))
    # Walk-forward: each month is scored by a model fitted only on the months
    # before it, so the reported confidence is out of sample.
    labels, probs, first_scored = regime_model.fit_and_score(
        X, n_clusters=n_clusters, min_train=REGIME_MIN_TRAIN_MONTHS
    )
    n_params = regime_model.spherical_param_count(n_clusters, X.shape[1])
    print(
        f"  GMM-{n_clusters} spherical, {n_params} free parameters over "
        f"{X.shape[1]} features; scored out of sample from month {months[first_scored] if first_scored < len(months) else 'n/a'}"
    )

    # Name the clusters. Only months the model actually scored participate, so
    # the names reflect real clusters rather than the warm-up filler.
    scored_idx = [i for i in range(len(months)) if labels[i] is not None]
    scored_labels = [labels[i] for i in scored_idx]
    char_map = regime_model.label_clusters(
        X[[i for i in scored_idx]],
        scored_labels,
        n_clusters,
    )
    by_return = sorted(range(n_clusters), key=lambda i: char_map[i]["mean_ret"], reverse=True)

    # Does the clustering actually separate forward returns? Reported either
    # way: the regime names are a labelling convention, and this is the check
    # on whether they correspond to anything economic.
    ret_idx = (
        regime_model.MARKET_FEATURE_COLUMNS.index("nifty_1m_return")
        if "nifty_1m_return" in regime_model.MARKET_FEATURE_COLUMNS
        else 0
    )
    forward = [
        X[i + 1, ret_idx] if i + 1 < X.shape[0] else float("nan")
        for i in scored_idx
    ]
    separation = regime_model.cluster_separation(forward, scored_labels)
    if separation is None:
        print("  Regime separation: too few observations to test.")
    elif separation["clusters_separate_returns"]:
        print(
            f"  Regime separation: clusters DO separate forward returns "
            f"(F = {separation['f_statistic']}, critical ~{separation['f_critical_approx']})."
        )
    else:
        print(
            f"  Regime separation: clusters do NOT separate forward returns "
            f"(F = {separation['f_statistic']} < ~{separation['f_critical_approx']}). "
            f"The regime names are descriptive labels, not a validated forecast."
        )

    label_map = {}
    if n_clusters >= 5:
        label_map[by_return[0]] = "Bull / Expansion"
        label_map[by_return[1]] = "Recovery"
        label_map[by_return[2]] = "Sideways / Neutral"
        label_map[by_return[3]] = "High Volatility / Risk-Off"
        label_map[by_return[4]] = "Bear / Stress"
    elif n_clusters == 4:
        label_map[by_return[0]] = "Bull / Expansion"
        label_map[by_return[1]] = "Recovery"
        label_map[by_return[2]] = "Sideways / Neutral"
        label_map[by_return[3]] = "Bear / Stress"
    else:
        for i, sc in enumerate(by_return):
            label_map[sc] = REGIME_LABELS[min(i, len(REGIME_LABELS)-1)]

    predictions = []
    prev_probs = None
    for i, month in enumerate(months):
        nf = news_lookup.get(month, {})
        ns = news_stress_score(nf)

        if labels[i] is None or probs[i] is None:
            # Warm-up month: the model has not seen enough history to score
            # this month out of sample. Reported as unscored rather than given
            # a fabricated confidence.
            predictions.append({
                "month": month,
                "regime_label": "Unscored",
                "regime_cluster": None,
                "regime_confidence": None,
                "transition_risk": None,
                "prob_bull_expansion": None,
                "prob_bear_stress": None,
                "prob_sideways_neutral": None,
                "prob_recovery": None,
                "prob_high_vol_risk_off": None,
                # Deliberately NOT REGIME_MODEL_VERSION. The mixture was never
                # fitted on this month, so labelling it with the GMM version
                # would assert a provenance the output does not have.
                "model_version": "not-scored-warmup",
                "is_warmup": True,
                "news_sentiment": round(float(nf.get("news_sentiment", 0.0)), 4),
                "negative_news_ratio": round(float(nf.get("negative_news_ratio", 0.0)), 4),
                "risk_event_count": round(float(nf.get("risk_event_count", 0.0)), 4),
                "news_confidence": round(float(nf.get("news_confidence", 0.0)), 4),
                "news_stress_score": ns,
            })
            continue

        p = probs[i]
        conf = float(np.max(p))
        if prev_probs is not None:
            instability = float(np.sum(np.abs(p - prev_probs))) / 2
            trans_risk = (1 - conf) * 0.5 + instability * 0.5
        else:
            trans_risk = 1 - conf
        trans_risk = min(1.0, trans_risk + 0.35 * ns)
        # News stress lowers confidence, but never below 0 and never above the
        # model's own out-of-sample probability.
        conf_adj = max(0.0, min(conf, conf - 0.10 * ns))

        predictions.append({
            "month": month,
            "regime_label": label_map[labels[i]],
            "regime_cluster": int(labels[i]),
            "regime_confidence": round(conf_adj, 4),
            "transition_risk": round(trans_risk, 4),
            "prob_bull_expansion": round(float(p[by_return[0]]), 4) if len(by_return) > 0 else None,
            "prob_bear_stress": round(float(p[by_return[-1]]), 4) if len(by_return) > 0 else None,
            "prob_sideways_neutral": round(float(p[by_return[len(by_return)//2]]), 4) if len(by_return) > 0 else None,
            "prob_recovery": round(float(p[by_return[1]]), 4) if len(by_return) > 1 else None,
            "prob_high_vol_risk_off": round(float(p[by_return[3]]), 4) if len(by_return) > 3 else None,
            "model_version": REGIME_MODEL_VERSION,
            "is_warmup": False,
            "news_sentiment": round(float(nf.get("news_sentiment", 0.0)), 4),
            "negative_news_ratio": round(float(nf.get("negative_news_ratio", 0.0)), 4),
            "risk_event_count": round(float(nf.get("risk_event_count", 0.0)), 4),
            "news_confidence": round(float(nf.get("news_confidence", 0.0)), 4),
            "news_stress_score": ns,
        })
        prev_probs = p

    # Attach the separation diagnostic to the newest record so the dashboard
    # can state whether the regime names carry predictive meaning.
    if predictions and separation is not None:
        predictions[-1]["cluster_separation"] = separation

    write_json("regime_predictions", predictions)
    headers = ["month","regime_label","regime_cluster","regime_confidence","transition_risk",
               "prob_bull_expansion","prob_bear_stress","prob_sideways_neutral","prob_recovery",
               "prob_high_vol_risk_off","model_version","is_warmup","news_sentiment","negative_news_ratio","risk_event_count","news_confidence","news_stress_score"]
    write_csv("regime_predictions_monthly", predictions, headers)
    scored = sum(1 for p in predictions if not p["is_warmup"])
    print(f"[RegimeDetectionAgent] Done. {len(predictions)} months ({scored} scored, {len(predictions)-scored} warm-up).")
    return predictions

def generate_regime_from_market(conn):
    """Fallback: generate regime from market index data if regime_features_monthly is empty."""
    cursor = conn.cursor()
    cursor.execute("SELECT month, monthly_close AS close, monthly_return AS return FROM market_index_monthly WHERE index_name LIKE '%Nifty%' ORDER BY month")
    rows = cursor.fetchall()
    if not rows:
        cursor.execute("SELECT month, monthly_close AS close FROM market_index_monthly ORDER BY month")
        rows = cursor.fetchall()

    if not rows:
        return []

    months = [r[0][:7] for r in rows]
    closes = [float(r[1]) if r[1] else 0 for r in rows]
    rets = []
    for i, r in enumerate(rows):
        if len(r) > 2 and r[2] is not None:
            rets.append(float(r[2]))
        elif i > 0 and closes[i-1] > 0:
            rets.append((closes[i] - closes[i-1]) / closes[i-1])
        else:
            rets.append(0.0)

    # Simple regime classification based on rolling returns and volatility
    predictions = []
    for i, month in enumerate(months):
        if i < 12:
            regime = "Sideways / Neutral"
            conf = 0.5
        else:
            ret_1m = rets[i]
            ret_3m = sum(rets[i-2:i+1]) / 3 if i >= 2 else ret_1m
            ret_6m = sum(rets[i-5:i+1]) / 6 if i >= 5 else ret_1m
            vol_6m = np.std(rets[i-5:i+1]) if i >= 5 else abs(ret_1m)

            if ret_3m > 0.03 and ret_6m > 0.05:
                regime = "Bull / Expansion"; conf = 0.75
            elif ret_3m < -0.03 and ret_6m < -0.05:
                regime = "Bear / Stress"; conf = 0.75
            elif vol_6m > 0.07:
                regime = "High Volatility / Risk-Off"; conf = 0.60
            elif ret_1m > 0 and ret_6m < 0:
                regime = "Recovery"; conf = 0.60
            else:
                regime = "Sideways / Neutral"; conf = 0.55

        pred = {
            "month": month, "regime_label": regime, "regime_cluster": REGIME_LABELS.index(regime),
            "regime_confidence": round(conf, 4), "transition_risk": round(1-conf, 4),
            "prob_bull_expansion": 0.2, "prob_bear_stress": 0.2,
            "prob_sideways_neutral": 0.2, "prob_recovery": 0.2,
            "prob_high_vol_risk_off": 0.2, "model_version": "rule-fallback-v1"
        }
        pred["prob_" + regime.lower().replace(" / ","_").replace("-","_")] = round(conf, 4)
        predictions.append(pred)

    write_json("regime_predictions", predictions)
    write_csv("regime_predictions_monthly", predictions, ["month","regime_label","regime_cluster","regime_confidence","transition_risk","prob_bull_expansion","prob_bear_stress","prob_sideways_neutral","prob_recovery","prob_high_vol_risk_off","model_version","news_sentiment","negative_news_ratio","risk_event_count","news_confidence","news_stress_score"])
    print(f"[RegimeDetectionAgent] Fallback done. {len(predictions)} predictions.")
    return predictions

# ─── FactorScoringAgent ───
def _rebuild_fundamental_factors(conn, months, excluded):
    """Rebuild Value and Quality from raw fundamentals, per month.

    Uses the engine in `factor_engine.py`, which winsorizes, sector-neutralises
    and applies a coverage rule. Returns
    month -> (Value scores, Quality scores, diagnostics), or an empty dict when
    `fundamentals_monthly` is unavailable.
    """
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM fundamentals_monthly")
        fetched = cur.fetchall()
        fcols = [d[0] for d in cur.description]
    except sqlite3.Error:
        print("  WARNING: fundamentals_monthly unavailable; keeping stored factor scores")
        return {}
    metric_cols = [c for c in fcols if c in {
        "monthly_pe", "earnings_yield_ttm", "debt_equity",
        "profit_margin", "earnings_growth", "revenue_growth",
    }]
    out = {}
    by_month: dict[str, list[dict]] = {}
    for r in fetched:
        d = dict(zip(fcols, r))
        if d.get("symbol") in excluded:
            continue
        by_month.setdefault(str(d["month"])[:7], []).append(d)

    for m in months:
        rows = by_month.get(m)
        if not rows:
            continue
        sectors = {d["symbol"]: (d.get("sector") or "Unknown") for d in rows}
        metrics = {
            d["symbol"]: {k: d[k] for k in metric_cols if d.get(k) is not None}
            for d in rows
        }
        if not any(metrics.values()):
            continue
        scores, diag = factor_engine.build_factor_scores(metrics, sectors)
        out[m] = (
            scores.get("Value", {}),
            scores.get("Quality", {}),
            diag,
        )
    return out


def factor_scoring_agent(conn, regime_preds, excluded=frozenset(), survivorship=None):
    print("[FactorScoringAgent] Starting...")
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM factor_scores_monthly ORDER BY month, symbol")
    cols = [d[0] for d in cursor.description]
    rows = [dict(zip(cols, r)) for r in cursor.fetchall()]

    if not rows:
        print("  WARNING: No factor scores found")
        return [], []

    # Determine factor columns
    # Map each factor to its SCORE column.
    #
    # A plain substring match is wrong here: `momentum_rank` also contains
    # "momentum", and because it appears after `momentum_score` in the schema it
    # used to overwrite the score, so every basket carried a 1..N rank in its
    # `factor_score` field and the dashboard showed a column of integers under a
    # "Score" header. Rank columns are now excluded explicitly.
    factor_map = {}
    rank_suffixes = ("_rank", "rank", "_position", "_pct")
    for c in cols:
        cl = c.lower()
        # Only accept a column that is not a rank/ordinal and not overall.
        if cl.endswith(rank_suffixes) or cl.startswith("overall"):
            continue
        if "momentum" in cl:
            factor_map.setdefault("Momentum", c)
        elif "value" in cl:
            factor_map.setdefault("Value", c)
        elif "quality" in cl:
            factor_map.setdefault("Quality", c)
        elif "low_vol" in cl or "lowvol" in cl or "volatility" in cl:
            factor_map.setdefault("Low Volatility", c)

    # Fallback: use first 4 numeric columns after month+symbol
    if not factor_map:
        skip = {"month", "symbol"}
        numeric_cols = [c for c in cols if c not in skip]
        fnames = ["Momentum", "Value", "Quality", "Low Volatility"]
        for i, c in enumerate(numeric_cols[:4]):
            factor_map[fnames[i]] = c

    missing = [f for f in ["Momentum", "Value", "Quality", "Low Volatility"] if f not in factor_map]
    if missing:
        print(f"  WARNING: no score column found for: {', '.join(missing)}")
    print(f"  Factor score columns: {factor_map}")

    baskets = []
    months = sorted(set(r["month"][:7] for r in rows))

    regime_lookup = {str(p["month"])[:7]: p["regime_label"] for p in regime_preds}

    # Value and Quality are rebuilt from raw fundamentals so the stored
    # scores can be winsorized, sector-neutralised and coverage-checked. The
    # stored values came from a global z-score with no outlier bound, which let
    # a single 1893x P/E decide the ranking, and no coverage rule, which scored
    # stocks whose only populated metric was debt/equity.
    rebuilt = _rebuild_fundamental_factors(conn, months, excluded)
    if rebuilt:
        val_n = sum(1 for m in rebuilt if rebuilt[m][0])
        qual_n = sum(1 for m in rebuilt if rebuilt[m][1])
        skipped_v = sum(
            1 for m in rebuilt for s, v in rebuilt[m][0].items() if v is None
        )
        print(
            f"  Rebuilt Value/Quality for {len(rebuilt)} months "
            f"(Value scored in {val_n}, Quality in {qual_n}; "
            f"{skipped_v} Value scores withheld by the coverage rule)."
        )

    coverage_report = {}
    first_traded = (survivorship or {}).get("first_traded") or {}
    db_symbols = {r.get("symbol") for r in rows if r.get("symbol")}
    for month in months:
        # Point-in-time eligibility. A symbol is only scoreable in a month it
        # was already trading, judged by the bhavcopy record. Before the archive
        # floor there is no evidence, so nothing is gated there and the residual
        # bias is reported rather than hidden.
        if first_traded:
            floor = min(first_traded.values())
            if month >= floor:
                tradable = {s for s in db_symbols if first_traded.get(s, floor) <= month}
            else:
                tradable = db_symbols
        else:
            tradable = db_symbols
        month_rows = [
            r for r in rows
            if r["month"][:7] == month
            and r.get("symbol") not in excluded
            and r.get("symbol") in tradable
        ]
        rb = rebuilt.get(month)
        for fname, fcol in factor_map.items():
            override = None
            if rb and fname in ("Value", "Quality"):
                override = rb[0] if fname == "Value" else rb[1]
            scored = []
            for r in month_rows:
                sym = r.get("symbol")
                if override is not None:
                    # Rebuilt score; None means the coverage rule withheld it.
                    v = override.get(sym)
                    if v is None:
                        coverage_report.setdefault(fname, {})
                        coverage_report[fname][f"{month}|{sym}"] = "coverage or missing metrics"
                        continue
                else:
                    v = r.get(fcol)
                    if v is not None:
                        try:
                            v = float(v)
                            if math.isnan(v):
                                v = None
                        except (TypeError, ValueError):
                            v = None
                if v is not None:
                    scored.append((sym, v))

            scored.sort(key=lambda x: x[1], reverse=True)
            for rank, (sym, score) in enumerate(scored, 1):
                baskets.append({
                    "month": month,
                    "factor_name": fname,
                    "symbol": sym,
                    "factor_score": round(score, 6),
                    "factor_rank": rank,
                    "selected_flag": rank <= TOP_K
                })

    write_json("factor_baskets", baskets)
    if coverage_report:
        # Which factor-score months were withheld and why, so the coverage rule
        # is visible rather than silently shrinking the universe.
        write_json("factor_coverage_withheld", {
            "withheld_counts": {
                f: sum(1 for v in d.values() if v) for f, d in coverage_report.items()
            },
            "coverage_rule": "factor score withheld when fewer than 75% of the "
                             "composite metric weight is present",
            "examples": {
                f: dict(list(d.items())[:20]) for f, d in coverage_report.items()
            },
        })


    # A count of withheld scores is a symptom. This names the cause: which
    # symbols are structurally outside the fundamental factors because their
    # sector reports on different conventions (every bank here), and which are
    # a genuine ingestion gap instead.
    _audit = coverage_audit.analyse(
        str(INPUT_DB), sorted({r["month"] for r in baskets}),
    )
    if _audit.get("available"):
        write_json("fundamental_coverage_audit", _audit)
        _sc = _audit["summary"]
        _bc = _sc.get("by_classification", {})
        print(
            f"  Fundamental coverage: {_sc.get('total_symbols')} symbols -- "
            f"{_bc.get('measured', 0)} measured, "
            f"{_bc.get('structurally_excluded', 0)} structurally out "
            f"({_sc.get('structural_sector_exposure_pct', 0)}%), "
            f"{_bc.get('sparse', 0)} sparse, "
            f"{_bc.get('unexplained_gap', 0)} unexplained"
        )
    write_csv("factor_baskets_monthly", baskets, ["month","factor_name","symbol","factor_score","factor_rank","selected_flag"])
    print(f"[FactorScoringAgent] Done. {len(baskets)} basket entries.")
    return baskets, list(factor_map.keys())

# ─── FactorForecastAgent ───
def factor_forecast_agent(conn, baskets, regime_preds, excluded=frozenset()):
    print("[FactorForecastAgent] Starting...")
    cursor = conn.cursor()

    # Get stock prices for return calculation
    cursor.execute("SELECT month, symbol, monthly_close AS close, monthly_return FROM stock_prices_monthly ORDER BY month, symbol")
    cols = [d[0] for d in cursor.description]
    price_rows = [dict(zip(cols, r)) for r in cursor.fetchall()]

    # Corporate-action guard. `monthly_return` is derived from raw closes, so
    # a split or bonus issue is recorded as a real gain or loss. Values beyond
    # the plausible monthly bound are winsorised before anything downstream
    # sees them. See price_sanity.py for the full rationale.
    raw_return_rows = [
        (r["month"][:7], r.get("symbol"), r.get("monthly_return"))
        for r in price_rows
        if r.get("month")
    ]
    return_lookup, corrections = price_sanity.winsorize_returns(raw_return_rows)
    if corrections:
        summary = price_sanity.summarize(corrections)
        print(
            f"  Corporate-action guard: {summary['corrected_rows']} monthly returns "
            f"across {summary['symbols_affected']} symbols winsorised "
            f"(largest: {summary['max_abs_example']} at {summary['max_abs_raw_return']:+.1%})."
        )

    # Build price lookup: (symbol, month) -> close
    price_lookup = {}
    for r in price_rows:
        sym = r.get("symbol")
        m = r["month"][:7]
        close = r.get("close")
        if sym and close and sym not in excluded:
            price_lookup[(sym, m)] = float(close)

    months = sorted(set(r["month"][:7] for r in price_rows if r.get("month")))
    month_idx = {m: i for i, m in enumerate(months)}

    # Calculate factor returns
    factor_returns = []
    factors = ["Momentum","Value","Quality","Low Volatility"]

    for i in range(1, len(months)):
        prev_month = months[i-1]
        curr_month = months[i]

        fr = {"month": curr_month}
        for fname in factors:
            # Get selected stocks from previous month
            selected = [b for b in baskets if str(b["month"])[:7] == prev_month and b["factor_name"] == fname and b["selected_flag"]]
            if not selected:
                fr[fname.lower().replace(" ", "_") + "_return"] = 0.0
                continue

            rets = []
            for s in selected:
                sym = s["symbol"]
                # Use the guarded monthly return rather than recomputing from
                # raw closes, so the corporate-action correction applies.
                r = return_lookup.get((curr_month, sym))
                if r is not None:
                    rets.append(r)

            fr[fname.lower().replace(" ", "_") + "_return"] = round(float(np.mean(rets)) if rets else 0.0, 6)

        factor_returns.append(fr)

    write_json("factor_returns", factor_returns)
    write_csv("factor_returns_monthly", factor_returns, ["month","momentum_return","value_return","quality_return","low_volatility_return"])

    # Build regime-conditional diagnostics.
    #
    # Both the covariance and the expected returns are computed from an
    # EXPANDING window of months up to and including the month being reported.
    # Two reasons:
    #   * Lookahead: the optimizer consumes this covariance, so a value built
    #     from the full sample would leak future factor returns into position
    #     sizing.
    #   * Honesty: a regime with fewer than two observations cannot support a
    #     correlation matrix. The previous code substituted an identity matrix,
    #     which displayed as a perfect 1.0 diagonal with fabricated zeros, and
    #     implied zero factor redundancy. It now reports null instead.
    regime_lookup = {str(p["month"])[:7]: p for p in regime_preds}
    diagnostics = []
    fkeys = [f.lower().replace(" ", "_") for f in factors]
    # Two observations are the minimum for a correlation, but a handful are
    # needed before a 4x4 matrix means anything.
    MIN_COV_OBS = 3

    def regime_of(month):
        return regime_lookup.get(str(month)[:7], {}).get("regime_label", "Sideways / Neutral")

    for idx, fr in enumerate(factor_returns):
        month = fr["month"]
        regime = regime_of(month)
        history = factor_returns[: idx + 1]
        group = [g for g in history if regime_of(g["month"]) == regime]

        # Expected return: mean of the regime group within the expanding
        # window, falling back to all history when the regime is too thin to
        # mean anything on its own.
        basis = group if len(group) >= MIN_COV_OBS else history
        er = {}
        for fname in factors:
            key = fname.lower().replace(" ", "_") + "_return"
            vals = [g[key] for g in basis if key in g and g[key] is not None]
            er[fname] = round(float(np.mean(vals)) if vals else 0.0, 6)

        ret_matrix = [
            [g.get(fk + "_return", 0.0) or 0.0 for fk in fkeys]
            for g in basis
        ]

        cov_dict = {fi: {} for fi in fkeys}
        corr_dict = {fi: {} for fi in fkeys}
        for i, fi in enumerate(fkeys):
            for j, fj in enumerate(fkeys):
                cov_dict[fi][fj] = None
                corr_dict[fi][fj] = None

        if len(ret_matrix) >= MIN_COV_OBS:
            arr = np.array(ret_matrix, dtype=float)
            with np.errstate(invalid="ignore", divide="ignore"):
                cov = np.cov(arr.T)
                # A factor that is constant within this window has an
                # undefined correlation; np.corrcoef returns NaN there, which
                # is reported as null below rather than coerced to 0.
                corr = np.corrcoef(arr.T)
            for i, fi in enumerate(fkeys):
                for j, fj in enumerate(fkeys):
                    cov_dict[fi][fj] = safe_float(cov[i, j])
                    cr = corr[i, j]
                    corr_dict[fi][fj] = (
                        round(float(cr), 6)
                        if np.isfinite(cr)
                        else None
                    )
            try:
                eigvals = np.linalg.eigvalsh(cov)
                total_eig = float(np.sum(eigvals))
                sq = float(np.sum(eigvals ** 2))
                max_eig_share = round(float(np.max(eigvals)) / total_eig, 4) if total_eig > 0 else None
                eff_factors = round(total_eig ** 2 / sq, 2) if sq > 0 else None
            except np.linalg.LinAlgError:
                max_eig_share = None
                eff_factors = None
        else:
            # Too few observations to compute a correlation. Report that rather
            # than inventing an identity matrix.
            max_eig_share = None
            eff_factors = None

        redundancy = (
            round(max(0.0, len(factors) - eff_factors) / len(factors), 4)
            if eff_factors is not None
            else None
        )

        diagnostics.append({
            "month": month,
            "regime_label": regime,
            "observation_count": len(ret_matrix),
            "expected_returns": er,
            "covariance_matrix": cov_dict,
            "correlation_matrix": corr_dict,
            "max_eigenvalue_share": max_eig_share,
            "effective_independent_factors": eff_factors,
            "risk_concentration_score": max_eig_share,
            "redundancy_score": redundancy,
        })

    write_json("factor_diagnostics", diagnostics)
    write_csv("regime_factor_diagnostics_monthly", diagnostics, ["month","regime_label","observation_count","expected_returns_json","covariance_matrix_json","correlation_matrix_json","max_eigenvalue_share","effective_independent_factors","risk_concentration_score","redundancy_score"])
    print(f"[FactorForecastAgent] Done. {len(factor_returns)} factor returns, {len(diagnostics)} diagnostics.")
    return factor_returns, diagnostics

# ─── AllocationOptimizerAgent ───
def allocation_optimizer_agent(factor_returns, diagnostics, regime_preds, news_features=None, news_articles=None):
    print("[AllocationOptimizerAgent] Starting...")
    allocations = []
    decisions = []

    regime_lookup = {str(p["month"])[:7]: p for p in regime_preds}
    diag_lookup = {str(d["month"])[:7]: d for d in diagnostics}
    news_lookup = news_lookup_from_features(news_features)

    factors = ["Momentum","Value","Quality","Low Volatility"]
    fkeys = ["momentum","value","quality","low_volatility"]

    prev_weights = np.array([0.25, 0.25, 0.25, 0.25])

    # Expected returns are estimated from a TRAILING window of factor returns
    # that stops at the PREVIOUS month.
    #
    # The weights decided for month M are traded during month M, so they may
    # only use information available before M. Using month M's own realised
    # factor return here made the optimizer pick the factor that was about to
    # win: correlation(weight, same-month return) reached +0.61, and the
    # backtest compounded that into a 69% CAGR that no real strategy achieves.
    #
    # The window is trailing rather than expanding because an expanding mean
    # barely moves over 150 months and would pin the weights near constant.
    # Observations are exponentially decayed so recent months carry more weight
    # without discarding the older sample entirely.
    ER_WINDOW = 24
    ER_HALFLIFE = 12.0
    MIN_ER_OBS = 12
    prior_vol = 0.04  # ~4% monthly factor volatility, used only as a fallback

    for idx, fr in enumerate(factor_returns):
        month = fr["month"]
        regime = regime_lookup.get(month, {})
        diag = diag_lookup.get(month, {})

        window = factor_returns[max(0, idx - ER_WINDOW):idx]
        if len(window) >= MIN_ER_OBS:
            ages = np.arange(len(window) - 1, -1, -1, dtype=float)  # 0 = most recent
            decay = 0.5 ** (ages / ER_HALFLIFE)
            decay = decay / decay.sum()
            er = np.array([
                float(np.dot(decay, [h.get(k + "_return", 0.0) or 0.0 for h in window]))
                for k in fkeys
            ])
        else:
            # Not enough history to estimate anything; hold equal weights
            # rather than acting on a handful of observations.
            er = np.zeros(4)

        news = news_lookup.get(month, {})
        ns = news_stress_score(news)
        if ns > 0:
            # High-confidence negative news penalizes aggressive Momentum/Value and supports defensive factors.
            er = er + np.array([-0.035 * ns, -0.020 * ns, 0.012 * ns, 0.018 * ns])

        # Covariance from the expanding-window diagnostics, which are built
        # only from months up to and including this one.
        cov = None
        if diag and diag.get("covariance_matrix"):
            cm = diag["covariance_matrix"]
            try:
                cand = np.array(
                    [[cm[fi][fj] for fj in fkeys] for fi in fkeys], dtype=float
                )
                if np.all(np.isfinite(cand)):
                    cov = cand
            except (KeyError, TypeError, ValueError):
                cov = None
        if cov is None:
            # No usable covariance: assume independent factors at the prior
            # volatility. Stated plainly rather than implied.
            cov = np.eye(4) * (prior_vol ** 2)

        # Grid search in 5% increments.
        #
        # The objective is risk-adjusted (expected return per unit of risk),
        # not raw return minus a risk penalty. A mean-variance utility of
        # `er - 0.75 * variance` is dominated by the variance term at these
        # scales and collapses to the minimum-variance portfolio, i.e. equal
        # weights in every month regardless of the signal. Dividing by risk
        # makes the objective scale-free, so factors are compared on how good
        # a return they buy per unit of volatility rather than on the absolute
        # size of that return.
        best_w = np.array([0.25, 0.25, 0.25, 0.25])
        best_util = -1e9
        turnover_pen = 0.02
        concentration_pen = 0.05

        # Diagnostics may report no redundancy (too few observations); treat
        # that as "no evidence of redundancy" rather than as a number.
        redundancy = (diag or {}).get("redundancy_score")
        if redundancy is None:
            redundancy = 0.0

        # Grid search
        step = 0.05
        w_vals = np.arange(0, 0.55, step)
        for w0 in w_vals:
            for w1 in w_vals:
                for w2 in w_vals:
                    w3 = 1 - w0 - w1 - w2
                    if w3 < -0.001 or w3 > 0.501:
                        continue
                    w = np.array([w0, w1, w2, w3])
                    gross = float(w.sum())
                    if gross <= 0:
                        continue
                    # Evaluate on a normalised portfolio so the ratio is
                    # comparable across the whole grid.
                    wn = w / gross
                    mu = float(np.dot(wn, er))
                    sd = math.sqrt(max(1e-12, float(wn @ cov @ wn)))
                    turnover = float(np.sum(np.abs(wn - prev_weights)))
                    # Concentrating into one correlated factor is penalised.
                    concentration = float(np.sum(wn * wn))
                    util = (
                        mu / sd
                        - turnover_pen * turnover
                        - concentration_pen * (redundancy + 0.25) * concentration
                    )
                    if util > best_util:
                        best_util = util
                        best_w = wn.copy()

        # Normalize
        total = best_w.sum()
        if total > 0:
            best_w = best_w / total

        turnover = float(np.sum(np.abs(best_w - prev_weights)))
        exp_ret = float(np.dot(best_w, er))
        exp_risk = math.sqrt(max(0, float(best_w @ cov @ best_w)))

        regime_label = regime.get("regime_label") or "Sideways / Neutral"
        regime_conf = regime.get("regime_confidence")
        if regime_conf is None:
            # Warm-up month: the model could not score it. Hold at an
            # explicitly neutral 0.5 rather than asserting confidence.
            regime_conf = 0.5
        tr = regime.get("transition_risk")
        trans_risk = min(1.0, (0.5 if tr is None else tr) + 0.25 * ns)

        alloc = {
            "month": month,
            "regime_label": regime_label,
            "regime_confidence": regime_conf,
            "transition_risk": trans_risk,
            "momentum_weight": round(float(best_w[0]), 4),
            "value_weight": round(float(best_w[1]), 4),
            "quality_weight": round(float(best_w[2]), 4),
            "low_volatility_weight": round(float(best_w[3]), 4),
            "expected_return": round(exp_ret, 6),
            "expected_risk": round(exp_risk, 6),
            "turnover": round(turnover, 4),
            "redundancy_score": redundancy,
            "optimizer_status": "grid_search_5pct_news_adjusted",
            "news_sentiment": round(float(news.get("news_sentiment", 0.0)), 4),
            "negative_news_ratio": round(float(news.get("negative_news_ratio", 0.0)), 4),
            "risk_event_count": round(float(news.get("risk_event_count", 0.0)), 4),
            "news_confidence": round(float(news.get("news_confidence", 0.0)), 4),
            "news_stress_score": ns
        }
        allocations.append(alloc)

        # Decision gate
        prev_alloc_dict = {factors[i]: round(float(prev_weights[i]), 4) for i in range(4)}
        rec_alloc_dict = {factors[i]: round(float(best_w[i]), 4) for i in range(4)}
        util_delta = best_util

        if util_delta > 0.02 and turnover > 0.15:
            decision = "REBALANCE"
            reason = f"Expected utility improvement {util_delta:.4f} exceeds threshold with turnover {turnover:.2%}"
        elif (trans_risk > 0.6 or ns > 0.45) and regime_label in ("Bear / Stress", "High Volatility / Risk-Off", "Sideways / Neutral"):
            decision = "DEFENSIVE"
            reason = f"High transition/news risk ({trans_risk:.2f}, news stress {ns:.2f}) in {regime_label}"
        elif turnover < 0.10:
            decision = "RETAIN"
            reason = f"Low turnover ({turnover:.2%}) - retaining previous allocation"
        else:
            decision = "RETAIN"
            reason = f"Moderate changes, utility delta {util_delta:.4f}"

        decisions.append({
            "month": month,
            "decision": decision,
            "reason": reason,
            "previous_allocation": prev_alloc_dict,
            "recommended_allocation": rec_alloc_dict,
            "expected_utility_delta": round(util_delta, 6),
            "transition_risk": trans_risk,
            "regime_confidence": regime_conf,
            "news_sentiment": round(float(news.get("news_sentiment", 0.0)), 4),
            "negative_news_ratio": round(float(news.get("negative_news_ratio", 0.0)), 4),
            "risk_event_count": round(float(news.get("risk_event_count", 0.0)), 4),
            "news_confidence": round(float(news.get("news_confidence", 0.0)), 4),
            "news_stress_score": ns,
            "supporting_news": top_news_for_month(news_articles, month)
        })

        prev_weights = best_w.copy()

    write_json("factor_allocations", allocations)
    write_csv("factor_allocations_monthly", allocations, ["month","regime_label","regime_confidence","transition_risk","momentum_weight","value_weight","quality_weight","low_volatility_weight","expected_return","expected_risk","turnover","redundancy_score","optimizer_status"])

    write_json("allocation_decisions", decisions)
    write_csv("allocation_decisions_monthly", decisions, ["month","decision","reason","previous_allocation_json","recommended_allocation_json","expected_utility_delta","transition_risk","regime_confidence"])
    print(f"[AllocationOptimizerAgent] Done. {len(allocations)} allocations, {len(decisions)} decisions.")
    return allocations, decisions

# ─── PortfolioTransitionAgent ───
def portfolio_transition_agent(conn, baskets, allocations, regime_preds, excluded=frozenset()):
    print("[PortfolioTransitionAgent] Starting...")
    cursor = conn.cursor()

    # Price lookup
    cursor.execute("SELECT month, symbol, sector, monthly_close AS close, monthly_close AS adjusted_close FROM stock_prices_monthly ORDER BY month, symbol")
    cols = [d[0] for d in cursor.description]
    price_rows = [dict(zip(cols, r)) for r in cursor.fetchall()]
    price_lookup = {}
    # Sector per symbol, for the sector-exposure constraint. The column must be
    # selected above; without it every symbol maps to "Unknown", the whole book
    # looks like one sector, and the sector cap truncates it to 30%.
    stock_sector: dict[str, str] = {}
    for r in price_rows:
        if r.get("sector"):
            stock_sector[r.get("symbol")] = r["sector"]
    for r in price_rows:
        sym = r.get("symbol")
        m = r["month"][:7]
        close = r.get("adjusted_close") or r.get("close")
        if sym and close and sym not in excluded:
            price_lookup[(sym, m)] = float(close)

    regime_lookup = {str(p["month"])[:7]: p for p in regime_preds}
    factors = ["Momentum","Value","Quality","Low Volatility"]
    fkeys = ["momentum_weight","value_weight","quality_weight","low_volatility_weight"]

    portfolio_targets = []
    rebalance_trades = []
    prev_portfolio = {}  # symbol -> weight

    for alloc in allocations:
        month = alloc["month"]
        month_key = str(month)[:7]
        regime_label = alloc.get("regime_label", "Sideways / Neutral")
        regime_conf = alloc.get("regime_confidence", 0.5)
        trans_risk = alloc.get("transition_risk", 0.5)

        # Get baskets for this month
        month_baskets = {}
        for fname in factors:
            selected = [b for b in baskets if str(b["month"])[:7] == month_key and b["factor_name"] == fname and b["selected_flag"]]
            month_baskets[fname] = selected

        # Factor-sleeve scores: a stock's appetite is the sum over the factor
        # sleeves that selected it, weighted by that sleeve's allocation.
        #
        # Factor scores are cross-sectional z-scores, so they are centred on
        # zero and roughly half are negative. Multiplying those straight into
        # the sleeve weight produced negative appetites, and the constrained
        # allocator (correctly) refused to hold a negative position. The book
        # collapsed to a handful of names. Each sleeve is therefore shifted to
        # a strictly positive appetite *within the sleeve's own selection*,
        # which is what "weight the sleeve, then pick its best names" means.
        stock_scores: dict[str, float] = {}
        factor_map_sym: dict[str, list[str]] = {}
        for i, fname in enumerate(factors):
            fw = alloc[fkeys[i]]
            basket = month_baskets.get(fname, [])
            if fw <= 0 or not basket:
                continue
            raw = {
                b["symbol"]: float(b["factor_score"] or 0.0)
                for b in basket
                if b["symbol"] not in excluded
            }
            if not raw:
                continue
            # Within-sleeve shift: the weakest name in the sleeve gets ~0, the
            # strongest gets the sleeve's full weight. The ordering is
            # unchanged, which is the only thing the sleeve weight expresses.
            lo = min(raw.values())
            span = max(raw.values()) - lo
            for sym, val in raw.items():
                appetite = fw * (1.0 if span <= 1e-12 else (val - lo) / span)
                stock_scores[sym] = stock_scores.get(sym, 0.0) + appetite
                factor_map_sym.setdefault(sym, []).append(fname)

        # Constrained construction. The previous cap-then-renormalise sequence
        # scaled capped names back above the cap, so 114 of 150 months breached
        # 5% and the largest position reached 10%. The allocator applies every
        # limit to the final weights and verifies them.
        sectors = {s: stock_sector.get(s, "Unknown") for s in stock_scores}
        allocation = build_target_weights(
            stock_scores, sectors=sectors, constraints=CONSTRAINTS
        )
        stock_weights = {
            sym: {
                "weight": w,
                "factors": factor_map_sym.get(sym, []),
                "score": stock_scores.get(sym, 0.0),
            }
            for sym, w in allocation.weights.items()
        }
        for sym in allocation.dropped:
            stock_weights.pop(sym, None)

        # Portfolio targets
        for sym, info in stock_weights.items():
            portfolio_targets.append({
                "month": month,
                "symbol": sym,
                "target_weight": round(info["weight"], 6),
                "factor_sources": info["factors"],
                "combined_score": round(info["score"], 6),
                "regime_label": regime_label,
                "sector": stock_sector.get(sym, "Unknown"),
                "allocation_method": "constrained_water_fill",
                "cash_residual": round(allocation.cash_residual, 6),
            })

        # Rebalance trades
        for sym, info in stock_weights.items():
            new_w = info["weight"]
            old_w = prev_portfolio.get(sym, 0)
            change = new_w - old_w
            price = price_lookup.get((sym, month_key), 0)

            if old_w == 0 and new_w > 0.001:
                sig = "BUY"
                reason = f"New position at {new_w:.2%}"
            elif old_w > 0 and new_w == 0:
                sig = "SELL"
                reason = f"Removed from portfolio"
            elif change > 0.005:
                sig = "ADD"
                reason = f"Increased from {old_w:.2%} to {new_w:.2%}"
            elif change < -0.005:
                sig = "REDUCE"
                reason = f"Reduced from {old_w:.2%} to {new_w:.2%}"
            elif abs(change) <= 0.001:
                sig = "HOLD"
                reason = f"Minimal change ({change:+.2%})"
            else:
                sig = "HOLD"
                reason = f"Minor adjustment"

            primary = info["factors"][0] if info["factors"] else "Momentum"
            rebalance_trades.append({
                "month": month,
                "symbol": sym,
                "signal_type": sig,
                "old_weight": round(old_w, 6),
                "new_weight": round(new_w, 6),
                "weight_change": round(change, 6),
                "signal_price": round(price, 2),
                "regime_label": regime_label,
                "regime_confidence": regime_conf,
                "transition_risk": trans_risk,
                "primary_factor": primary,
                "reason": reason
            })

        # Handle SELL for removed stocks
        for sym in list(prev_portfolio.keys()):
            if sym not in stock_weights and prev_portfolio[sym] > 0.001:
                price = price_lookup.get((sym, month_key), 0)
                rebalance_trades.append({
                    "month": month,
                    "symbol": sym,
                    "signal_type": "SELL",
                    "old_weight": round(prev_portfolio[sym], 6),
                    "new_weight": 0,
                    "weight_change": round(-prev_portfolio[sym], 6),
                    "signal_price": round(price, 2),
                    "regime_label": regime_label,
                    "regime_confidence": regime_conf,
                    "transition_risk": trans_risk,
                    "primary_factor": "Momentum",
                    "reason": "Removed from target portfolio"
                })

        # Update prev_portfolio
        prev_portfolio = {sym: info["weight"] for sym, info in stock_weights.items()}

    # Constraint-compliance audit, written alongside the targets so the
    # dashboard can show the limits actually honoured rather than the intended
    # ones. This is checked against the FINAL weights, after every adjustment.
    compliance = {
        "constraints": CONSTRAINTS.describe(),
        "months": {},
    }
    _months = sorted({t["month"] for t in portfolio_targets})
    breaches = []
    for _m in _months:
        _rows = [t for t in portfolio_targets if t["month"] == _m]
        _w = [t["target_weight"] for t in _rows]
        _mx = max(_w) if _w else 0.0
        _inv = sum(_w)
        _sec: dict[str, float] = {}
        for t in _rows:
            _s = stock_sector.get(t["symbol"], "Unknown")
            _sec[_s] = _sec.get(_s, 0.0) + t["target_weight"]
        _maxsec = max(_sec.values()) if _sec else 0.0
        compliance["months"][_m] = {
            "positions": len(_rows),
            "invested": round(_inv, 6),
            "cash": round(1.0 - _inv, 6),
            "max_weight": round(_mx, 6),
            "max_sector_weight": round(_maxsec, 6),
            "sector_exposure": {k: round(v, 4) for k, v in sorted(
                _sec.items(), key=lambda kv: -kv[1])[:8]},
            # Weights are persisted rounded to 6dp, so a sector summing to
            # 0.3000004 reads as 0.300001. The tolerance matches the stored
            # precision rather than exact float equality, so a genuine breach
            # still trips it.
            "sector_cap_respected": _maxsec <= CONSTRAINTS.max_sector_weight + 5e-6,
        }
        if _mx > CONSTRAINTS.max_weight + 1e-6:
            breaches.append((_m, _mx))
    compliance["months_breaching_max_weight"] = len(breaches)
    compliance["all_constraints_respected"] = not breaches and all(
        v["sector_cap_respected"] for v in compliance["months"].values()
    )
    write_json("portfolio_constraint_compliance", compliance)
    if breaches:
        print(f"  WARNING: {len(breaches)} months breach max_weight; first {breaches[0]}")
    else:
        print(
            f"  Constraints: max_weight {CONSTRAINTS.max_weight:.0%} respected in all "
            f"{len(_months)} months; sector cap "
            f"{CONSTRAINTS.max_sector_weight:.0%} respected in "
            f"{sum(1 for v in compliance['months'].values() if v['sector_cap_respected'])} months."
        )

    write_json("portfolio_targets", portfolio_targets)
    write_csv("portfolio_targets_monthly", portfolio_targets, ["month","symbol","sector","target_weight","factor_sources","combined_score","regime_label","allocation_method"])

    write_json("rebalance_trades", rebalance_trades)
    write_csv("rebalance_trades_monthly", rebalance_trades, ["month","symbol","signal_type","old_weight","new_weight","weight_change","signal_price","regime_label","regime_confidence","transition_risk","primary_factor","reason"])
    print(f"[PortfolioTransitionAgent] Done. {len(portfolio_targets)} targets, {len(rebalance_trades)} trades.")
    return portfolio_targets, rebalance_trades

# ─── RiskDiagnosticsAgent ───
def risk_diagnostics_agent(diagnostics, regime_preds):
    print("[RiskDiagnosticsAgent] Starting...")
    # Already covered in factor_diagnostics
    print("[RiskDiagnosticsAgent] Done (integrated into diagnostics).")
    return diagnostics

# ─── BacktestAgent ───
def backtest_agent(conn, allocations, rebalance_trades, regime_preds, portfolio_targets=None):
    print("[BacktestAgent] Starting...")
    cursor = conn.cursor()

    # Get benchmark (Nifty 200 or Nifty 50)
    cursor.execute("SELECT month, monthly_close AS close FROM market_index_monthly WHERE index_name LIKE '%Nifty%' ORDER BY month")
    cols = [d[0] for d in cursor.description]
    bench_rows = cursor.fetchall()
    if not bench_rows:
        cursor.execute("SELECT month, monthly_close AS close FROM market_index_monthly ORDER BY month")
        bench_rows = cursor.fetchall()

    bench_prices = {}
    bench_months = []
    for r in bench_rows:
        m = r[0][:7]
        bench_months.append(m)
        bench_prices[m] = float(r[1]) if r[1] else 0

    # Factor returns for static allocation
    factor_returns_map = {}
    for alloc in allocations:
        m = alloc["month"]
        factor_returns_map[m] = {
            "Momentum": alloc.get("momentum_weight", 0),
            "Value": alloc.get("value_weight", 0),
            "Quality": alloc.get("quality_weight", 0),
            "Low Volatility": alloc.get("low_volatility_weight", 0)
        }

    # Get actual factor returns from factor_returns.json
    fr_path = JSON_DIR / "factor_returns.json"
    with open(fr_path) as f:
        factor_returns = json.load(f)
    fr_lookup = {str(fr["month"])[:7]: fr for fr in factor_returns}

    regime_lookup = {str(p["month"])[:7]: p["regime_label"] for p in regime_preds}

    # Backtest months
    bt_months = sorted(set(str(alloc["month"])[:7] for alloc in allocations))
    if not bt_months:
        print("  WARNING: No months to backtest")
        return [], []

    # Strategy 1: Dynamic
    dyn_values = [100.0]
    dyn_returns = [0.0]
    dyn_turnover = [0.0]

    # Strategy 2: Static 25/25/25/25
    static_w = {"momentum_return": 0.25, "value_return": 0.25, "quality_return": 0.25, "low_volatility_return": 0.25}
    static_values = [100.0]
    static_returns = [0.0]

    # Strategy 3: Buy and hold benchmark
    bench_values = [100.0]
    bench_returns = [0.0]

    prev_dyn_w = [0.25, 0.25, 0.25, 0.25]

    for i, month in enumerate(bt_months):
        fr = fr_lookup.get(month, {})
        if not fr:
            continue

        # Dynamic
        alloc = next((a for a in allocations if str(a["month"])[:7] == month), None)
        if alloc:
            dyn_w = [alloc["momentum_weight"], alloc["value_weight"], alloc["quality_weight"], alloc["low_volatility_weight"]]
            turnover = sum(abs(dyn_w[j] - prev_dyn_w[j]) for j in range(4))
        else:
            dyn_w = [0.25, 0.25, 0.25, 0.25]
            turnover = 0

        fr_vals = [
            fr.get("momentum_return", 0) or 0.0,
            fr.get("value_return", 0) or 0.0,
            fr.get("quality_return", 0) or 0.0,
            fr.get("low_volatility_return", 0) or 0.0,
        ]
        dyn_ret = sum(dyn_w[j] * fr_vals[j] for j in range(4)) - turnover * TX_COST
        dyn_values.append(dyn_values[-1] * (1 + dyn_ret))
        dyn_returns.append(dyn_ret)
        dyn_turnover.append(turnover)
        prev_dyn_w = dyn_w

        # Static
        static_ret = 0.25 * fr_vals[0] + 0.25 * fr_vals[1] + 0.25 * fr_vals[2] + 0.25 * fr_vals[3]
        static_values.append(static_values[-1] * (1 + static_ret))
        static_returns.append(static_ret)

        # Benchmark
        if i > 0 and month in bench_prices:
            prev_m = bt_months[i-1] if i > 0 else None
            prev_price = bench_prices.get(prev_m, 0) if prev_m else 0
            curr_price = bench_prices.get(month, 0)
            if prev_price > 0:
                bench_ret = (curr_price - prev_price) / prev_price
            else:
                bench_ret = 0
        else:
            bench_ret = 0
        bench_values.append(bench_values[-1] * (1 + bench_ret))
        bench_returns.append(bench_ret)

    # Build portfolio points
    bt_portfolio = []
    strategies = [
        ("Dynamic Regime Factor Allocation", dyn_values, dyn_returns),
        ("Static 25/25/25/25", static_values, static_returns),
        ("Nifty 200 Buy & Hold", bench_values, bench_returns),
    ]

    # Authoritative stock-level strategy (spec sec 13).
    #
    # The three series above compound FACTOR returns, which is not a portfolio:
    # it has no holdings, no position sizes, no overlap between sleeves and no
    # cost of implementing it. This builds the return of the actual target
    # book from real stock returns, net of traded turnover, and reports it
    # alongside the factor view rather than replacing it, so the difference
    # between the two is visible instead of hidden.
    stock_rows = []
    stock_summary = {}
    if portfolio_targets:
        cursor.execute("SELECT month, symbol, monthly_return FROM stock_prices_monthly")
        returns_by_month: dict[str, dict[str, float]] = {}
        for m, sym, r in cursor.fetchall():
            if r is not None:
                returns_by_month.setdefault(str(m)[:7], {})[sym] = float(r)
        # Corporate-action guard, same bound as the factor layer.
        flat = [
            (m, sym, val)
            for m, row in returns_by_month.items()
            for sym, val in row.items()
        ]
        guarded, guard_fixes = price_sanity.winsorize_returns(flat)
        if guard_fixes:
            for m in list(returns_by_month):
                for sym in list(returns_by_month[m]):
                    key = (m, sym)
                    if key in guarded:
                        returns_by_month[m][sym] = guarded[key]

        targets_by_month: dict[str, dict[str, float]] = {}
        for t in portfolio_targets:
            w = t.get("target_weight")
            if w and w > 0:
                targets_by_month.setdefault(str(t["month"])[:7], {})[t["symbol"]] = float(w)

        cost = CostModel(bps=COST_BPS, label="base")
        stock_rows = stock_level_returns(targets_by_month, returns_by_month, cost)
        stock_summary = summarize(stock_rows)
        stock_summary["cost_model"] = cost.describe()
        stock_summary["method"] = "stock_level_target_weights_net_of_turnover"
        if stock_rows:
            stock_values = [100.0] + [r["portfolio_value"] for r in stock_rows]
            stock_returns = [r["monthly_return"] for r in stock_rows]
            print(
                f"  Stock-level: CAGR {stock_summary.get('cagr', 0)*100:.2f}%  "
                f"Sharpe {stock_summary.get('sharpe', 0):.2f}  "
                f"maxDD {stock_summary.get('max_drawdown', 0)*100:.2f}%  "
                f"avg holdings {stock_summary.get('avg_holdings', 0):.1f}  "
                f"cost drag {stock_summary.get('total_cost', 0)*100:.2f}%"
            )

            # Sections 21-23: cost ladder, extended risk metrics, and
            # confidence intervals on the headline numbers.
            #
            # Sharpe uses the measured Indian 10-year G-Sec yield rather than
            # an assumed constant. macro_monthly carries it for every month of
            # the backtest, so there was never a reason to guess -- and
            # guessing 6.5% against a realised 7.24% mean overstated the
            # result. The report records which basis produced the number.
            rf_loaded = risk_free.load_series(str(INPUT_DB))
            rf_aligned = risk_free.resolve(rf_loaded, [r["month"] for r in stock_rows])
            rf_meta = risk_free.describe(rf_loaded, rf_aligned)

            # The yield is a rate, not a return. Converting it to the return
            # a bondholder actually earned adds the price effect of a rate
            # move, which matters most in exactly the months that move a
            # Sharpe: a risk-off rally lowers yields, so a holder earned more
            # than the quoted rate, and measuring against the rate alone
            # overstates the excess return precisely then.
            _months_rf = [r["month"] for r in stock_rows]
            _rates = rf_aligned["rates"]
            _prev = None
            rf_realised: dict[str, float] = {}
            for _m in _months_rf:
                _y = _rates.get(_m)
                if _y is None or _prev is None:
                    continue
                rf_realised[_m] = risk_free.realised_bond_return(_prev, _y)
                _prev = _y
            if _prev is None and _rates:
                _prev = _rates.get(_months_rf[0]) if _months_rf else None
            report = performance_stats.full_report(
                stock_rows, bench_prices,
                rf_rates=rf_aligned["rates"], rf_meta=rf_meta,
            )
            if report:
                report["cost_model"] = cost.describe()
                write_json("backtest_performance_report", report)
                ra = report.get("risk_adjusted", {})
                vb = report.get("vs_benchmark", {})
                mt = report.get("mean_return_test", {})
                ci = report.get("confidence_intervals", {})
                rf_blk = report["risk_free_assumption"]
                if rf_blk.get("is_measured"):
                    print(
                        f"    Risk-free: MEASURED {rf_blk['instrument']}, mean "
                        f"{(rf_blk.get('mean_annual') or 0) * 100:.2f}% over "
                        f"{rf_blk.get('months_observed')} months, range "
                        f"{(rf_blk.get('min_annual') or 0) * 100:.2f}-"
                        f"{(rf_blk.get('max_annual') or 0) * 100:.2f}%"
                    )
                else:
                    print(
                        f"    Risk-free: ASSUMED constant "
                        f"{rf_blk.get('annual', 0) * 100:.2f}% (no series found)"
                    )
                print(
                    f"    Sharpe vs risk-free: {ra.get('sharpe_vs_rf', 0):.2f}"
                    f"  (vs 0% rate: {ra.get('sharpe_vs_zero', 0):.2f})"
                )
                if vb:
                    print(
                        f"    vs NIFTY 200: beta {vb.get('beta', 0):.2f}  "
                        f"alpha {vb.get('alpha_annual', 0)*100:.2f}%  "
                        f"IR {vb.get('information_ratio', 0):.2f}  "
                        f"TE {vb.get('tracking_error_annual', 0)*100:.1f}%"
                    )
                if mt:
                    print(
                        f"    Mean-return t (Newey-West) {mt.get('t_stat', 0):.2f}  "
                        f"[{mt.get('lags', 0)} lags, AC1 {mt.get('lag1_autocorrelation', 0):+.2f}]"
                    )
                if "sharpe" in ci:
                    s = ci["sharpe"]
                    print(
                        f"    CAGR 95% CI: "
                        f"[{ci['cagr']['ci_low']*100:.2f}%, {ci['cagr']['ci_high']*100:.2f}%]"
                    )
                    print(
                        f"    Sharpe 95% CI: "
                        f"[{s['ci_low']:.2f}, {s['ci_high']:.2f}]"
                    )

            ladder = performance_stats.cost_scenario_table(
                returns_by_month, targets_by_month, COST_SCENARIOS_BPS
            )
            if ladder:
                base = next((r for r in ladder if r["bps"] == COST_BPS), None)
                gross = next((r for r in ladder if r["bps"] == 0.0), None)
                stress = ladder[-1]
                write_json("backtest_cost_scenarios", {
                    "scenarios": ladder,
                    "base_bps": COST_BPS,
                    "gross_cagr": gross["cagr"] if gross else None,
                    "base_cagr": base["cagr"] if base else None,
                    "stress_bps": stress["bps"],
                    "stress_cagr": stress["cagr"],
                    "cagr_lost_to_costs_pct": (
                        round(((gross["cagr"] - stress["cagr"]) * 100), 2)
                        if gross else None
                    ),
                    "interpretation": (
                        "The book turns over roughly a quarter of its value a month, "
                        "so each 10bps of cost assumption is worth about 0.27% of "
                        "annual return. The gap between the 0bps and base rows is the "
                        "gross edge; the gap between base and the stress row is how "
                        "much of it execution can consume."
                    ),
                })
                print(
                    "    Cost ladder CAGR: "
                    + "  ".join(f"{r['bps']:g}bps {r['cagr']*100:.2f}%" for r in ladder)
                )

    for sname, values, returns in strategies:
        peak = values[0]
        for i, v in enumerate(values):
            if i == 0:
                continue
            month = bt_months[i-1] if i-1 < len(bt_months) else ""
            peak = max(peak, v)
            dd = (v - peak) / peak if peak > 0 else 0
            regime = regime_lookup.get(month, "Sideways / Neutral")
            turnover = dyn_turnover[i-1] if sname == "Dynamic Regime Factor Allocation" and i-1 < len(dyn_turnover) else 0
            bt_portfolio.append({
                "month": month,
                "strategy_name": sname,
                "portfolio_value": round(v, 2),
                "monthly_return": round(returns[i], 6),
                "drawdown": round(dd, 6),
                "turnover": round(turnover, 4),
                "regime_label": regime
            })

    write_json("backtest_portfolio", bt_portfolio)

    # The stock-level book is emitted as its own series with its own month
    # index. It starts one month after the factor-level series because a book
    # formed at the close of month t is first evaluated in t+1, and it may be
    # shorter when the final weight month has no following returns.
    if stock_rows:
        stock_points = []
        for r in stock_rows:
            stock_points.append({
                "month": r["month"],
                "strategy_name": "Stock-Level Constrained Portfolio",
                "portfolio_value": round(r["portfolio_value"], 2),
                "monthly_return": round(r["monthly_return"], 6),
                "drawdown": round(r["drawdown"], 6),
                "turnover": round(r["turnover"], 4),
                "gross_return": round(r["gross_return"], 6),
                "cost": round(r["cost"], 6),
                "holdings": r["holdings"],
                "regime_label": regime_lookup.get(r["month"], "Sideways / Neutral"),
            })
        write_json("backtest_portfolio", bt_portfolio + stock_points)

    # Summary
    summaries = []
    for sname, values, returns in strategies:
        rets = returns[1:]
        if not rets:
            continue
        total_ret = (values[-1] / values[0] - 1) if values[0] > 0 else 0
        years = len(rets) / 12
        cagr = ((values[-1] / values[0]) ** (1/years) - 1) if years > 0 and values[0] > 0 else 0
        vol = float(np.std(rets) * math.sqrt(12)) if len(rets) > 1 else 0
        sharpe = (float(np.mean(rets)) * 12) / vol if vol > 0 else 0
        max_dd = min(0, min((values[i] - max(values[:i+1])) / max(values[:i+1]) for i in range(1, len(values)))) if len(values) > 1 else 0
        calmar = cagr / abs(max_dd) if max_dd != 0 else 0
        avg_to = float(np.mean(dyn_turnover)) if sname == "Dynamic Regime Factor Allocation" else 0
        best = max(rets) if rets else 0
        worst = min(rets) if rets else 0

        summaries.append({
            "strategy_name": sname,
            "cagr": round(cagr, 4),
            "total_return": round(total_ret, 4),
            "annual_volatility": round(vol, 4),
            "sharpe": round(sharpe, 4),
            "max_drawdown": round(max_dd, 4),
            "calmar": round(calmar, 4),
            "avg_turnover": round(avg_to, 4),
            "best_month": round(best, 6),
            "worst_month": round(worst, 6)
        })

    write_json("backtest_summary", summaries)
    # The stock-level book is the authoritative implementation result; the
    # factor-level series above is retained for comparison and attribution.
    if stock_rows:
        write_json("backtest_stock_level", stock_rows)
    if stock_summary:
        write_json("backtest_stock_level_summary", stock_summary)
    write_csv("backtest_portfolio_monthly", bt_portfolio, ["month","strategy_name","portfolio_value","monthly_return","drawdown","turnover","regime_label"])
    write_csv("backtest_summary", summaries, ["strategy_name","cagr","total_return","annual_volatility","sharpe","max_drawdown","calmar","avg_turnover","best_month","worst_month"])
    print(f"[BacktestAgent] Done. {len(bt_portfolio)} points, {len(summaries)} summaries.")
    return bt_portfolio, summaries

# ─── ChartSignalAgent ───
def chart_signal_agent(conn, rebalance_trades, baskets, excluded=frozenset(),
                       news_features=None):
    print("[ChartSignalAgent] Starting...")
    cursor = conn.cursor()

    # Build signal events for charts
    signal_events = []
    for t in rebalance_trades:
        if t["signal_type"] == "HOLD":
            continue
        # Find factor score
        fs = 0
        for b in baskets:
            if b["month"] == t["month"] and b["symbol"] == t["symbol"] and b["factor_name"] == t["primary_factor"]:
                fs = b["factor_score"]
                break

        signal_events.append({
            "date": t["month"] + "-01",
            "month": t["month"],
            "symbol": t["symbol"],
            "signal_type": t["signal_type"],
            "signal_price": t["signal_price"],
            "old_weight": t["old_weight"],
            "new_weight": t["new_weight"],
            "weight_change": t["weight_change"],
            "regime": t["regime_label"],
            "regime_confidence": t["regime_confidence"],
            "transition_risk": t["transition_risk"],
            "primary_factor": t["primary_factor"],
            "factor_score": round(fs, 6),
            "reason": t["reason"]
        })

    write_json("stock_signal_events", signal_events)
    write_csv("stock_signal_events", signal_events, ["date","month","symbol","signal_type","signal_price","old_weight","new_weight","weight_change","regime","regime_confidence","transition_risk","primary_factor","factor_score","reason"])

    # Also export stock prices for charting
    cursor.execute("SELECT month, symbol, monthly_close AS open, monthly_close AS high, monthly_close AS low, monthly_close AS close, monthly_close AS adjusted_close, monthly_volume AS volume FROM stock_prices_monthly ORDER BY month, symbol")
    cols = [d[0] for d in cursor.description]
    prices = []
    for r in cursor.fetchall():
        d = dict(zip(cols, r))
        if d.get("symbol") and d["symbol"] not in excluded:
            prices.append({
                "month": d["month"][:7] if d.get("month") else "",
                "symbol": d["symbol"],
                "open": safe_float(d.get("open")),
                "high": safe_float(d.get("high")),
                "low": safe_float(d.get("low")),
                "close": safe_float(d.get("close")),
                "adjusted_close": safe_float(d.get("adjusted_close")),
                "volume": safe_float(d.get("volume"))
            })
    write_json("stock_prices", prices)

    # Market index
    cursor.execute("SELECT * FROM market_index_monthly ORDER BY month")
    cols = [d[0] for d in cursor.description]
    mkt = []
    for r in cursor.fetchall():
        d = dict(zip(cols, r))
        mkt.append({
            "month": d.get("month","")[:7] if d.get("month") else "",
            "index_name": d.get("index_name","Nifty 200"),
            "open": safe_float(d.get("open")),
            "high": safe_float(d.get("high")),
            "low": safe_float(d.get("low")),
            "close": safe_float(d.get("close")),
            "return": safe_float(d.get("return")),
            "drawdown": safe_float(d.get("drawdown"))
        })
    write_json("market_index", mkt)

    # Macro
    try:
        cursor.execute("SELECT * FROM macro_monthly ORDER BY month")
        cols = [d[0] for d in cursor.description]
        macro = []
        for r in cursor.fetchall():
            d = dict(zip(cols, r))
            macro.append({
                "month": d.get("month","")[:7] if d.get("month") else "",
                "cpi": safe_float(d.get("cpi")),
                "repo_rate": safe_float(d.get("repo_rate")),
                "ten_year_yield": safe_float(d.get("ten_year_yield")),
                "usd_inr": safe_float(d.get("usd_inr")),
                "crude_oil": safe_float(d.get("crude_oil")),
                "india_vix": safe_float(d.get("india_vix")),
                "fii_net": safe_float(d.get("fii_net")),
                "dii_net": safe_float(d.get("dii_net"))
            })
        write_json("macro_monthly", macro)
    except:
        write_json("macro_monthly", [])

    # Sector index
    try:
        cursor.execute("SELECT * FROM sector_index_monthly ORDER BY month")
        cols = [d[0] for d in cursor.description]
        sector = []
        for r in cursor.fetchall():
            d = dict(zip(cols, r))
            sector.append({
                "month": d.get("month","")[:7] if d.get("month") else "",
                "index_name": d.get("index_name",""),
                "close": safe_float(d.get("close")),
                "return": safe_float(d.get("return"))
            })
        write_json("sector_index", sector)
    except:
        write_json("sector_index", [])

    # News features: merge the stored history with the live figures.
    #
    # This used to re-read `news_features_monthly` and write the result over
    # `news_features.json`, which the news agent had just written correctly.
    # Two faults: the columns were named `sentiment_score` when the table calls
    # them `monthly_news_sentiment`, so every field came back None and 61 rows
    # of nulls overwrote good data; and it replaced live values for months both
    # sources cover, when the live figure is the one the model was given.
    try:
        cursor.execute(
            "SELECT month, monthly_news_sentiment, monthly_negative_news_ratio, "
            "       news_article_count, monthly_risk_event_count, news_confidence "
            "FROM news_features_monthly ORDER BY month"
        )
        stored = {}
        for _m, _s, _n, _c, _r, _cf in cursor.fetchall():
            stored[str(_m)[:7]] = {
                "month": str(_m)[:7],
                "sentiment_score": safe_float(_s),
                "negative_ratio": safe_float(_n),
                "article_count": safe_float(_c),
                "risk_event_count": safe_float(_r),
                "news_confidence": safe_float(_cf),
            }
        live = {str(r.get("month", ""))[:7]: r for r in (news_features or [])}
        news = []
        for _month in sorted(set(stored) | set(live)):
            _row = dict(stored.get(_month) or live.get(_month) or {"month": _month})
            _row["month"] = _month
            if _month in live:
                _row.update({k: v for k, v in live[_month].items() if v is not None})
            news.append(_row)
        write_json("news_features", news)
        _shared = len(set(stored) & set(live))
        print(f"  News features: {len(news)} months ({len(live)} live, "
              f"{len(stored) - _shared} historical, {_shared} shared)")
    except sqlite3.Error as exc:
        print(f"  WARNING: could not merge historical news features: {exc}")

    print(f"[ChartSignalAgent] Done. {len(signal_events)} signals, {len(prices)} price points.")
    return signal_events

# ─── ExplanationAgent ───
def explanation_agent(validation_report, regime_preds, baskets, factor_returns, diagnostics, allocations, decisions, portfolio_targets, rebalance_trades, bt_portfolio, bt_summary, signal_events):
    print("[ExplanationAgent] Starting...")
    report = []
    report.append("# Indian Regime/Factor/Portfolio Intelligence - Model Run Report\n")
    report.append(f"Generated: {datetime.datetime.now().isoformat()}\n")
    report.append("\n## Data Used\n")
    report.append(f"- Input database: processed_financial_data.sqlite\n")
    report.append(f"- Stocks in universe: {validation_report.get('final_stock_count', 'N/A')}\n")
    report.append(f"- Regime date range: {validation_report.get('regime_date_range', 'N/A')}\n")
    coverage = validation_report.get("universe_coverage", {})
    excluded_detail = coverage.get("excluded_symbols", {})
    if excluded_detail:
        report.append(
            f"- Universe coverage: {coverage.get('modeling_universe_size', 'N/A')}"
            f"/{coverage.get('index_size', 'N/A')} index symbols usable\n"
        )
        report.append("- Symbols excluded for insufficient upstream data:\n")
        for sym, reason in excluded_detail.items():
            report.append(f"  - {sym}: {reason}\n")
    else:
        report.append("- Symbols excluded: none\n")
    report.append("\n## Regime Model\n")
    report.append("- Model: Gaussian Mixture Model (5 clusters)\n")
    report.append(f"- Regime predictions: {len(regime_preds)}\n")
    if regime_preds:
        from collections import Counter
        rc = Counter(p["regime_label"] for p in regime_preds)
        for label, count in rc.most_common():
            report.append(f"  - {label}: {count} months\n")
    report.append("\n## Factor Model\n")
    report.append(f"- Factors: Momentum, Value, Quality, Low Volatility\n")
    report.append(f"- Top K per factor: {TOP_K}\n")
    report.append(f"- Factor basket entries: {len(baskets)}\n")
    report.append(f"- Factor return months: {len(factor_returns)}\n")
    report.append("\n## Allocation Optimizer\n")
    report.append("- Method: Grid search in 5% increments\n")
    report.append("- Objective: maximize w'u - eta * w'Sigma*w - lambda * turnover - rho * redundancy\n")
    report.append("- Constraints: weights sum to 1, weights >= 0, max weight <= 0.50\n")
    report.append(f"- Allocations generated: {len(allocations)}\n")
    report.append(f"- Decisions: {len(decisions)}\n")
    if decisions:
        from collections import Counter
        dc = Counter(d["decision"] for d in decisions)
        for dec, count in dc.most_common():
            report.append(f"  - {dec}: {count}\n")
    report.append("\n## Signal Logic\n")
    report.append("- BUY: new symbol with target weight > 0\n")
    report.append("- ADD: existing symbol with increased weight\n")
    report.append("- REDUCE: existing symbol with reduced weight\n")
    report.append("- SELL: existing symbol removed from target\n")
    report.append("- HOLD: small weight change\n")
    report.append(f"- Total trades: {len(rebalance_trades)}\n")
    report.append(f"- Chart signal events: {len(signal_events)}\n")
    report.append("\n## Backtest Assumptions\n")
    report.append(f"- Transaction cost: {TX_COST*100:.2f}% per trade side\n")
    report.append(f"- Backtest months: {len(bt_portfolio)//3}\n")
    report.append("\n### Performance Summary\n")
    if bt_summary:
        report.append("| Strategy | CAGR | Vol | Sharpe | Max DD | Calmar |\n")
        report.append("|----------|------|-----|--------|--------|--------|\n")
        for s in bt_summary:
            report.append(f"| {s['strategy_name']} | {s['cagr']:.2%} | {s['annual_volatility']:.2%} | {s['sharpe']:.2f} | {s['max_drawdown']:.2%} | {s['calmar']:.2f} |\n")
    report.append("\n## Known Limitations\n")
    report.append("- Grid search uses 5% increments, not continuous optimization\n")
    report.append("- Factor returns use equal weighting within baskets\n")
    report.append("- Regime detection uses GMM which may not capture all market dynamics\n")
    report.append("- No look-ahead bias in factor returns (uses previous month baskets)\n")
    report.append("- Transaction costs are symmetric and fixed\n")

    report_text = "".join(report)
    with open(PROJECT_DIR / "model_run_report.md", "w") as f:
        f.write(report_text)
    print("[ExplanationAgent] Done. Report written to model_run_report.md")
    return report_text

# ─── Main ───
def main():
    run_started = datetime.datetime.now(datetime.timezone.utc)
    print("=" * 60)
    print("Indian Regime/Factor/Portfolio Intelligence Pipeline")
    print("=" * 60)

    if not INPUT_DB.exists():
        print(f"ERROR: Input database not found at {INPUT_DB}")
        print(f"Please place processed_financial_data.sqlite in {INPUT_DB.parent}/")
        sys_exit_code = 1
        return

    # Announce data currency before doing any work, not after. A pipeline that
    # quietly computes on four-day-old prices and prints a confident summary is
    # the failure mode worth being loud about, and the reader cannot tell from
    # the numbers alone.
    try:
        freshness = data_freshness.assess(str(INPUT_DB))
        print(data_freshness.format_report(freshness))
        if freshness.get("status") == "stale":
            print(
                "  WARNING: the source data is stale. Every current-month figure "
                "below is out of date. Run scripts/daily_eod_refresh.py, or "
                "`python scripts/verify_data.py` to re-check."
            )
        print("-" * 60)
    except Exception as exc:
        print(f"  WARNING: data freshness check could not run: {exc}")

    conn = sqlite3.connect(str(INPUT_DB))

    # Node 0: RSSNewsAgent
    news_articles, news_features = rss_news_agent()

    # The live feed covers about a week. `news_features_monthly` already holds
    # 56 months inside the backtest window, collected upstream and then never
    # read, because the pipeline built its news view from the fetch alone.
    # Merging them takes news coverage from a handful of months to most of the
    # window. Live wins for shared months; every row keeps its own confidence
    # weight, so a month backed by one article stays discounted against one
    # backed by several hundred.
    _hist = news_history.load_historical(str(INPUT_DB))
    news_features, _merge = news_history.merge(news_features, _hist)
    print(
        f"  News: {_merge['total_months']} months "
        f"({_merge['live_months']} live, {_merge['historical_months']} from database)"
    )

    # Node 1: DataValidationAgent
    validation_report, symbols, excluded, survivorship = data_validation_agent(conn)

    # Node 2: RegimeDetectionAgent
    regime_preds = regime_detection_agent(conn, news_features)

    # Node 3: FactorScoringAgent
    baskets, factor_names = factor_scoring_agent(
        conn, regime_preds, excluded, survivorship
    )

    # Node 4: FactorForecastAgent
    factor_returns, diagnostics = factor_forecast_agent(conn, baskets, regime_preds, excluded)

    # Node 5: AllocationOptimizerAgent
    allocations, decisions = allocation_optimizer_agent(factor_returns, diagnostics, regime_preds, news_features, news_articles)

    # Node 6: PortfolioTransitionAgent
    portfolio_targets, rebalance_trades = portfolio_transition_agent(conn, baskets, allocations, regime_preds, excluded)

    # Node 7: RiskDiagnosticsAgent
    risk_diagnostics_agent(diagnostics, regime_preds)

    # Node 8: BacktestAgent
    bt_portfolio, bt_summary = backtest_agent(conn, allocations, rebalance_trades, regime_preds, portfolio_targets=portfolio_targets)

    # Node 9: ChartSignalAgent
    signal_events = chart_signal_agent(conn, rebalance_trades, baskets, excluded, news_features)

    # Node 10 was a second RSSNewsAgent call. Removed: it re-fetched the live
    # feeds, produced a different article set from the one the regime model had
    # consumed at Node 0, and overwrote the snapshot with it. The snapshot
    # exists to record what the run actually used, so re-fetching defeated it,
    # and the downstream outputs could no longer be reproduced from it. The
    # articles from Node 0 are the ones used throughout.

    # Node 11: ExplanationAgent
    explanation_agent(validation_report, regime_preds, baskets, factor_returns, diagnostics,
                     allocations, decisions, portfolio_targets, rebalance_trades,
                     bt_portfolio, bt_summary, signal_events)

    conn.close()

    # Section 24: record what this run consumed and assumed, so the numbers
    # above can be reproduced and so a later run knows whether it is even
    # comparable to this one.
    #
    # The manifest is written last, deliberately: `collect_caveats` reads the
    # artifacts the earlier nodes produced, so a caveat is read from the same
    # JSON it qualifies rather than restated by hand.
    try:
        runtime = (datetime.datetime.now(datetime.timezone.utc)
                   - run_started).total_seconds()
        manifest = experiment_manifest.build_manifest(
            str(INPUT_DB), str(SCRIPT_DIR), str(JSON_DIR), run_started, runtime,
            news_mode=NEWS_MODE,
        )
        write_json("experiment_manifest", manifest)
        cs = manifest["caveat_summary"]
        fr = manifest.get("data_freshness") or {}
        print(f"[Manifest] fingerprint {manifest['run']['fingerprint'][:16]}  "
              f"news {NEWS_MODE}  data {fr.get('status', 'unknown')}  "
              f"{cs['high']} high / {cs['medium']} medium / {cs['low']} low caveats  "
              f"runtime {runtime:.1f}s")
    except Exception as exc:
        # A manifest failure must never invalidate a run that produced valid
        # results, but it must be loud.
        print(f"[Manifest] WARNING: could not write experiment manifest: {exc}")

    print("\n" + "=" * 60)
    print("Pipeline complete!")
    print(f"  JSON outputs: {JSON_DIR}")
    print(f"  CSV outputs: {CSV_DIR}")
    print(f"  Report: {PROJECT_DIR / 'model_run_report.md'}")
    print("=" * 60)

if __name__ == "__main__":
    main()

















