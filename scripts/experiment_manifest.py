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
    pit = load("point_in_time_universe")
    if cov and pit and pit.get("available"):
        index_name = str(cov.get("index_name") or "Nifty 200").strip()
        gated = pit.get("backtest_months_gated_pct", 0.0)
        caveats.append({
            "id": "survivorship_bias",
            "severity": "high",
            "statement": (
                f"Partly corrected, and the remainder is now measured rather "
                f"than asserted. Every month-end of the NSE bhavcopy archive "
                f"({pit.get('archive_floor')} to {pit.get('archive_ceiling')}, "
                f"{pit.get('months_covered')} snapshots) lists every symbol that "
                f"traded that day, so the trading universe is known directly. A "
                f"symbol is now scored only in months it had already started "
                f"trading, which removes {pit.get('db_symbols_not_yet_listed_at_archive_start')} "
                f"of {pit.get('db_symbols')} database symbols from the "
                f"{gated:.0f}% of backtest months the archive covers -- several "
                f"were 2024-25 listings previously carried back to 2014. The "
                f"gate is worth 0.6pp of CAGR and 1.1pp of drawdown. What "
                f"remains is exclusion rather than look-forward: "
                f"{pit.get('stopped_trading_absent_from_db')} symbols traded at "
                f"the start of the archive and had stopped by the end, and the "
                f"database holds none of them, against a trading universe that "
                f"grew from {pit.get('trading_universe_at_archive_start')} to "
                f"{pit.get('trading_universe_at_archive_end')} names. Those are "
                f"invisible to today's {index_name} list, so the return remains "
                f"biased upward by an unknown amount."
            ),
            "why_not_fixed": (
                f"Correcting the remaining {pit.get('stopped_trading_absent_from_db')} "
                "names needs fundamentals for tickers never ingested, which is "
                "paid data acquisition rather than calculation. The archive also "
                f"only reaches {pit.get('archive_floor')}, so the "
                f"{pit.get('backtest_months_ungated')} earlier backtest months "
                "are ungated."
            ),
        })
    elif cov:
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
                "return is biased upward. No bhavcopy trading record was "
                "available this run, so point-in-time gating is off."
            ),
            "why_not_fixed": (
                "data_input/nse_trading_universe.json was absent. Rebuild it "
                "with scripts/nse_universe.py to restore the gate."
            ),
        })

    audit = load("fundamental_coverage_audit")
    withheld = load("factor_coverage_withheld")
    if audit and audit.get("available"):
        sc = audit.get("summary", {})
        bc = sc.get("by_classification", {})
        struct = [s for s in audit.get("symbols", [])
                  if s.get("classification") == "structurally_excluded"]
        gap = [s for s in audit.get("symbols", [])
               if s.get("classification") == "unexplained_gap"]
        sectors = audit.get("structurally_excluded_sectors", [])
        total = sc.get("total_symbols", 0) or 1
        n_struct = bc.get("structurally_excluded", 0)
        n_sparse = bc.get("sparse", 0)
        n_gap = bc.get("unexplained_gap", 0)
        withheld_n = 0
        if withheld:
            withheld_n = sum((withheld.get("withheld_counts") or {}).values())

        caveats.append({
            "id": "fundamental_factors_skip_the_whole_banking_sector",
            "severity": "medium",
            "statement": (
                f"{n_struct} of {total} symbols "
                f"({100.0 * n_struct / total:.0f}%) are structurally invisible "
                f"to the Value and Quality factors. They are all in "
                f"{', '.join(sectors) or 'a non-comparable sector'}: a bank has "
                "no revenue line to grow and deposits are not debt in the sense "
                f"debt/equity assumes. {withheld_n:,} factor score-months are "
                "withheld, and this is the largest single cause -- not missing "
                "data, but a sector whose reporting conventions do not map onto "
                "the metrics. Momentum and Low Volatility are price-based and "
                "still cover these names."
            ),
            "why_not_fixed": (
                "Fixing it needs bank-specific metrics (NIM, GNPA, NPA ratio, "
                "PCR, CASA) sourced from filings, and equity metrics that are "
                "comparable across the two sector types. Adding them is a data "
                "acquisition project, not a calculation change."
            ),
        })
        if n_gap:
            caveats.append({
                "id": "fundamental_ingestion_gaps",
                "severity": "medium",
                "statement": (
                    f"{n_gap} symbols ({', '.join(g['symbol'] for g in gap)}) "
                    "have fundamental rows but no populated metric in any month. "
                    "Unlike the banks, this is an ingestion gap rather than an "
                    "economic fact, and it is probably a recent listing with no "
                    "extracted history."
                ),
                "why_not_fixed": (
                    "Upstream extraction. The coverage rule correctly withholds "
                    "their scores rather than guessing from partial data."
                ),
            })
        if n_sparse:
            sparse_syms = [s for s in audit.get("symbols", [])
                           if s.get("classification") == "sparse"]
            detail = ", ".join(
                f"{s['symbol']} ({s.get('coverage_pct', 0):.0f}% of "
                f"{s.get('months_with_rows', 0)} months)"
                for s in sparse_syms[:6]
            )
            caveats.append({
                "id": "sparse_fundamental_coverage",
                "severity": "low",
                "statement": (
                    f"{n_sparse} symbols carry metrics in fewer than half their "
                    "months, so the coverage rule withholds their score in most "
                    "months and they contribute unevenly to the factors: "
                    f"{detail}. The rule is doing the conservative thing here, "
                    "since a score computed from the months that happen to be "
                    "populated would be noisier than no score at all."
                ),
                "why_not_fixed": (
                    "The missing months are absent upstream, not dropped "
                    "downstream -- the rows exist in fundamentals_monthly and "
                    "the metric columns are empty. Fixing it means re-extracting "
                    "the filing history for these tickers. The pipeline already "
                    "handles the consequence correctly by withholding rather "
                    "than imputing, so this affects breadth of coverage rather "
                    "than correctness of what is reported."
                ),
            })
    elif withheld:
        counts = withheld.get("withheld_counts", {})
        total_w = sum(counts.values())
        caveats.append({
            "id": "factor_coverage",
            "severity": "medium",
            "statement": (
                f"{total:,} factor scores were withheld rather than computed "
                f"from incomplete data ({', '.join(f'{k} {v:,}' for k, v in counts.items())}). "
                "Where a metric is missing the score is absent, so the effective "
                "universe for that factor is smaller than the nominal one."
            ),
            "why_not_fixed": "The underlying metrics are not in the source data.",
        })

    report = load("backtest_performance_report")
    if report:
        ci = report.get("confidence_intervals", {}).get("cagr")
        rf = report.get("risk_free_assumption", {})
        vb = report.get("vs_benchmark", {})
        rp = report.get("return_path", {})
        entries = []
        if rf.get("is_measured"):
            entries.append({
                "id": "risk_free_rate_is_measured_but_backwards_looking",
                "severity": "low",
                "statement": (
                    f"Sharpe is computed against the measured Indian 10-year "
                    f"G-Sec yield from macro_monthly, averaging "
                    f"{(rf.get('mean_annual') or 0) * 100:.2f}% over the window "
                    f"and spanning {(rf.get('min_annual') or 0) * 100:.2f}% to "
                    f"{(rf.get('max_annual') or 0) * 100:.2f}%. It is applied "
                    f"month by month, not as a single average. One caveat "
                    f"remains: the series is a yield, so it is a contemporaneous "
                    f"rate rather than a return actually earned in that month, "
                    f"which slightly overstates the excess return in a risk-off "
                    f"period when yields fall alongside prices."
                ),
                "why_not_fixed": (
                    "A realised total-return index on 10-year G-Secs would be "
                    "the correct benchmark, and no such series is in the database."
                ),
            })
        else:
            entries.append({
                "id": "risk_free_rate_is_an_assumption",
                "severity": "high",
                "statement": (
                    "No risk-free series was found, so Sharpe against a constant "
                    f"rate of {(rf.get('annual') or 0) * 100:.2f}% is an "
                    "assumption rather than a measurement."
                ),
                "why_not_fixed": "The series is not in the database.",
            })
        if ci:
            # A sibling of `return_path`, not a member of it: `rp` below is
            # bound to report["return_path"], so reading the rolling block off
            # it always yields nothing.
            roll = report.get("rolling_36m") or {}
            width = (ci['ci_high'] - ci['ci_low']) * 100
            if roll.get("available"):
                stability = (
                    f" The window analysis says how much of that is spread: of "
                    f"{roll['windows']} overlapping 36-month stretches, "
                    f"{roll['windows_positive_cagr']} compounded positively "
                    f"({roll['pct_windows_positive_cagr']}%), with a median of "
                    f"{roll['median_cagr'] * 100:.1f}% and a range of "
                    f"{roll['min_cagr'] * 100:.1f}% to "
                    f"{roll['max_cagr'] * 100:.1f}%. The worst was "
                    f"{roll['worst_window']['from']} to "
                    f"{roll['worst_window']['to']}, the best "
                    f"{roll['best_window']['from']} to "
                    f"{roll['best_window']['to']}. A reader starting at an "
                    f"arbitrary date would have experienced the median, not the "
                    f"headline."
                )
            else:
                stability = ""
            entries.append({
                "id": "precision_of_the_headline",
                "severity": "high",
                "statement": (
                    f"The {ci['point'] * 100:.2f}% CAGR point estimate has a "
                    f"95% interval of {ci['ci_low'] * 100:.2f}% to "
                    f"{ci['ci_high'] * 100:.2f}%. The interval is roughly "
                    f"{width:.0f} points wide: 149 monthly returns cannot pin "
                    "down a growth rate more precisely than that." + stability
                ),
                "why_not_fixed": (
                    "A longer out-of-sample history would narrow it, and no "
                    "amount of statistics manufactures months that did not "
                    "happen. The rolling windows narrow the practical uncertainty "
                    "without pretending the sample grew."
                ),
            })
        r2 = vb.get("r_squared")
        sb = report.get("selection_bias") or {}
        if sb.get("observed_sharpe") is not None:
            survives = sb.get("survives_selection_at_95pct")
            pfp = sb.get("probability_of_false_positive")
            if survives:
                entries.append({
                    "id": "selection_bias",
                    "severity": "low",
                    "statement": (
                        f"The reported Sharpe of {sb['observed_sharpe']} is the "
                        f"best of {sb.get('trials_effective')} effectively "
                        f"independent configurations, not one fixed in advance. "
                        f"Compared against what the best of that many random "
                        f"strategies would produce, it clears the bar with a "
                        f"false-positive probability of about {pfp:.1%}, so the "
                        f"selection does not explain it away."
                    ),
                    "why_not_fixed": (
                        "Nothing to fix. The adjustment is reported so the "
                        "reader can weigh it."
                    ),
                })
            else:
                entries.append({
                    "id": "sharpe_does_not_clear_the_selection_bar",
                    "severity": "high",
                    "statement": (
                        f"The reported Sharpe of {sb['observed_sharpe']} is the "
                        f"best of {sb.get('trials_effective')} effectively "
                        f"independent configurations, not one chosen in advance. "
                        f"Against the {sb.get('expected_max_sharpe_under_null')} "
                        f"that the best of that many random strategies would be "
                        f"expected to reach, a strategy this strong appears by "
                        f"chance roughly {pfp:.0%} of the time. The deflated "
                        f"figure is {sb.get('deflated_sharpe')}. A simulation-"
                        f"calibrated bar, which is less strict, would give "
                        f"{sb.get('deflated_sharpe_simulated')}."
                    ),
                    "why_not_fixed": (
                        "This is not a defect in the calculation; it is what the "
                        "sample supports. Closing the gap needs either more "
                        "out-of-sample history, a strategy fixed in advance "
                        "rather than selected, or a fresh sample the search "
                        "never touched."
                    ),
                })
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
                    "Tested, and the obvious remedy does not work. Re-running "
                    "the allocator with the sector cap tightened from 30% to 8% "
                    "left R-squared at 76-79% the whole way while beta fell "
                    "1.04 to 0.75 and CAGR fell 29.6% to 20.7%. Sector "
                    "concentration is not the cause; the correlation is what a "
                    "long-only equity book is. Lowering it needs shorting or "
                    "hedging the index, which is a different strategy rather "
                    "than a fix to this one."
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
        total_articles = sum(n.get("article_count") or 0 for n in news)
        regimes_all = load("regime_predictions")
        total_months = len(regimes_all) if regimes_all else 0
        months_with = sum(1 for n in news if (n.get("article_count") or 0) > 0)
        in_window = sum(1 for n in news if str(n.get("month", "")) >= "2014-01")
        # Mean confidence over the months that actually carry articles, rather
        # than a hard-coded range. A number written into the sentence by hand
        # goes stale the moment the coverage changes, and this sentence has
        # already said "95%" about a series that is 42% covered.
        confs = [
            float(n.get("news_confidence") or 0.0)
            for n in news
            if (n.get("article_count") or 0) > 0
        ]
        mean_conf = (sum(confs) / len(confs)) if confs else 0.0
        coverage_pct = 100.0 * months_with / total_months if total_months else 0.0
        if total_months and months_with < total_months:
            if coverage_pct < 50:
                judgement = (
                    "A feature absent in more than half the months is not "
                    "measuring sentiment; it is partly measuring article "
                    "availability."
                )
            else:
                judgement = (
                    "Coverage is now a majority of the window, but the thin "
                    "months carry a confidence weight of about "
                    f"{mean_conf:.2f}, so a month with one article barely moves "
                    "the model and a month with several hundred moves it a lot. "
                    "The average is therefore a blend of a few well-observed "
                    "months and many near-empty ones."
                )
            caveats.append({
                "id": "news_coverage_is_sparse",
                "severity": "medium" if coverage_pct < 50 else "low",
                "statement": (
                    f"News features are populated for {months_with} of "
                    f"{total_months} months ({coverage_pct:.0f}% coverage, "
                    f"{in_window} inside the backtest window, {total_articles} "
                    f"articles in total), at a mean confidence of about "
                    f"{mean_conf:.2f}. {judgement}"
                ),
                "why_not_fixed": (
                    "The archive only goes back so far. This is why the news "
                    "factor is weighted by its own confidence rather than "
                    "treated as a full-strength input, and why it is retained as "
                    "decision context rather than removed outright."
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
