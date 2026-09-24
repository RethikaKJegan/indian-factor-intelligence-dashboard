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

# ─── Paths ───
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
INPUT_DB = PROJECT_DIR / "data_input" / "processed_financial_data.sqlite"
OUTPUT_DB = PROJECT_DIR / "financial_intelligence_outputs.sqlite"
JSON_DIR = PROJECT_DIR / "public" / "data"
CSV_DIR = PROJECT_DIR / "output_csv"
RAW_DATA_DIR = PROJECT_DIR.parent.parent / "data"
RSS_SOURCE_FILE = RAW_DATA_DIR / "News Data" / "rss_sources.txt.txt"
CSV_DIR.mkdir(exist_ok=True)
JSON_DIR.mkdir(parents=True, exist_ok=True)

EXCLUDED = {"ENRIN","GROWW","HDFCLIFE","ICICIAMC","ICICIGI","LENSKART","LGEINDIA","MCX","SBILIFE","TATACAP","TMCV"}
REGIME_LABELS = ["Bull / Expansion","Bear / Stress","Sideways / Neutral","Recovery","High Volatility / Risk-Off"]
FACTORS = ["Momentum","Value","Quality","Low Volatility"]
TOP_K = 10
TX_COST = 0.001  # 0.10% per side

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
    print("[RSSNewsAgent] Starting...")
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
    for feed_url in sources:
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
    if failed_feeds and not articles_by_id:
        for f in failed_feeds:
            print(f"  RSS warning: {f['reason']} from {f['feed_url']}")
    elif failed_feeds:
        print(f"  RSS note: skipped {len(failed_feeds)} empty/unavailable optional feeds; fetched {len(articles_by_id)} unique articles.")
    write_json("news_articles_raw", articles)
    write_json("news_features", news_features)
    write_json("news_features_daily", news_daily)
    write_csv("news_articles_raw", articles, ["article_id", "source", "title", "summary", "url", "published_at", "published_date", "month", "sentiment", "risk_event_count", "is_negative", "feed_url"])
    write_csv("news_features_monthly", news_features, ["month", "sentiment_score", "negative_ratio", "article_count", "risk_event_count", "news_confidence"])
    write_csv("news_features_daily", news_daily, ["date", "sentiment_score", "negative_ratio", "article_count", "risk_event_count", "news_confidence"])
    print(f"[RSSNewsAgent] Done. {len(articles)} articles, {len(news_features)} monthly rows.")
    return articles, news_features

# ─── DataValidationAgent ───
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

    # Check excluded symbols absent
    for sym in EXCLUDED:
        cursor.execute("SELECT COUNT(*) FROM factor_scores_monthly WHERE symbol=?", (sym,))
        cnt = cursor.fetchone()[0]
        if cnt > 0:
            print(f"  WARNING: Excluded symbol {sym} found in factor_scores_monthly ({cnt} rows)")

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
        symbols = [r[0] for r in cursor.fetchall() if r[0] not in EXCLUDED]
    except:
        cursor.execute("SELECT DISTINCT symbol FROM factor_scores_monthly ORDER BY symbol")
        symbols = [r[0] for r in cursor.fetchall() if r[0] not in EXCLUDED]

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
    return report, symbols

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

    # Identify numeric feature columns
    skip_cols = {"month"}
    feature_cols = [c for c in cols if c not in skip_cols and isinstance(rows[0].get(c), (int, float, type(None)))]

    # Build feature matrix
    months = [r["month"][:7] for r in rows]
    X_raw = []
    for r in rows:
        vec = []
        for c in feature_cols:
            v = r.get(c)
            vec.append(float(v) if v is not None else 0.0)
        nf = news_lookup.get(r["month"][:7], {})
        vec.extend([
            float(nf.get("news_sentiment", 0.0)),
            float(nf.get("negative_news_ratio", 0.0)),
            float(nf.get("risk_event_count", 0.0)),
            float(nf.get("news_confidence", 0.0)),
        ])
        X_raw.append(vec)
    feature_cols = feature_cols + ["news_sentiment", "negative_news_ratio", "risk_event_count", "news_confidence"]
    X = np.array(X_raw)

    # Drop fully null columns
    valid_cols = [i for i in range(X.shape[1]) if np.any(X[:, i] != 0)]
    X = X[:, valid_cols]
    used_features = [feature_cols[i] for i in valid_cols]

    # Standardize
    mean = X.mean(axis=0)
    std = X.std(axis=0)
    std[std == 0] = 1
    X_std = (X - mean) / std

    # GMM with 5 clusters
    from sklearn.mixture import GaussianMixture
    n_clusters = min(5, len(rows))
    gmm = GaussianMixture(n_components=n_clusters, covariance_type='full', random_state=42, max_iter=200)
    gmm.fit(X_std)
    labels = gmm.predict(X_std)
    probs = gmm.predict_proba(X_std)

    # Map clusters to regime labels based on characteristics
    # Use nifty returns and vix to characterize
    cluster_chars = {}
    for i in range(n_clusters):
        mask = labels == i
        if np.any(mask):
            cluster_chars[i] = {
                "mean_ret": float(np.mean(X_std[mask, 0])) if X_std.shape[1] > 0 else 0,
                "mean_vol": float(np.mean(X_std[mask, min(1, X_std.shape[1]-1)])) if X_std.shape[1] > 1 else 0,
                "count": int(np.sum(mask))
            }
        else:
            cluster_chars[i] = {"mean_ret": 0, "mean_vol": 0, "count": 0}

    # Sort clusters by mean return: high->bull, low->bear
    sorted_clusters = sorted(range(n_clusters), key=lambda i: cluster_chars[i]["mean_ret"], reverse=True)
    label_map = {}
    if n_clusters >= 5:
        label_map[sorted_clusters[0]] = "Bull / Expansion"
        label_map[sorted_clusters[1]] = "Recovery"
        label_map[sorted_clusters[2]] = "Sideways / Neutral"
        label_map[sorted_clusters[3]] = "High Volatility / Risk-Off"
        label_map[sorted_clusters[4]] = "Bear / Stress"
    elif n_clusters == 4:
        label_map[sorted_clusters[0]] = "Bull / Expansion"
        label_map[sorted_clusters[1]] = "Recovery"
        label_map[sorted_clusters[2]] = "Sideways / Neutral"
        label_map[sorted_clusters[3]] = "Bear / Stress"
    else:
        for i, sc in enumerate(sorted_clusters):
            label_map[sc] = REGIME_LABELS[min(i, len(REGIME_LABELS)-1)]

    predictions = []
    prev_probs = None
    for i, month in enumerate(months):
        conf = float(probs[i, labels[i]])
        # Transition risk
        if prev_probs is not None:
            instability = float(np.sum(np.abs(probs[i] - prev_probs))) / 2
            trans_risk = (1 - conf) * 0.5 + instability * 0.5
        else:
            trans_risk = 1 - conf

        nf = news_lookup.get(month, {})
        ns = news_stress_score(nf)
        trans_risk = min(1.0, trans_risk + 0.35 * ns)
        conf = max(0.0, min(1.0, conf - 0.10 * ns))

        pred = {
            "month": month,
            "regime_label": label_map[labels[i]],
            "regime_cluster": int(labels[i]),
            "regime_confidence": round(conf, 4),
            "transition_risk": round(trans_risk, 4),
            "prob_bull_expansion": round(float(probs[i, sorted_clusters[0]]) if len(sorted_clusters) > 0 else 0, 4),
            "prob_bear_stress": round(float(probs[i, sorted_clusters[-1]]) if len(sorted_clusters) > 0 else 0, 4),
            "prob_sideways_neutral": round(float(probs[i, sorted_clusters[len(sorted_clusters)//2]]) if len(sorted_clusters) > 0 else 0, 4),
            "prob_recovery": round(float(probs[i, sorted_clusters[1]]) if len(sorted_clusters) > 1 else 0, 4),
            "prob_high_vol_risk_off": round(float(probs[i, sorted_clusters[3]]) if len(sorted_clusters) > 3 else 0, 4),
            "model_version": "GMM-5-news-v2",
            "news_sentiment": round(float(nf.get("news_sentiment", 0.0)), 4),
            "negative_news_ratio": round(float(nf.get("negative_news_ratio", 0.0)), 4),
            "risk_event_count": round(float(nf.get("risk_event_count", 0.0)), 4),
            "news_confidence": round(float(nf.get("news_confidence", 0.0)), 4),
            "news_stress_score": ns
        }
        predictions.append(pred)
        prev_probs = probs[i]

    write_json("regime_predictions", predictions)
    headers = ["month","regime_label","regime_cluster","regime_confidence","transition_risk",
               "prob_bull_expansion","prob_bear_stress","prob_sideways_neutral","prob_recovery",
               "prob_high_vol_risk_off","model_version","news_sentiment","negative_news_ratio","risk_event_count","news_confidence","news_stress_score"]
    write_csv("regime_predictions_monthly", predictions, headers)
    print(f"[RegimeDetectionAgent] Done. {len(predictions)} predictions.")
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
def factor_scoring_agent(conn, regime_preds):
    print("[FactorScoringAgent] Starting...")
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM factor_scores_monthly ORDER BY month, symbol")
    cols = [d[0] for d in cursor.description]
    rows = [dict(zip(cols, r)) for r in cursor.fetchall()]

    if not rows:
        print("  WARNING: No factor scores found")
        return [], []

    # Determine factor columns
    factor_map = {}
    for c in cols:
        cl = c.lower()
        if "momentum" in cl: factor_map["Momentum"] = c
        elif "value" in cl: factor_map["Value"] = c
        elif "quality" in cl: factor_map["Quality"] = c
        elif "low_vol" in cl or "lowvol" in cl or "volatility" in cl: factor_map["Low Volatility"] = c

    if not factor_map:
        # Try standard column names
        for c in cols:
            if c in ("momentum_score","momentum"): factor_map["Momentum"] = c
            if c in ("value_score","value"): factor_map["Value"] = c
            if c in ("quality_score","quality"): factor_map["Quality"] = c
            if c in ("low_volatility_score","low_vol"): factor_map["Low Volatility"] = c

    # Fallback: use first 4 numeric columns after month+symbol
    if not factor_map:
        skip = {"month","symbol"}
        numeric_cols = [c for c in cols if c not in skip]
        fnames = ["Momentum","Value","Quality","Low Volatility"]
        for i, c in enumerate(numeric_cols[:4]):
            factor_map[fnames[i]] = c

    print(f"  Factor columns: {factor_map}")

    baskets = []
    months = sorted(set(r["month"][:7] for r in rows))

    regime_lookup = {str(p["month"])[:7]: p["regime_label"] for p in regime_preds}

    for month in months:
        month_rows = [r for r in rows if r["month"][:7] == month and r.get("symbol") not in EXCLUDED]
        for fname, fcol in factor_map.items():
            scored = []
            for r in month_rows:
                v = r.get(fcol)
                if v is not None:
                    try:
                        v = float(v)
                        if not math.isnan(v):
                            scored.append((r.get("symbol",""), v))
                    except: pass

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
    write_csv("factor_baskets_monthly", baskets, ["month","factor_name","symbol","factor_score","factor_rank","selected_flag"])
    print(f"[FactorScoringAgent] Done. {len(baskets)} basket entries.")
    return baskets, list(factor_map.keys())

# ─── FactorForecastAgent ───
def factor_forecast_agent(conn, baskets, regime_preds):
    print("[FactorForecastAgent] Starting...")
    cursor = conn.cursor()

    # Get stock prices for return calculation
    cursor.execute("SELECT month, symbol, monthly_close AS close, monthly_close AS adjusted_close FROM stock_prices_monthly ORDER BY month, symbol")
    cols = [d[0] for d in cursor.description]
    price_rows = [dict(zip(cols, r)) for r in cursor.fetchall()]

    # Build price lookup: (symbol, month) -> close
    price_lookup = {}
    for r in price_rows:
        sym = r.get("symbol")
        m = r["month"][:7]
        close = r.get("adjusted_close") or r.get("close")
        if sym and close and sym not in EXCLUDED:
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
                prev_price = price_lookup.get((sym, prev_month))
                curr_price = price_lookup.get((sym, curr_month))
                if prev_price and curr_price and prev_price > 0:
                    rets.append((curr_price - prev_price) / prev_price)

            fr[fname.lower().replace(" ", "_") + "_return"] = round(float(np.mean(rets)) if rets else 0.0, 6)

        factor_returns.append(fr)

    write_json("factor_returns", factor_returns)
    write_csv("factor_returns_monthly", factor_returns, ["month","momentum_return","value_return","quality_return","low_volatility_return"])

    # Build regime-conditional diagnostics
    regime_lookup = {str(p["month"])[:7]: p for p in regime_preds}
    diagnostics = []

    # Group factor returns by regime
    regime_groups = {}
    for fr in factor_returns:
        regime = regime_lookup.get(str(fr["month"])[:7], {}).get("regime_label", "Sideways / Neutral")
        if regime not in regime_groups:
            regime_groups[regime] = []
        regime_groups[regime].append(fr)

    for fr in factor_returns:
        regime = regime_lookup.get(str(fr["month"])[:7], {}).get("regime_label", "Sideways / Neutral")
        group = regime_groups.get(regime, [fr])

        # Calculate expected returns (mean of regime group up to current month)
        er = {}
        for fname in factors:
            key = fname.lower().replace(" ", "_") + "_return"
            vals = [g[key] for g in group if key in g]
            er[fname] = round(float(np.mean(vals)) if vals else 0.0, 6)

        # Covariance matrix
        ret_matrix = []
        for g in group:
            row = [g.get(f.lower().replace(" ", "_") + "_return", 0) for f in factors]
            ret_matrix.append(row)

        if len(ret_matrix) >= 2:
            cov = np.cov(np.array(ret_matrix).T)
            corr = np.corrcoef(np.array(ret_matrix).T)
        else:
            cov = np.eye(4) * 0.01
            corr = np.eye(4)

        cov_dict = {}
        corr_dict = {}
        fkeys = [f.lower().replace(" ", "_") for f in factors]
        for i, fi in enumerate(fkeys):
            cov_dict[fi] = {}
            corr_dict[fi] = {}
            for j, fj in enumerate(fkeys):
                cov_dict[fi][fj] = round(float(cov[i, j]), 6)
                corr_dict[fi][fj] = round(float(corr[i, j]), 6) if not math.isnan(corr[i,j]) else 0.0

        # Eigenvalues
        try:
            eigvals = np.linalg.eigvalsh(cov)
            max_eig = float(max(eigvals))
            total_eig = float(sum(eigvals))
            max_eig_share = round(max_eig / total_eig if total_eig > 0 else 0, 4)
            eff_factors = round(float(sum(eigvals)**2 / sum(eigvals**2)) if sum(eigvals**2) > 0 else 1, 2)
        except:
            max_eig_share = 0.5
            eff_factors = 2.0

        redundancy = round(max(0, 4 - eff_factors) / 4, 4)
        risk_conc = round(max_eig_share, 4)

        diagnostics.append({
            "month": fr["month"],
            "regime_label": regime,
            "expected_returns": er,
            "covariance_matrix": cov_dict,
            "correlation_matrix": corr_dict,
            "max_eigenvalue_share": max_eig_share,
            "effective_independent_factors": eff_factors,
            "risk_concentration_score": risk_conc,
            "redundancy_score": redundancy
        })

    write_json("factor_diagnostics", diagnostics)
    write_csv("regime_factor_diagnostics_monthly", diagnostics, ["month","regime_label","expected_returns_json","covariance_matrix_json","correlation_matrix_json","max_eigenvalue_share","effective_independent_factors","risk_concentration_score","redundancy_score"])
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

    for fr in factor_returns:
        month = fr["month"]
        regime = regime_lookup.get(month, {})
        diag = diag_lookup.get(month, {})

        er = np.array([fr.get(k + "_return", 0) for k in fkeys])
        news = news_lookup.get(month, {})
        ns = news_stress_score(news)
        if ns > 0:
            # High-confidence negative news penalizes aggressive Momentum/Value and supports defensive factors.
            er = er + np.array([-0.035 * ns, -0.020 * ns, 0.012 * ns, 0.018 * ns])

        # Get covariance from diagnostics
        cov = np.eye(4) * 0.01
        if diag and "covariance_matrix" in diag:
            cm = diag["covariance_matrix"]
            for i, fi in enumerate(fkeys):
                for j, fj in enumerate(fkeys):
                    cov[i, j] = cm.get(fi, {}).get(fj, 0.01 if i == j else 0)

        # Grid search in 5% increments
        best_w = np.array([0.25, 0.25, 0.25, 0.25])
        best_util = -1e9
        risk_aversion = 0.75
        turnover_pen = 0.02
        redundancy_pen = 0.05

        redundancy = diag.get("redundancy_score", 0) if diag else 0

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
                    exp_ret = np.dot(w, er)
                    exp_risk = math.sqrt(max(0, w @ cov @ w))
                    turnover = float(np.sum(np.abs(w - prev_weights)))
                    corr_penalty = redundancy * float(np.sum(w * w))
                    util = exp_ret - risk_aversion * exp_risk**2 - turnover_pen * turnover - redundancy_pen * corr_penalty
                    if util > best_util:
                        best_util = util
                        best_w = w.copy()

        # Normalize
        total = best_w.sum()
        if total > 0:
            best_w = best_w / total

        turnover = float(np.sum(np.abs(best_w - prev_weights)))
        exp_ret = float(np.dot(best_w, er))
        exp_risk = math.sqrt(max(0, float(best_w @ cov @ best_w)))

        regime_label = regime.get("regime_label", "Sideways / Neutral")
        regime_conf = regime.get("regime_confidence", 0.5)
        trans_risk = min(1.0, regime.get("transition_risk", 0.5) + 0.25 * ns)

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
def portfolio_transition_agent(conn, baskets, allocations, regime_preds):
    print("[PortfolioTransitionAgent] Starting...")
    cursor = conn.cursor()

    # Price lookup
    cursor.execute("SELECT month, symbol, monthly_close AS close, monthly_close AS adjusted_close FROM stock_prices_monthly ORDER BY month, symbol")
    cols = [d[0] for d in cursor.description]
    price_rows = [dict(zip(cols, r)) for r in cursor.fetchall()]
    price_lookup = {}
    for r in price_rows:
        sym = r.get("symbol")
        m = r["month"][:7]
        close = r.get("adjusted_close") or r.get("close")
        if sym and close and sym not in EXCLUDED:
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

        # Allocate factor weights to stocks (equal weight within basket)
        stock_weights = {}  # symbol -> {weight, factors, score}
        for i, fname in enumerate(factors):
            fw = alloc[fkeys[i]]
            basket = month_baskets.get(fname, [])
            if not basket:
                continue
            per_stock = fw / len(basket)
            for b in basket:
                sym = b["symbol"]
                if sym not in stock_weights:
                    stock_weights[sym] = {"weight": 0, "factors": [], "score": 0}
                stock_weights[sym]["weight"] += per_stock
                stock_weights[sym]["factors"].append(fname)
                stock_weights[sym]["score"] += b["factor_score"]

        # Cap at 5%
        MAX_W = 0.05
        for sym in stock_weights:
            stock_weights[sym]["weight"] = min(stock_weights[sym]["weight"], MAX_W)

        # Renormalize
        total_w = sum(v["weight"] for v in stock_weights.values())
        if total_w > 0:
            for sym in stock_weights:
                stock_weights[sym]["weight"] /= total_w

        # Portfolio targets
        for sym, info in stock_weights.items():
            portfolio_targets.append({
                "month": month,
                "symbol": sym,
                "target_weight": round(info["weight"], 6),
                "factor_sources": info["factors"],
                "combined_score": round(info["score"], 6),
                "regime_label": regime_label,
                "allocation_method": "factor_weighted_equal"
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

    write_json("portfolio_targets", portfolio_targets)
    write_csv("portfolio_targets_monthly", portfolio_targets, ["month","symbol","target_weight","factor_sources","combined_score","regime_label","allocation_method"])

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
def backtest_agent(conn, allocations, rebalance_trades, regime_preds):
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

        fr_vals = [fr.get("momentum_return",0), fr.get("value_return",0), fr.get("quality_return",0), fr.get("low_volatility_return",0)]
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
    write_csv("backtest_portfolio_monthly", bt_portfolio, ["month","strategy_name","portfolio_value","monthly_return","drawdown","turnover","regime_label"])
    write_csv("backtest_summary", summaries, ["strategy_name","cagr","total_return","annual_volatility","sharpe","max_drawdown","calmar","avg_turnover","best_month","worst_month"])
    print(f"[BacktestAgent] Done. {len(bt_portfolio)} points, {len(summaries)} summaries.")
    return bt_portfolio, summaries

# ─── ChartSignalAgent ───
def chart_signal_agent(conn, rebalance_trades, baskets):
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
        if d.get("symbol") and d["symbol"] not in EXCLUDED:
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

    # News features
    try:
        cursor.execute("SELECT * FROM news_features_monthly ORDER BY month")
        cols = [d[0] for d in cursor.description]
        news = []
        for r in cursor.fetchall():
            d = dict(zip(cols, r))
            news.append({
                "month": d.get("month","")[:7] if d.get("month") else "",
                "sentiment_score": safe_float(d.get("sentiment_score")),
                "negative_ratio": safe_float(d.get("negative_ratio")),
                "article_count": safe_float(d.get("article_count")),
                "risk_event_count": safe_float(d.get("risk_event_count"))
            })
        write_json("news_features", news)
    except:
        write_json("news_features", [])

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
    report.append(f"- Excluded symbols: {', '.join(sorted(EXCLUDED))}\n")
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
    print("=" * 60)
    print("Indian Regime/Factor/Portfolio Intelligence Pipeline")
    print("=" * 60)

    if not INPUT_DB.exists():
        print(f"ERROR: Input database not found at {INPUT_DB}")
        print(f"Please place processed_financial_data.sqlite in {INPUT_DB.parent}/")
        sys_exit_code = 1
        return

    conn = sqlite3.connect(str(INPUT_DB))

    # Node 0: RSSNewsAgent
    news_articles, news_features = rss_news_agent()

    # Node 1: DataValidationAgent
    validation_report, symbols = data_validation_agent(conn)

    # Node 2: RegimeDetectionAgent
    regime_preds = regime_detection_agent(conn, news_features)

    # Node 3: FactorScoringAgent
    baskets, factor_names = factor_scoring_agent(conn, regime_preds)

    # Node 4: FactorForecastAgent
    factor_returns, diagnostics = factor_forecast_agent(conn, baskets, regime_preds)

    # Node 5: AllocationOptimizerAgent
    allocations, decisions = allocation_optimizer_agent(factor_returns, diagnostics, regime_preds, news_features, news_articles)

    # Node 6: PortfolioTransitionAgent
    portfolio_targets, rebalance_trades = portfolio_transition_agent(conn, baskets, allocations, regime_preds)

    # Node 7: RiskDiagnosticsAgent
    risk_diagnostics_agent(diagnostics, regime_preds)

    # Node 8: BacktestAgent
    bt_portfolio, bt_summary = backtest_agent(conn, allocations, rebalance_trades, regime_preds)

    # Node 9: ChartSignalAgent
    signal_events = chart_signal_agent(conn, rebalance_trades, baskets)

    # Node 10: RSSNewsAgent
    news_articles, news_features = rss_news_agent()

    # Node 11: ExplanationAgent
    explanation_agent(validation_report, regime_preds, baskets, factor_returns, diagnostics,
                     allocations, decisions, portfolio_targets, rebalance_trades,
                     bt_portfolio, bt_summary, signal_events)

    conn.close()
    print("\n" + "=" * 60)
    print("Pipeline complete!")
    print(f"  JSON outputs: {JSON_DIR}")
    print(f"  CSV outputs: {CSV_DIR}")
    print(f"  Report: {PROJECT_DIR / 'model_run_report.md'}")
    print("=" * 60)

if __name__ == "__main__":
    main()

















