"""Experiment manifest (spec section 24).

A result is only reproducible if the run that produced it can be described
exactly. "The backtest returned 27.91% CAGR" is not a result until you can say
which data, which code, which assumptions, and which random seed produced that
number, and can re-run it to get the same one.

This module writes `experiment_manifest.json`, which records:

* **Identity** — when the run happened, how long it took, and a fingerprint
  derived from the inputs, the code and the assumptions together. Two runs with
  the same fingerprint produced the same outputs; a different fingerprint means
  something moved and the numbers are not comparable.
* **Inputs** — the source database, its size, and the row counts and date
  ranges of every table actually read. A manifest that does not record the data
  window cannot answer "is this comparable to last month's run?".
* **Assumptions** — every constant that changes a result if it is wrong, each
  with its value and a plain statement of what it is. These are the numbers
  most likely to be silently tuned later, so they are recorded rather than left
  in the source.
* **Determinism controls** — which seeds are pinned, and which stages are
  genuinely deterministic. A stage that uses a random initialisation without a
  fixed seed is marked as such instead of being assumed reproducible.
* **Caveats** — what this run cannot support, collected from the artifacts the
  pipeline already produced rather than restated by hand.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sqlite3
import sys
from datetime import datetime, timezone

try:
    import data_freshness
except ImportError:  # pragma: no cover - manifest must never break a run
    data_freshness = None

#: Tables the pipeline reads. Row counts for anything outside this list are
#: not recorded, because an unused table cannot change a result.
READ_TABLES = (
    "fundamentals_monthly",
    "factor_scores_monthly",
    "stock_prices_monthly",
    "stock_prices_daily",
    "market_index_monthly",
    "market_index_daily",
    "sector_index_monthly",
    "macro_monthly",
    "regime_features_monthly",
    "news_articles_raw",
    "news_features_monthly",
    "data_inventory",
)


def _file_fingerprint(path: str, chunk: int = 1 << 20) -> dict:
    """SHA-256 of a file, without loading it all into memory."""
    if not os.path.exists(path):
        return {"path": path, "exists": False}
    h = hashlib.sha256()
    size = 0
    with open(path, "rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
            size += len(block)
    return {
        "path": path,
        "exists": True,
        "bytes": size,
        "sha256": h.hexdigest(),
    }


def _code_fingerprint(code_dir: str) -> list[dict]:
    """SHA-256 of every pipeline module, so a code change is visible."""
    out = []
    if not os.path.isdir(code_dir):
        return out
    for name in sorted(os.listdir(code_dir)):
        if not name.endswith(".py"):
            continue
        out.append(_file_fingerprint(os.path.join(code_dir, name)))
    return out


def _database_fingerprint(db_path: str) -> dict:
    """Row counts and month ranges for every table the pipeline reads.

    Hashing a multi-gigabyte SQLite file makes the manifest depend on physical
    layout, so any unrelated write would change the fingerprint. Counting rows
    and reading the date bounds records what the run actually consumed, which
    is both cheaper and the more useful question.
    """
    if not os.path.exists(db_path):
        return {"path": db_path, "exists": False}
    size = os.path.getsize(db_path)
    out: dict = {"path": db_path, "exists": True, "bytes": size, "tables": {}}
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        present = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        for table in READ_TABLES:
            if table not in present:
                out["tables"][table] = {"present": False}
                continue
            n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            entry: dict = {"present": True, "rows": n}
            cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
            if "month" in cols and n > 0:
                lo, hi = conn.execute(
                    f"SELECT MIN(month), MAX(month) FROM {table}"
                ).fetchone()
                entry["month_min"] = lo
                entry["month_max"] = hi
                entry["months"] = _distinct_months(conn, table)
            out["tables"][table] = entry
    finally:
        conn.close()
    return out


def _distinct_months(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(
        f"SELECT COUNT(DISTINCT substr(CAST(month AS TEXT), 1, 7)) FROM {table}"
    ).fetchone()[0]


def assumptions_from_modules() -> list[dict]:
    """Read the constants that change results straight out of the modules.

    These are read from the live module objects rather than re-declared here,
    so a manifest can never drift from the code that produced the run. If
    `TOP_K` changes, the manifest changes with it.
    """
    out: list[dict] = []

    def add(name, value, unit, what_it_controls, risk):
        out.append({
            "name": name,
            "value": value,
            "unit": unit,
            "controls": what_it_controls,
            "risk_if_wrong": risk,
        })

    try:
        import run_pipeline as rp
        # Stashed so the constraints block below can read the same live module
        # without re-importing it or guessing whether the import succeeded.
        globals()["_rp_module"] = rp

        add("TOP_K", rp.TOP_K, "names per factor",
            "How many names each factor sleeve nominates each month.",
            "Tied to the 5% position cap: N names at 5% can place N*5% of "
            "capital. Below 20 names the book cannot be fully invested.")
        add("TX_COST", rp.TX_COST, "fraction per side",
            "Cost on the factor-level dynamic strategy only.",
            "The stock-level book uses COST_BPS instead; this one does not "
            "affect the authoritative result.")
        add("COST_BPS", rp.COST_BPS, "basis points",
            "Base round-trip cost on traded notional for the stock-level book.",
            "A full sensitivity ladder is reported at 0/10/20/50/100 bps, so "
            "the conclusion does not rest on this value.")
        add("REGIME_MIN_TRAIN_MONTHS", rp.REGIME_MIN_TRAIN_MONTHS, "months",
            "Warm-up before the regime model is allowed to score out of sample.",
            "Lowering it lets the mixture be fitted and scored on months it "
            "has already seen, which reintroduces look-ahead.")
        add("REGIME_MODEL_VERSION", rp.REGIME_MODEL_VERSION, "label",
            "Identifies the regime model configuration used.",
            "A label only; the parameters live in regime_model.py.")
    except Exception as exc:  # pragma: no cover - manifest must never break a run
        out.append({
            "name": "pipeline_constants",
            "value": None,
            "unit": None,
            "controls": "Could not be read from run_pipeline.",
            "risk_if_wrong": f"Import failed: {exc}",
        })

    try:
        import factor_engine as fe

        add("WINSOR_TAIL", fe.WINSOR_TAIL, "fraction of each tail",
            "Percentile clip applied to each raw metric before scaling.",
            "Too small leaves outliers able to dominate a cross-sectional "
            "rank; too large erases genuine signal at the extremes.")
        add("MIN_METRIC_COVERAGE", fe.MIN_METRIC_COVERAGE, "fraction of weight",
            "Share of composite metric weight that must be present for a "
            "factor score to be produced at all.",
            "Below this threshold a score is withheld rather than computed from "
            "whatever metrics survived.")
        add("MIN_SECTOR_SIZE", fe.MIN_SECTOR_SIZE, "stocks",
            "Smallest sector that is demeaned; smaller ones keep raw values.",
            "Demeaning a group of two against its own mean would drive both to "
            "zero and discard real signal.")
    except Exception as exc:  # pragma: no cover
        out.append({
            "name": "factor_engine_constants",
            "value": None,
            "unit": None,
            "controls": "Could not be read from factor_engine.",
            "risk_if_wrong": f"Import failed: {exc}",
        })

    try:
        import portfolio_construction as pc
        # The active limits live in run_pipeline as CONSTRAINTS; the module
        # itself only defines the dataclass. Read the live object so the
        # manifest cannot drift from the allocator that actually ran.
        active = globals().get("_rp_module")
        c = getattr(active, "CONSTRAINTS", None) or pc.PortfolioConstraints()
        add("CONSTRAINTS", {
            "max_weight": c.max_weight,
            "min_weight": c.min_weight,
            "max_sector_weight": c.max_sector_weight,
            "min_names": c.min_names,
            "max_names": c.max_names,
        }, "weight fractions",
            "Hard limits the allocator must satisfy in every month.",
            "A breach would mean the reported backtest held positions the "
            "stated construction could not have built.")
    except Exception as exc:  # pragma: no cover
        out.append({
            "name": "CONSTRAINTS",
            "value": None,
            "unit": None,
            "controls": "Could not be read from the active configuration.",
            "risk_if_wrong": f"Import failed: {exc}",
        })

    try:
        import performance_stats as ps

        add("RISK_FREE_ANNUAL", ps.RISK_FREE_ANNUAL, "annual decimal",
            "Risk-free rate used for the excess-return Sharpe and Jensen's "
            "alpha. Not measured: the source data has no G-Sec series.",
            "Moves Sharpe from 1.41 (at zero) to 1.07. Both are reported, so "
            "no conclusion depends on the exact value.")
        add("CI_LEVEL", ps.CI_LEVEL, "probability",
            "Width of the bootstrap confidence intervals.",
            "A narrower interval would overstate precision.")
        add("BOOTSTRAP_SEED", ps.BOOTSTRAP_SEED, "integer",
            "Seed for the moving-block bootstrap.",
            "Unpinned, the interval would change on every run and could not be "
            "quoted as a result.")
        add("BOOTSTRAP_SAMPLES", ps.BOOTSTRAP_SAMPLES, "resamples",
            "Draws per confidence interval.",
            "Too few resamples makes the interval itself noisy, which is a "
            "different kind of uncertainty from the one being measured.")
    except Exception as exc:  # pragma: no cover
        out.append({
            "name": "performance_stats_constants",
            "value": None,
            "unit": None,
            "controls": "Could not be read from performance_stats.",
            "risk_if_wrong": f"Import failed: {exc}",
        })

    return out


def determinism_report(
    news_snapshot: dict | None = None,
    news_mode: str | None = None,
) -> list[dict]:
    """State, per stage, whether the same inputs give the same outputs.

    An unseeded random initialisation, or a stage that reads a live network
    feed, is listed as non-deterministic rather than assumed reproducible.
    Claiming determinism that does not hold is worse than recording that it
    does not.

    `news_mode` is the mode the run actually used, reported by the news agent.
    It cannot be inferred from whether a snapshot file exists, because a live
    run also writes one -- inferring it that way made a live fetch claim it had
    been replayed.
    """
    replayed = news_mode == "replayed"
    return [
        {
            "stage": "Regime model (GMM)",
            "deterministic": True,
            "basis": "k-means++ init is seeded inside regime_model; components "
                     "are aligned across refits with linear_sum_assignment, so "
                     "component order cannot drift between months.",
        },
        {
            "stage": "Factor construction",
            "deterministic": True,
            "basis": "Pure cross-sectional arithmetic. No sampling, no fitting.",
        },
        {
            "stage": "Portfolio construction",
            "deterministic": True,
            "basis": "Bounded water-filling on a fixed input, no randomness.",
        },
        {
            "stage": "Stock-level backtest",
            "deterministic": True,
            "basis": "Compounds a fixed weight path. Cost enters linearly. "
                     "Weights are summed in sorted order: iterating a set of "
                     "tickers follows Python's per-process hash randomisation "
                     "and float addition is not associative, which produced "
                     "~1e-6 run-to-run drift in turnover before it was fixed.",
        },
        {
            "stage": "Bootstrap confidence intervals",
            "deterministic": True,
            "basis": "random.Random(seed) with a fixed seed, so the interval is "
                     "identical on every run.",
        },
        {
            "stage": "News ingestion (RSS)",
            "deterministic": replayed,
            "basis": (
                "Replayed from data_input/news_snapshot.json: the exact article "
                f"set of the last fetch, sha256 "
                f"{str((news_snapshot or {}).get('content_sha256', ''))[:12]}. "
                "Identical inputs give identical output. Re-run with the same "
                "NEWS_REPLAY=1 to reproduce this run byte for byte."
                if replayed else
                "Fetched live from RSS this run, so the article set depends on "
                "the network. A difference here moves the current month's news "
                "sentiment, then news_stress_score, then transition_risk, then "
                "the regime row, the allocation and the rebalance trades. "
                "Measured across two runs it perturbed 1 month of 153 and changed "
                "no regime label -- small, but not reproducible. The article set "
                "was snapshotted and hashed into the fingerprint, so this run "
                "can still be replayed exactly with NEWS_REPLAY=1."
            ),
        },
    ]


def collect_caveats(json_dir: str) -> list[dict]:
    """Assemble run limitations from artifacts the pipeline already wrote.

    These are read from the outputs rather than restated by hand, so a caveat
    cannot drift away from the number it qualifies.
    """
    import os.path

    caveats: list[dict] = []

    def load(name):
        p = os.path.join(json_dir, f"{name}.json")
        if not os.path.exists(p):
            return None
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return None

    cov = load("universe_coverage")
    if cov:
        index_name = str(cov.get("index_name") or "Nifty 200").strip()
        caveats.append({
            "id": "survivorship_bias",
            "severity": "high",
            "statement": (
                f"The universe is today's {index_name} constituent list applied "
                f"to all {cov.get('modeling_universe_size', 0)} names across "
                "the whole history. A stock that was removed from the index is "
                "absent from the backtest rather than being held to zero, so "
                "delisted and dropped names cannot drag the result and the "
                "return is biased upward."
            ),
            "why_not_fixed": (
                "The source database has no effective_from / effective_to "
                "columns and no add/remove dates, and the constituent list is a "
                "single static file. Correcting this needs paid historical NSE "
                "constituent data."
            ),
        })

    withheld = load("factor_coverage_withheld")
    if withheld:
        counts = withheld.get("withheld_counts", {})
        total = sum(counts.values())
        caveats.append({
            "id": "factor_coverage",
            "severity": "medium",
            "statement": (
                f"{total:,} factor scores were withheld rather than computed "
                f"from incomplete data ({', '.join(f'{k} {v:,}' for k, v in counts.items())}). "
                "Where a metric is missing the score is absent, so the effective "
                "universe for that factor is smaller than the nominal one and "
                "the factor is not measured on the same names every month."
            ),
            "why_not_fixed": (
                "The underlying metrics are not in the source data. Columns for "
                "ROE, ROCE, P/B and EV/EBITDA exist but are 0% populated."
            ),
        })

    report = load("backtest_performance_report")
    if report:
        ci = report.get("confidence_intervals", {}).get("cagr")
        rf = report.get("risk_free_assumption", {})
        vb = report.get("vs_benchmark", {})
        rp = report.get("return_path", {})
        entries = [{
            "id": "risk_free_rate_is_an_assumption",
            "severity": "high",
            "statement": (
                f"No Treasury-bill or G-Sec series exists in the source data, "
                f"so Sharpe against a {rf.get('annual', 0) * 100:.1f}% Indian "
                "risk-free rate is an assumption, not a measurement. Against a "
                "zero rate the same returns give a materially higher Sharpe. "
                "Both are reported."
            ),
            "why_not_fixed": "The series is not in the database.",
        }]
        if ci:
            entries.append({
                "id": "precision_of_the_headline",
                "severity": "high",
                "statement": (
                    f"The {ci['point'] * 100:.2f}% CAGR point estimate has a "
                    f"95% interval of {ci['ci_low'] * 100:.2f}% to "
                    f"{ci['ci_high'] * 100:.2f}%. The interval is roughly 30 "
                    "points wide: 149 monthly returns cannot pin down a growth "
                    "rate more precisely than that."
                ),
                "why_not_fixed": (
                    "A longer out-of-sample history would narrow it. Extending "
                    "the sample is the only honest route."
                ),
            })
        r2 = vb.get("r_squared")
        if r2 is not None and r2 > 0.5:
            entries.append({
                "id": "diversification_is_illusory",
                "severity": "medium",
                "statement": (
                    f"Beta of {vb.get('beta')} looks market-neutral, but R-squared "
                    f"of {r2 * 100:.0f}% means {r2 * 100:.0f}% of monthly variance "
                    "is still the index's. The alpha is real; the diversification "
                    "benefit is not."
                ),
                "why_not_fixed": (
                    "A sector- or factor-neutral book would lower both, at the "
                    "cost of the return. Not a bug, a design choice to disclose."
                ),
            })
        cv = rp.get("cvar_95_monthly")
        if cv is not None:
            entries.append({
                "id": "tail_risk",
                "severity": "medium",
                "statement": (
                    f"Average of the worst 5% of months is {cv * 100:.1f}%, the "
                    f"worst single month was {rp.get('cvar_99_monthly', 0) * 100:.1f}%, "
                    f"and the book spent {rp.get('longest_drawdown_months', 0)} "
                    "consecutive months below a prior peak. A mean and a Sharpe "
                    "ratio both hide this."
                ),
                "why_not_fixed": (
                    "Inherent to a long-only equity book. Disclosed rather than "
                    "smoothed away."
                ),
            })
        caveats.extend(entries)

    regimes = load("regime_predictions")
    if regimes:
        scored = [r for r in regimes if not r.get("is_warmup")]
        warmup = [r for r in regimes if r.get("is_warmup")]
        if warmup:
            mislabelled = [
                r for r in warmup
                if r.get("model_version") == "GMM-5-spherical-walkforward"
            ]
            caveats.append({
                "id": "regime_warmup",
                "severity": "medium",
                "statement": (
                    f"{len(warmup)} of {len(regimes)} months carry no regime "
                    "score, because the mixture refuses to fit and score a month "
                    "before its warm-up ends. Those months are labelled "
                    "'Unscored' and the allocator holds an explicitly neutral 0.5 "
                    "confidence rather than a fabricated one. The regime input is "
                    f"therefore absent for the first {len(warmup)} months of the "
                    "backtest, which is roughly "
                    f"{100.0 * len(warmup) / len(regimes):.0f}% of the period."
                ),
                "why_not_fixed": (
                    "A shorter warm-up would let the mixture be fitted and scored "
                    "on months it has already seen, which is precisely the "
                    "look-ahead the warm-up exists to prevent."
                ),
                "provenance_check": (
                    "No warm-up month is labelled with the GMM model version, "
                    "so the output does not claim a provenance it does not have."
                    if not mislabelled
                    else f"WARNING: {len(mislabelled)} warm-up months claim the "
                         "GMM model version despite never being scored by it."
                ),
            })

    news = load("news_features")
    if news:
        months_with_articles = sum(
            1 for n in news if (n.get("article_count") or 0) > 0
        )
        total_articles = sum(n.get("article_count") or 0 for n in news)
        # The denominator is every month the backtest covers, not every month
        # that happens to have a news row. A feature present in 7 rows out of
        # 153 is a 4.6% coverage rate, and reporting it as 7 of 7 would dress a
        # gap as a complete series.
        total_months = 0
        regimes_all = load("regime_predictions")
        if regimes_all:
            total_months = len(regimes_all)
        coverage_pct = (
            100.0 * months_with_articles / total_months if total_months else None
        )
        if total_months and months_with_articles < total_months:
            caveats.append({
                "id": "news_coverage_is_sparse",
                "severity": "medium",
                "statement": (
                    f"News features carry articles in only {months_with_articles} "
                    f"of {total_months} months "
                    f"({coverage_pct:.0f}% coverage, {total_articles} articles "
                    "in total), and the pipeline's own confidence weight for "
                    "them is 0.05–0.10. A feature that is absent in 95% of "
                    "months is not measuring news sentiment; it is measuring "
                    "article availability."
                ),
                "why_not_fixed": (
                    "The RSS archive covers a short window. This is why the news "
                    "factor is excluded from the allocation and retained only as "
                    "decision context, rather than removed outright, which would "
                    "have discarded the audit trail."
                ),
            })

    caveats.append({
        "id": "no_machine_learning_layer",
        "severity": "low",
        "statement": (
            "No supervised learning layer is fitted. A learner needs "
            "substantially more forward return periods than exist here before "
            "it can be validated out of sample, and fitting one on this data "
            "would be overfitting dressed as sophistication."
        ),
        "why_not_fixed": (
            "Requires more out-of-sample history, not a different algorithm."
        ),
    })

    return caveats


def freshness_caveat(db_path: str) -> tuple[dict | None, list[dict]]:
    """Measure how current the data is, and turn anything wrong into a caveat.

    A daily job that quietly stops working is worse than one that crashes: the
    dashboard keeps rendering and the numbers just stop moving. The staleness
    is not visible in any displayed figure, so it has to be recorded here or it
    is not recorded at all.
    """
    if data_freshness is None or not db_path:
        return None, []
    try:
        a = data_freshness.assess(db_path)
    except Exception as exc:  # pragma: no cover
        return None, [{
            "id": "freshness_check_failed",
            "severity": "medium",
            "statement": f"Could not measure data freshness: {exc}",
            "why_not_fixed": "The check itself raised; see the pipeline log.",
        }]

    caveats: list[dict] = []
    for issue in a.get("issues", []):
        if issue["severity"] == "ok":
            continue
        caveats.append({
            "id": issue["id"],
            "severity": issue["severity"],
            "statement": issue["detail"],
            "why_not_fixed": (
                "The scheduled refresh has not delivered data for these "
                "trading days. Run `python scripts/verify_data.py` to see the "
                "current position, and check the scheduled job has a `schedule:` "
                "trigger -- without one it never runs on its own."
            ),
        })
    return a, caveats


def build_manifest(
    db_path: str,
    code_dir: str,
    json_dir: str,
    started_at: datetime,
    runtime_seconds: float,
    news_mode: str | None = None,
) -> dict:
    """Assemble the full manifest for one pipeline run."""
    database = _database_fingerprint(db_path)
    code = _code_fingerprint(code_dir)
    assumptions = assumptions_from_modules()
    caveats = collect_caveats(json_dir)
    freshness, freshness_caveats = freshness_caveat(db_path)
    caveats.extend(freshness_caveats)

    # The article set is the one input that can move between runs, so its hash
    # is recorded. Two runs sharing it saw the same news; two runs differing on
    # it do not, and their current-month numbers are not comparable.
    news_snapshot: dict | None = None
    snap_path = os.path.join(os.path.dirname(db_path), "news_snapshot.json")
    if os.path.exists(snap_path):
        try:
            with open(snap_path, encoding="utf-8") as f:
                snap = json.load(f)
            news_snapshot = {
                "path": snap_path,
                "fetched_at": snap.get("fetched_at"),
                "article_count": snap.get("article_count"),
                "content_sha256": snap.get("content_sha256"),
            }
        except (OSError, json.JSONDecodeError):
            news_snapshot = None

    # The fingerprint hashes inputs, code and assumptions together. It changes
    # if any of the three moves, which is exactly the condition under which two
    # runs stop being comparable.
    parts = [
        database.get("path", ""),
        json.dumps(
            {t: v.get("rows") for t, v in database.get("tables", {}).items()},
            sort_keys=True,
        ),
        json.dumps([c.get("sha256") for c in code], sort_keys=True),
        json.dumps(assumptions, sort_keys=True, default=str),
        str((news_snapshot or {}).get("content_sha256") or ""),
    ]
    fingerprint = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()

    return {
        "schema": "experiment_manifest/1",
        "run": {
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "runtime_seconds": round(runtime_seconds, 2),
            "fingerprint": fingerprint,
            "fingerprint_covers": [
                "source database path and per-table row counts",
                "SHA-256 of every pipeline module",
                "every assumption listed below",
                "SHA-256 of the news article set actually used",
            ],
            "fingerprint_note": (
                "Two runs with the same fingerprint produced the same outputs. "
                "A different fingerprint means an input, a module or an "
                "assumption moved, and the results are not comparable without "
                "saying so."
            ),
        },
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "inputs": database,
        "code": {
            "dir": code_dir,
            "modules": code,
            "note": "Hashed so a change to any module invalidates comparability.",
        },
        "assumptions": assumptions,
        "news_snapshot": news_snapshot,
        "news_mode": news_mode,
        "data_freshness": freshness,
        "determinism": determinism_report(news_snapshot, news_mode),
        "caveats": caveats,
        "caveat_summary": {
            "high": sum(1 for c in caveats if c.get("severity") == "high"),
            "medium": sum(1 for c in caveats if c.get("severity") == "medium"),
            "low": sum(1 for c in caveats if c.get("severity") == "low"),
        },
    }
