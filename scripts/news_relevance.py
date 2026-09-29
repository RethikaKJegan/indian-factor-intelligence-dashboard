"""Entity tagging and relevance scoring for fetched news articles.

Every article used to carry a sentiment score and a risk-event count with no
indication of *what* it was about. `symbols` and `relevance` were published as
null for the whole corpus. Two consequences, both of which reached the model
rather than staying cosmetic:

1. Nothing could tell a market article from a general-interest one. An item
   about a US Federal Reserve speech scored the same as an item about an RBI
   decision, and `news_stress_score` feeds the allocation optimiser, so an
   off-topic headline moved Indian factor weights.
2. Nothing linked an article to the 189-name universe, so "news about this
   portfolio" was not a question the data could answer.

This module tags each article with the Nifty 200 symbols and sectors named in
its text, and scores relevance from three independent signals:

  - a named symbol in the universe (strongest)
  - a named sector
  - Indian-market or macro vocabulary

A symbol mention is what makes a story decision-relevant, so the score is
weighted to favour it. Matching is done on word boundaries: `ABB` must not
match inside `ABBR`, and `M&M` must match whole, or short tickers produce a
constant low background of false hits.

Nothing here discards an article. Tagging is additive, and the caller decides
the threshold, so the published corpus stays auditable and the excluded set can
be inspected rather than being silently swallowed.
"""

from __future__ import annotations

import re

# Indian-market vocabulary. Presence of these terms is weak evidence on its
# own: a story can discuss crude or the rupee without being about Indian
# equities, which is why it scores less than a symbol match.
_MARKET_TERMS = (
    "nifty", "sensex", "bse", "nse", "sebi", "rbi", "repo rate", "repo rate",
    "monetary policy", "inflation", "iip", "g-sec", "bond yield", "rupee",
    "fii", "dii", "fpi", "crude", "brent", "sensex", "market cap",
    "quarterly results", "q1", "q2", "q3", "q4", "eps", "pe ratio", "p/e",
    "ipo", "block deal", "bulk deal", "stake sale", "buyback", "dividend",
    "index", "stock market", "share price", "equity", "brokerage",
    "mutual fund", "etf", "small cap", "mid cap", "large cap",
)

# Terms that indicate the story is not about Indian listed equities even when
# it shares vocabulary with them.
_OFF_TOPIC = (
    "recipe", "kobe bryant", "nba", "nfl", "cricket", "ipl match", "holiday",
    "movie", "box office", "celebrity", "temple", "school result", "board exam",
    "obituary", "recipe", "horoscope", "lottery result", "weather",
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).lower()


def _word_set(text: str) -> set[str]:
    """Split into comparable tokens.

    Tickers contain characters that plain `\w+` splits badly: `M&M` becomes
    `m` and `m`, `BAJAJ-AUTO` becomes `bajaj` and `auto`, and `3MINDIA` starts
    with a digit. Tokens are therefore normalised by removing separators but
    keeping alphanumerics together, and a separate set of long forms is kept
    for multi-word names.
    """
    return {t for t in re.findall(r"[a-z0-9&]+", _norm(text)) if t}


def build_matchers(symbols: list[str], sectors: list[str]) -> dict:
    """Pre-compile the lookup tables used by `score_article`.

    Compiled once per run rather than per article: an article-by-article regex
    compile across a few hundred articles is measurable, and the tables are
    fixed for the length of a run.
    """
    symbol_tokens: set[str] = set()
    for s in symbols:
        s = (s or "").strip()
        if not s:
            continue
        symbol_tokens.add(s.lower())
        symbol_tokens.add(re.sub(r"[^a-z0-9]", "", s.lower()))
    sector_tokens: set[str] = set()
    for s in sectors:
        s = (s or "").strip()
        if not s:
            continue
        sector_tokens.add(s.lower())
        for part in re.split(r"[&/]| and ", s.lower()):
            part = part.strip()
            if len(part) > 3:
                sector_tokens.add(part)
    return {
        "symbols": symbol_tokens,
        "sectors": sector_tokens,
    }


def score_article(title: str, summary: str, matchers: dict) -> dict:
    """Tag one article with the universe entities it names, and score relevance.

    Returns a dict with `symbols` (list of matched tickers), `sector_hits`
    (list of matched sector names), `relevance` (0..1) and `relevance_band`.
    `relevance_band` is published so a consumer can filter without having to
    invent its own threshold from the score.
    """
    text = _norm(f"{title} {title} {summary}")  # title weighted by repetition
    tokens = _word_set(text)
    flat = re.sub(r"[^a-z0-9]", "", text)

    matched: list[str] = []
    for s in matchers.get("symbols", ()):  # exact ticker token
        if s in tokens:
            matched.append(s.upper())
    # Tickers as substrings, for the normalised form ("3mindia" in prose).
    for s in matchers.get("symbols", ()):
        if len(s) >= 5 and s in flat and s not in tokens:
            matched.append(s.upper())
    matched = sorted(set(matched))

    sector_hits = sorted(
        {s for s in matchers.get("sectors", ()) if s in tokens or s in flat}
    )

    market_terms = sum(1 for t in _MARKET_TERMS if t in text)
    off_topic = sum(1 for t in _OFF_TOPIC if t in text)

    # Weighted so a named constituent outranks generic vocabulary, which is
    # the ordering that matches what makes a story actionable.
    score = 0.0
    if matched:
        score += 0.55
    if sector_hits:
        score += 0.20
    if market_terms:
        score += min(0.25, 0.05 * market_terms)
    if off_topic:
        score -= 0.45 * min(2, off_topic)
    score = max(0.0, min(1.0, score))

    if score >= 0.55:
        band = "high"
    elif score >= 0.25:
        band = "medium"
    elif score > 0.0:
        band = "low"
    else:
        band = "off_topic"

    return {
        "symbols": matched,
        "sector_hits": sector_hits,
        "relevance": round(score, 4),
        "relevance_band": band,
    }


def relevance_summary(articles: list[dict]) -> dict:
    """Aggregate coverage, published so the corpus can be judged, not assumed."""
    total = len(articles)
    if not total:
        return {
            "articles": 0,
            "tagged_with_symbols": 0,
            "symbol_tag_pct": 0.0,
            "bands": {},
            "tagged_article_id": None,
        }
    bands: dict[str, int] = {}
    tagged = 0
    tagged_id = None
    for a in articles:
        b = a.get("relevance_band") or "low"
        bands[b] = bands.get(b, 0) + 1
        if a.get("symbols"):
            tagged += 1
            if tagged_id is None:
                tagged_id = a.get("article_id")
    return {
        "articles": total,
        "tagged_with_symbols": tagged,
        "symbol_tag_pct": round(100.0 * tagged / total, 1),
        "bands": dict(sorted(bands.items(), key=lambda kv: -kv[1])),
        "tagged_article_id": tagged_id,
    }
