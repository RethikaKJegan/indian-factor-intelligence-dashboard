# Indian Factor Intelligence Dashboard

A full-stack local dashboard for Indian equity regime detection, factor scoring, dynamic factor allocation, portfolio rebalance signals, backtesting, RSS news evidence, and LangGraph-style pipeline orchestration.

The project is built around the Nifty 200 universe and uses Indian market/factor/news data. It is intended for research, simulation, and decision-support workflows, not direct investment advice.

## Features

- User-facing monthly trading assistant flow:
  - Command Center
  - Trade Plan
  - Final Portfolio
  - Stock Inspector
  - Performance & Trust
  - Advanced Research
- Nifty 200 regime dashboard with 5 regime labels
- Momentum, Value, Quality, and Low Volatility factor scoring
- Dynamic event-driven decision gate:
  - `RETAIN`
  - `REBALANCE`
  - `DEFENSIVE`
- Portfolio trade actions:
  - `BUY`
  - `ADD`
  - `REDUCE`
  - `SELL`
- Stock signal charts with date zoom, action filters, and signal history
- Backtest comparison:
  - Dynamic regime/factor allocation
  - Static 25/25/25/25 allocation
  - Nifty 200 benchmark
- RSS financial news ingestion and news stress features
- Daily NSE EOD refresh script for latest Nifty 200 EOD prices
- LangGraph orchestration report page
- Historical simulation/replay page

## Tech Stack

- React
- TypeScript
- Vite
- Tailwind CSS
- Python
- SQLite
- LangGraph
- RSS feeds and NSE EOD data sources

## Repository Contents

Committed:

- React dashboard source in `src/`
- Generated demo JSON data in `public/data/`
- Python pipeline scripts in `scripts/`
- Package files and frontend config
- `.env.example`

Not committed:

- `.env`
- `node_modules/`
- `dist/`
- extra local SQLite databases in `data_input/`
- `output_csv/`
- local runtime logs/reports

## Setup

Install frontend dependencies:

```powershell
npm install
```

Install Python dependencies (needed to run the pipeline; the dashboard alone
does not need them, but `npm run eod` and `npm run dev:eod` do):

```powershell
python -m pip install -r requirements.txt
```

Create your local environment file:

```powershell
copy .env.example .env
```

Then edit `.env` and add your LLM key if you want optional LLM explanations:

```env
GEMINI_API_KEY=your_key_here
LLM_PROVIDER=gemini
```

The dashboard can run from the committed JSON files immediately.

```powershell
npm run dev:5174
```

Open:

```text
http://127.0.0.1:5174/
```

## Index Coverage

The index has 200 constituents, but the modeling universe is only what the
upstream data can actually support. Every pipeline run measures per-symbol
data depth and writes the result to `public/data/universe_coverage.json`,
which the Model Report page displays.

A symbol is dropped when the source data cannot support the four factors:

- **no NSE fundamentals history** — NSE's corporate financial-results API
  returns no rows for the ticker, so Value and Quality cannot be scored.
- **insufficient price history** — fewer than 13 monthly closes, so 12-month
  momentum and the volatility factors have nothing to measure.

Currently 189 of 200 symbols are usable and 11 are excluded. Nothing is
imputed to fill the gap: the pipeline drops the symbol rather than inventing
values, so every figure shown is measured.

The exclusion is **data-driven, not hardcoded**. `scripts/universe.py` derives
the set from the database on each run, so if NSE later publishes the missing
filings — or a symbol accumulates enough price history — it is picked up
automatically on the next run with no code change. The pipeline prints which
symbols were excluded and why.

## Implementation Status

Tracked against the rectification spec. "Blocked" means the fix requires data
this repository does not hold.

| Item | Status | Note |
|---|---|---|
| §14 Position cap after normalisation | **Done** | See "Position cap" below |
| §13 Stock-level backtest | **Done** | Authoritative result, net of traded turnover |
| §21 Transaction costs | **Done** | 20bps base + 0/10/20/50/100bps ladder |
| §22 Risk metrics | **Done** | CVaR, alpha, beta, TE, IR, ulcer, skew |
| §23 Statistical inference | **Done** | Newey-West t-stat, block-bootstrap CIs |
| §24 Experiment manifest | **Done** | `experiment_manifest.py`, run fingerprint |
| §28 Model Integrity page | **Done** | 12 caveats read from run artifacts |
| Data freshness gate | **Done** | `verify_data.py`, schedule trigger added |
| §15 Portfolio constraints | **Done (core)** | max weight, sector cap, name count |
| §2 Walk-forward GMM | **Done** | Spherical, aligned, 60-month warm-up |
| §1 Look-ahead in optimizer | **Done** | Trailing decayed window |
| §5 Feature dictionary | **Done** | `regime_model.DATA_ARTIFACT_COLUMNS` + allowlist |
| §9 Sector-neutral factor scores | **Done** | `factor_engine.py` |
| §10 Winsorization | **Done** | 2.5/97.5 inputs, ±3σ composite |
| §11 Missing-data coverage | **Done** | 75% metric-weight rule |
| §6 Point-in-time fundamentals | **Verified** | `available_date` already lagged |
| §4 Regime posterior naming | **Done** | Renamed; ANOVA shown on the page |
| §3 Regime validation | **Done** | F=0.745, labels declared descriptive |
| §7 Survivorship bias | **Blocked** | No membership history exists |
| §8 Richer factor metrics | **Blocked** | ROE/ROCE/PB/EV-EBITDA are 0% populated |
| §17 ML forecasting | **Blocked (premature)** | 92 forward periods; see below |
| §19 NLP pipeline | **Blocked** | 7 months of articles |
| §25 PostgreSQL/FastAPI | **Deferred** | Contradicts "do not redesign" |

### Position cap (§14)

The old code capped each weight at 5% and then renormalised, which scales
capped names back above the cap. Measured on the shipped output: **114 of 150
months breached the limit and the largest position reached 10.0%**.

`scripts/portfolio_construction.py` now applies every limit to the final
weights via bounded water-filling, and `validate()` raises if any constraint is
violated. Verified on the current output: **0 of 150 months breach 5%**, and
the 30% sector cap holds in all 150. Compliance is written to
`public/data/portfolio_constraint_compliance.json`.

Two related defects surfaced while fixing this:

- `TOP_K = 10` gave 10 names per sleeve. A 5% cap on 10 names can only place
  50% of capital, so the book could never be fully invested. Raised to 30.
- Factor scores are z-scores, so about half are negative. Multiplying them
  straight into the sleeve weight produced negative positions, which the
  allocator correctly refused. Each sleeve is now shifted within its own
  selection.

### Factor construction (§9, §10, §11)

`factor_scores_monthly` is a pre-built table produced upstream, and it had three
defects that `scripts/factor_engine.py` now corrects for Value and Quality:

**Outliers were unbounded.** `monthly_pe` runs from 3.56 to 1893.61 in a single
month. A 1893x multiple z-scores far into the tail and can single-handedly
decide whether a stock is a Value pick. Inputs are now winsorized at 2.5/97.5,
and the composite score is clipped to ±3σ — bounding the inputs alone is not
enough, because a composite of several extreme z-scores still reached |8|.

**Scoring ignored how many metrics existed.** 21 stocks in the latest month
have no populated fundamentals and were scored anyway; `debt_equity` is
populated for only 83 of 168, so Quality was often computed from one surviving
metric. A score is now withheld unless at least 75% of the composite metric
weight is present. Current output: 5,795 Value and 5,518 Quality stock-months
withheld, written to `factor_coverage_withheld.json`.

**Scoring was global, not sector-relative.** Financial Services carries mean
`profit_margin` of 0.44 against 0.15 for Information Technology, and mean
`debt_equity` of 0.03 against 0.01 elsewhere, so a global ranking is partly a
bet on sector membership. Metrics are now demeaned within sector (sectors with
fewer than 4 members keep their raw value) before scaling.

The size of that last correction, measured on the latest month:

| Factor | Top-10 overlap, global vs sector-neutral |
|---|---|
| Value | 9 / 10 |
| **Quality** | **2 / 10** |

Quality was previously almost entirely a sector bet. Leverage metrics are also
excluded for Financial Services, where a bank's balance sheet is not comparable
to an industrial's.

Momentum and Low Volatility remain price-based and are read from the stored
table; the price layer already skips the current month, so there is no
leakage to correct there.

### The equal-weight baseline, and what it says about the factors

`Universe Equal-Weight` is now a reported strategy: every stock in the
189-name universe, equal weight, rebalanced monthly, with no factor logic at
all. It is in `backtest_summary`, on the equity-curve chart, and in the
strategy table.

It is there because the Nifty 200 price index is a weak yardstick for a factor
book tilted toward smaller names. The index is cap-weighted and price-only; the
investable universe equal-weighted is neither. Measured over the same 152
months:

| Strategy | CAGR | vs equal-weight baseline |
|---|---|---|
| **Universe Equal-Weight** (no factors) | **25.04%** | — |
| Dynamic Regime Factor Allocation | 20.22% | **−4.82pp p.a.** |
| Static 25/25/25/25 | 20.69% | **−4.35pp p.a.** |
| **Stock-Level Constrained Portfolio** (20bps) | **26.58%** | **+1.54pp p.a.** |

**The factor sleeves do not beat holding the universe equally.** Read against
Nifty 200 the same strategies appear to gain roughly 8pp a year; that figure is
borrowed from the equal-weight effect, not earned by the factors. The
stock-level construction — real holdings, 5% cap, sector cap, net of traded
turnover — is the only book that clears the baseline, by about 1.5pp a year
against a 95% interval of roughly 13% to 40%.

All four numbers are published together. The factor layer's shortfall is
reported, not omitted, and neither is the baseline that exposes it.

### Forward outlook, and scoring the model's own forecasts

`forward_outlook.json` carries two things.

**The T+1 forecast.** The next rebalance month's expected return, volatility
and turnover, plus the regime probability vector. It is not a second model: the
expected factor returns are the optimiser's own decayed trailing inputs,
persisted as `er_*` on every allocation row specifically so the panel cannot
drift from the weights it explains.

**The accuracy record.** Every past forecast, scored against what actually
happened, out of sample only:

| Measure | Value |
|---|---|
| Directional hit rate | **65.85%** over 366 sleeve-months (93 months) |
| Information coefficient | **+0.081** (n=372) |
| Mean absolute error | 4.38% mean across sleeves |

The information coefficient is small and that is reported rather than
smoothed over: a monthly factor forecast is worth far less than a daily stock
signal, and claiming otherwise would be the error this project spent most of
its effort removing elsewhere. The per-month table on the Overview page shows
the misses too — 2026-03 scored 0 of 4 sleeves right.

Any measure with too few observations is published as `null` alongside the
count that blocked it, rather than as a number computed from four months that
would look like evidence.


### Stock-level backtest (§13)

The previous backtest compounded factor returns:

```
portfolio_value *= 1 + sum(factor_weight * factor_return)
```

That is not a portfolio — no holdings, no position sizes, no overlap between
sleeves, and no cost of implementing it. `scripts/stock_backtest.py` now
computes the return of the actual target book from real stock returns, net of
one-way turnover, and reports it as its own strategy.

```
Stock-Level Constrained Portfolio   CAGR 27.91%  Sharpe 1.41  maxDD -28.33%
  avg holdings 53.4   avg monthly turnover 27.5%   total cost 8.20%   hit rate 69.1%
```

The factor-level series is retained alongside it so the difference between the
two views is visible rather than hidden. Writes
`backtest_stock_level.json` and `backtest_stock_level_summary.json`.

Note the comparison: the same factor weights produce ~20% compounded at factor
level and 27.91% on actual holdings. Neither number is "the" answer on its own,
which is why both are now reported.

### Cost sensitivity and statistical reliability (§21, §22, §23)

`scripts/performance_stats.py` adds the three things a return path needs before
its headline numbers should be quoted. All of it is surfaced on the Backtest
page under **Statistical Reliability**.

**Cost ladder.** A single cost assumption is a claim; a ladder is a sensitivity
analysis. The book is re-run end to end at 0/10/20/50/100 bps, because turnover
depends on the weights, not just on the base case:

| Cost | CAGR | Sharpe | Max DD | Cumulative cost |
|---|---|---|---|---|
| 0 bps | 28.74% | 1.44 | −27.19% | 0.00% |
| 20 bps (base) | 27.91% | 1.41 | −28.33% | 8.20% |
| 100 bps | 24.64% | 1.27 | −32.74% | 41.02% |

The result is not an artefact of a favourable cost assumption. At roughly 27%
monthly turnover, each 10 bps is worth about 0.27% of annual return.

**Sharpe depends on a rate the data does not contain.** There is no
Treasury-bill or G-Sec series anywhere in the database, so the dashboard's
"Sharpe 1.41" was silently excess-return-over-zero. Against a disclosed 6.5%
Indian risk-free assumption it is **1.07**. Both are now reported side by side,
because comparing an excess-of-cash number with an excess-of-nothing one is the
most common way a Sharpe ratio gets overstated. The Sortino reported on the
dashboard was also wrong: it divided by the count of *losing* months rather than
all periods, understating it as 1.46 where the standard definition gives 2.62.

**The interval around the headline.** Point estimates from 149 monthly returns
invite over-reading. Both headline numbers now carry a 95% confidence interval
from a **moving-block** bootstrap (block length 5, 2,000 resamples, fixed seed),
which preserves the serial dependence that month-by-month resampling would
destroy:

| Statistic | Point | 95% interval |
|---|---|---|
| CAGR | 27.91% | **13.48% – 42.64%** |
| Sharpe (vs 6.5%) | 1.07 | **0.44 – 1.80** |

The Sharpe lower bound stays positive, which is the strongest claim this
backtest supports. The CAGR interval is ~30 points wide, which is the honest
answer to "how precisely do 149 months pin down a growth rate": not precisely.

**Is the average month distinguishable from zero?** A Newey-West HAC t-statistic
on the mean monthly return gives **t = 4.46** (4 lags, lag-1 autocorrelation
+0.10), above the 1.96 threshold. Losses do cluster mildly, so the correction
widens the interval rather than flattering it.

**Against the index.** Beta **1.02**, Jensen's alpha **14.46%**, information
ratio **1.58**, tracking error **8.66%**, and the book beat the index in 64% of
months. R² is **78%**, which is the number that keeps this honest: the book's
*average* move matches the index, but 78% of its monthly variance is still the
index's. The alpha is real; the diversification benefit is not.

**The tail a mean and a Sharpe both hide.** Monthly CVaR at 95% is **−10.4%**
(one month in twenty lost about a tenth of the book; the worst single month was
−21.7%), the longest stretch below a prior peak is **25 months**, skew is
**−0.39** and excess kurtosis **1.83**. Depth of drawdown and CVaR answer
different questions: drawdown is the worst path, CVaR is the typical bad month.

Writes `backtest_performance_report.json` and `backtest_cost_scenarios.json`.

### Data freshness, and how to verify it

A daily job that quietly stops working is worse than one that crashes: the
dashboard keeps rendering and the numbers simply stop moving. `scripts/verify_data.py`
answers "is the data current?" and is safe to run any time (read-only):

```
$ python scripts/verify_data.py
Data freshness
  today              2026-09-29
  expected EOD date  2026-09-29
  latest close       2026-09-25 (567 daily rows, 2 trading days behind)
  newest month label 2026-09-30
  last refresh       ok at 2026-09-25T18:12:51 (counts: {'ok': 10})
  VERDICT            DEGRADED
  [~] EOD data stops at 2026-09-25, 2 trading days behind 2026-09-29...
```

Exit codes: `0` current, `1` degraded, `2` stale, `3` the check could not run.
`--json` for machine output, `--strict` to fail on medium severity.

It separates three things that fail differently, and which were all invisible
in the rendered numbers:

| Finding | Meaning |
|---|---|
| EOD behind N trading days | The scheduled refresh is missing or failing runs |
| Month label ahead of data | Tables say `2026-09-30`; the newest close is `2026-09-25` |
| Refresh reported failure | Attempts exited 0 while finding nothing (see below) |

**On the month label.** Months are keyed by calendar month-end, so an
in-progress month always carries a future date. That is a convention, not a
claim that trading reached it — but nothing in the table said so, which is why
the dashboard header (a real close date) appeared to contradict the tables.
Both are now reported side by side and the discrepancy is stated explicitly.

#### The scheduled job was not scheduled

`.github/workflows/daily-eod-refresh.yml` had **no `schedule:` trigger** — only
`workflow_dispatch` and `repository_dispatch`. It could not have run on its own
at 6pm, or at all, unless something external was firing `repository_dispatch`.
The last successful refresh was 2026-09-25, two trading days before this check.

Added:

```yaml
schedule:
  - cron: "30 12 * * 1-5"   # 18:00 IST, weekdays
```

18:00 IST rather than 15:45 because NSE bhavcopy files appear after the 15:30
close and a run before they are published finds yesterday's file, reporting a
spurious one-day lag every day.

#### `--allow-no-data` made failure invisible

The workflow ran `daily_eod_refresh.py --allow-no-data`, which writes a
`no_data` status and **exits 0**. The job then ran the pipeline on stale data
and committed it, and a green Actions tick meant nothing. Added a real gate:

```yaml
- name: Verify the data actually advanced
  run: |
    python scripts/verify_data.py --strict
    # stale (exit 2) fails the job; degraded (1) warns
```

Publishing a stale dashboard is worse than a red X, because nobody checks a
green tick. The run summary also now carries the refresh status table, so a
failing refresh is visible without opening logs.

The pipeline prints the same freshness report **before doing any work**, and
records it in the manifest, so a stale run is labelled as stale in the output
itself.

#### News: fresh by default, reproducible on demand

The earlier snapshot approach made runs reproducible by default, which meant a
daily dashboard showing stale sentiment. That was the wrong trade for a
scheduled job, so it is inverted:

| Mode | Behaviour |
|---|---|
| default | Fetch live. Always snapshot the article set and hash it into the fingerprint |
| `NEWS_REPLAY=1` | Replay the snapshot — reproduces the last run exactly |

Verified: a live run and a replay of its own snapshot produce the **same
fingerprint** and **29 of 30 byte-identical artifacts**. The only differences
are the timestamps and the manifest's honest self-description of which mode ran.
So a run is neither silently reproducible nor silently unreproducible — it
carries the evidence.

This surfaced two more bugs. The news agent was being called **twice** per
pipeline (Node 0 and Node 10), so the second fetch overwrote the snapshot with
an article set the regime model had never consumed — the snapshot did not
record what the run actually used. And `NEWS_MODE` was assigned inside the
function without `global`, so the manifest always reported `fetched-live` even
during a replay.

#### Two more bugs found

**`global` scope.** `NEWS_MODE = "replayed"` inside `rss_news_agent` created a
local, leaving the module global at its initial value. The manifest reported
the wrong mode for every run.

**The determinism report inferred the mode from a file.** It decided a run had
replayed the news snapshot because the snapshot existed — but a live run also
writes one, so every live fetch claimed to have been replayed. The mode is now
reported by the agent that knows it, never inferred.

### Reproducibility and model integrity (§24, §28)

`scripts/experiment_manifest.py` writes `experiment_manifest.json` on every run,
and the **Model Integrity** page renders it. The manifest records four things:

**A run fingerprint** hashing the source database path and per-table row counts,
the SHA-256 of all 11 pipeline modules, and every assumption, together. Two runs
with the same fingerprint produced the same outputs; a different fingerprint
means an input, a module or an assumption moved and the results are not
comparable without saying so.

**The data actually consumed** — row counts and month windows for all 12 tables
read. Row counts rather than a file hash, because hashing a multi-gigabyte
SQLite file would make the fingerprint depend on physical layout, so any
unrelated write would change it.

**Every assumption that would change a result if wrong**, read from the live
modules rather than restated, so the manifest cannot drift from the code. 13
are recorded: `TOP_K`, `TX_COST`, `COST_BPS`, the regime warm-up, the
winsorization tail, the coverage threshold, the sector minimum, the portfolio
constraints, the risk-free rate, the bootstrap seed and sample count.

**What the run cannot support** — 9 caveats, 3 high severity, each read from the
artifact it qualifies rather than typed by hand:

| Severity | Caveat |
|---|---|
| High | Survivorship bias — today's Nifty 200 list applied to all history |
| High | Risk-free rate is an assumption, not a measurement |
| High | 27.91% CAGR has a 95% interval of 13.48%–42.64% |
| Medium | 11,313 factor scores withheld by the coverage rule |
| Medium | Beta 1.02 but R² 78% — alpha real, diversification not |
| Medium | Monthly CVaR −10.4%, 25 months below a prior peak |
| Medium | 60 of 153 months carry no regime score |
| Medium | News features cover 7 of 153 months (5%) |
| Low | No ML layer fitted, and none should be until more history exists |

#### Three reproducibility bugs this found

Verifying the manifest meant running the pipeline twice and byte-comparing the
output. Three real defects surfaced, none of which was visible in any displayed
number.

**1. Set iteration order leaked into the return series.** `backtest_stock_level.json`
differed between runs — in 24 of 149 rows, turnover moved by 1e-6:

```python
turnover = sum(abs(weights.get(n, 0) - previous_weights.get(n, 0))
               for n in set(weights) | set(previous_weights))
```

Python randomises string hashing per process, so a `set` of tickers iterates in
a different order in every run, and float addition is not associative. Sorting
the names before summing fixed it.

**2. The live RSS feed moved the current month.** `regime_predictions.json`
differed in exactly one month — `news_sentiment` and `risk_event_count` for the
current month, and nothing else. The cause is that the news feed moves
`news_sentiment` → `news_stress_score` → `transition_risk` → the regime row →
the allocation → the rebalance trades. It perturbed 1 month of 153 and changed
no regime label, but small is not the same as reproducible.

A successful fetch is now written to `data_input/news_snapshot.json` and
subsequent runs replay it, so a run reproduces its own inputs. `NEWS_REFRESH=1`
forces a re-fetch, and the article set's SHA-256 is hashed into the manifest
fingerprint — so two runs either provably saw the same articles, or the
manifest says they did not.

**3. A broken guard made fix 2 a no-op.** The replay path checked
`isinstance(snap, list)` while the snapshot is written as an object with an
`articles` key, so every run silently fell through to a live fetch anyway. This
was found only because the byte-comparison was re-run after the fix rather than
assumed to have worked.

**Result: a live run and a replay of its own snapshot now produce the same
fingerprint and 29 of 30 byte-identical artifacts.** The one that differs is the
manifest itself, in its timestamps and in the field recording which news mode
ran — which is the point of a manifest.

A fourth, separate defect surfaced alongside these: the 60 regime warm-up months
carried `model_version: "GMM-5-spherical-walkforward"` although the mixture was
never fitted on them. They now carry `"not-scored-warmup"`, so the output does
not claim a provenance it does not have. The Model Integrity page renders that
as an explicit check rather than a static claim.

### Verifying a run

```bash
# 1. Is the data current?
python scripts/verify_data.py                 # exit 0 current / 1 degraded / 2 stale

# 2. Run the pipeline -- prints the freshness report first, the manifest last
python scripts\run_pipeline.py

# 3. Reproduce the run you just made
NEWS_REPLAY=1 python scripts\run_pipeline.py  # same fingerprint, same 29/30 artifacts
```

If the fingerprints match, the two runs are comparable. If they differ, the
manifest names which input moved: the database, the code, an assumption, or the
news article set.

### What is still blocked

- **§7 Survivorship.** No `effective_from`/`effective_to` or add/remove dates
  exist anywhere in the database, and the Nifty 200 list is a single static
  CSV. Historical universe reconstruction needs paid NSE constituent data.
  Every backtest here uses today's surviving stocks and should be read with
  that caveat.
- **§8 Factor inputs.** `monthly_roe`, `monthly_roce`, `monthly_pb` and
  `ev_ebitda` are present as columns but 0% populated. `debt_equity` is 25.9%
  populated, so the Quality factor often rests on fewer metrics than §11 would
  require. Book-to-price, FCF yield and dividend yield are not collected.
- **§17 ML.** There are ~25,000 cross-sectional stock-months but only **92
  months of forward returns**. That supports a linear model and a rank-IC
  measurement, not LightGBM or CatBoost. Running six model families and
  reporting the winner is the exact selection bias §23 warns about, so this is
  gated behind evidence of signal.

## Model Integrity

Several methods were corrected after an audit of the shipped outputs. Each is
enforced in code rather than left to convention, and each is visible in the UI.

### No lookahead in the optimizer

The weights chosen for month M were previously fitted to month M's own
realised factor return, and the backtest then applied those weights to that
same month. That let the optimizer pick the factor that was about to win, and
it compounded into a 69% CAGR that no real strategy achieves.

Expected returns are now estimated from a decayed trailing window that stops at
M-1. As a check, the top-weighted factor matches that month's best performer
about 25-28% of the time, which is what random selection gives; before the fix
it was 58%.

### Out-of-sample regime confidence

The regime model was a 5-component full-covariance Gaussian mixture — 115 free
parameters — fitted to 153 monthly observations, then asked for
`predict_proba` on the rows it had just memorised. It reported confidence
1.0000 for 143 of 153 months.

It is now a spherical mixture (49 parameters) scored by walk-forward fitting:
each month is predicted by a model fitted only on earlier months. Months before
enough history exists are labelled `Unscored` and carry no confidence, rather
than being given a number the model cannot support.

Data-pipeline columns (`stock_coverage_x`, `sector_count_x`, …) are excluded
from the feature set. They describe how many symbols the pipeline had that
month and correlate +0.98 with the month index, so including them made the
model cluster data-availability eras.

### Corporate-action guard

`stock_prices_monthly.monthly_return` is computed from **raw** closes, so a
split or bonus issue is recorded as a real move. PATANJALI shows −93.9% then
+201.7% around its 1:16 split in early 2020.

Monthly returns beyond ±35% are winsorised before anything downstream sees
them. Nothing is deleted and no split ratio is assumed; the run log reports how
many rows were affected. Reconstructing true split-adjusted history would
require the corporate-action table, which this project does not carry.

### Cluster identity is aligned across refits

Walk-forward refitting re-indexes mixture components arbitrarily: component 1
in the 2019 fit is a different region of feature space from component 1 in the
2026 fit. Measured on this data, the per-index mean 12-month return moved by up
to 3.8 z-score units across refits, which would label months by whichever
component happened to land on that index. Each refit is now matched to the
previous one by maximum assignment overlap, so component *k* denotes the same
regime across the scored window.

### The regime names are not a validated forecast

This is the most important caveat in the project, so it is measured on every
run and shown on the Regime page.

A one-way ANOVA tests whether the five clusters differ in the *next* month's
index return. On the current data:

```text
F = 0.745   (5% critical ≈ 2.5)   -> clusters do NOT separate forward returns
```

So the labels "Bull / Expansion", "Bear / Stress" and so on are a naming
convention applied by ordering clusters on trailing return. They classify what
already happened. They do not, on this sample, reliably predict what happens
next, and no claim of regime forecasting should be made from them.

The regime layer still does useful work — it conditions the covariance estimate
and drives the DEFENSIVE decision gate — but its value is as a state
description, not as a timing signal. The factor-based backtest result stands on
its own and is reported separately.

If the regime model is meant to forecast, it needs a different design: more
history, a feature set with genuine forward predictive power, and validation on
a held-out period. Adding features to a 153-month sample will not fix it.

### No fabricated diagnostics

A regime with fewer than three observations in the expanding window cannot
support a correlation matrix. The code previously substituted an identity
matrix, which displayed as a perfect 1.00 diagonal with zeros and implied zero
factor redundancy — on the most recent month, the one actually on screen.

Those months now report `null` and the UI shows an em dash.

### Rebalancing is decided before the month starts

The optimizer maximises return per unit of risk rather than
`return − 0.75·variance`. At these scales the variance term dominates, which
collapses the objective to the minimum-variance portfolio and returns equal
weights every month regardless of the signal.

### Other notes

- The factor score columns are resolved by name, excluding `*_rank`. A
  substring match previously let `momentum_rank` overwrite `momentum_score`,
  so the "Score" column showed a 1..189 rank.
- Charts treat `null` as a gap, breaking the line rather than interpolating.
- History tables are newest-first.
- The Model Report page lists every symbol excluded from the index and why.

## Daily EOD Workflow

To refresh real NSE EOD data, rerun the LangGraph pipeline, and start the dashboard:

```powershell
npm run dev:eod
```

This runs:

```text
scripts/run_daily_eod_pipeline.ps1
```

That wrapper:

1. Downloads the latest available NSE EOD/bhavcopy data.
2. Filters to Nifty 200 symbols.
3. Updates daily stock tables in SQLite.
4. Refreshes the affected monthly stock/factor/regime rows.
5. Runs the LangGraph pipeline.
6. Updates `public/data/*.json`.
7. Starts Vite on port `5174`.

Refresh only:

```powershell
npm run eod
```

Website only:

```powershell
npm run dev:5174
```

## Product Flow Added

The product now defaults to a simpler end-user workflow:

```text
Command Center
  -> Trade Plan
  -> Final Portfolio
  -> Stock Inspector
  -> Performance & Trust
  -> Advanced Research
```

The Trade Plan page can accept holdings manually or through CSV import. It converts model target weights into exact share quantities:

```text
You have X shares.
The model wants Y shares.
Today you should buy/sell Z shares.
```

Holdings are stored in browser `localStorage` in this slice. Backend account storage can be added later.

The daily execution overlay is currently deterministic:

```text
Normal  -> execute full monthly plan
Caution -> stagger new buys
Danger  -> pause new buys
Extreme -> defensive execution
```

The LLM must only explain these structured outputs. It must not decide trades or quantities.

## Automated Vercel Data Refresh

The deployed Vercel dashboard is a static frontend that reads generated JSON from:

```text
public/data/*.json
```

For automatic EOD updates, the repository includes:

```text
.github/workflows/daily-eod-refresh.yml
```

Daily automation is handled by cron-job.org, which triggers the GitHub Actions workflow through `repository_dispatch` at:

```text
Monday-Friday, 18:30 IST
```

GitHub's native scheduled cron was removed because it can run late and create duplicate delayed EOD runs. The workflow now runs from cron-job.org or from the manual GitHub **Run workflow** button.

```text
daily_eod_refresh.py
        ↓
run_langgraph_pipeline.py
        ↓
commit updated public/data/*.json and SQLite snapshot
        ↓
push to GitHub
        ↓
Vercel auto-redeploys
```

You can also run it manually from GitHub:

```text
Actions → Daily EOD Refresh → Run workflow
```

If you want optional Groq explanations in the automated workflow, add this repository secret:

```text
GROQ_API_KEY
```

External cron setup details:

```text
EXTERNAL_CRON_SETUP.md
```

## SQLite Data

The main local database is expected at:

```text
data_input/processed_financial_data.sqlite
```

The baseline `data_input/processed_financial_data.sqlite` is committed so teammates can rerun the pipeline after cloning. Extra local database copies remain ignored.

The committed dashboard JSON files under `public/data/` let the UI run as a demo snapshot. To regenerate all JSON from your own database, place the SQLite file in `data_input/` and run:

```powershell
npm run eod
```

or:

```powershell
python scripts/run_langgraph_pipeline.py
```

## Important Scripts

```text
scripts/daily_eod_refresh.py
```

Downloads latest real NSE EOD data, updates daily/monthly data tables, and writes `public/data/eod_refresh_status.json`.

```text
scripts/run_langgraph_pipeline.py
```

Runs the model pipeline as a LangGraph `StateGraph` and writes dashboard JSON plus `langgraph_run_report`.

```text
scripts/run_pipeline.py
```

Core quantitative/data pipeline functions for regime detection, factor scoring, allocation, portfolio transitions, backtest, chart signals, and news ingestion.

```text
scripts/run_daily_eod_pipeline.ps1
```

Daily Windows wrapper that runs EOD refresh first and then the LangGraph pipeline.

```text
scripts/universe.py
```

Universe coverage policy. Defines how much data a symbol needs before it can
be modeled, derives the excluded set from the database on every run, and
documents why each known exclusion exists. See "Index Coverage" above.

```text
scripts/forward_outlook.py
```

Builds the T+1 forecast from the optimiser's own inputs and scores every past
forecast against its realised outcome, out of sample. Also the module that
decides when a measure is too small to publish. See "Forward outlook" above.

```text
scripts/news_relevance.py
```

Entity tagging and relevance scoring for fetched articles. Matches each
headline against the 189 symbols and 16 sectors, scores relevance from symbol
matches, sector matches and market vocabulary, and weights the monthly and
daily sentiment aggregates by it.

Sentiment and risk are relevance-weighted means, not plain means. A plain mean
treats a story naming a constituent and a general-interest story as equally
informative, so unrelated headlines diluted the signal while their keyword
hits still inflated `risk_event_count`. `news_confidence` is now coverage-based
— it rises with the share of articles that actually name the universe, so a
month of untagged headlines cannot look high-confidence.

The general-interest Economic Times feed was removed for the same reason. It
was the sole source of every non-market headline that reached the model, and
`news_stress_score` feeds the allocation optimiser, so those items were moving
Indian factor weights. Every remaining feed is market-specific by
construction. In the latest run 30.9% of articles name a constituent and 78
are classified `off_topic`.

```text
scripts/repair_fii_dii.py
```

Populates `macro_monthly.monthly_fii_flow` / `monthly_dii_flow` from the
scraped daily FII/DII file. The columns were empty for all 414 months even
though the source carries `fii_net` and `dii_net`; that was an ingestion gap,
not a missing source.

The source is **not** a full history despite its filename: 158 trading days
covering 2026-01 onward. Eight month-ends are now populated and the earlier
years are left null on purpose. Back-filling a flow series that was never
observed would make the table look complete when it is not. The regime model
drops `fii_dii_trend` below its 10% coverage floor, so no reported figure
depends on these values. The script exits 0 when the scrape directory is
absent, because a colleague cloning the repository has no `Downloads/data`.

```text
scripts/repair_eod_aggregates.py
```

Recomputes `daily_count` and `monthly_volume` for every month from
`stock_prices_daily`. The EOD refresh had been accumulating them, reaching
37-38 reported trading days against 5 stored; see the daily-refresh note
above. A pure function of the daily table, so re-running is safe.

```text
scripts/test_dashboard_contracts.py
```

Twelve guard tests over the published artifacts, each tied to a fault that
reached `public/data/*.json` and survived a pipeline rewrite because nothing
checked for it. Run with `python scripts/test_dashboard_contracts.py` or
`python -m pytest scripts/test_dashboard_contracts.py -q`.

## Notes

- The EOD refresh script does not create mock data. If NSE data is unavailable, it records a failure or no-data status.
- Index data may be unavailable from the NiftyIndices API on some runs; the script records this rather than inventing index rows.
- RSS feeds are optional supporting evidence. The pipeline uses working Economic Times and Google News RSS feeds.
- `market_index.json` publishes `open`/`high`/`low` as null with an `ohlc_note`: `market_index_monthly` stores a month-end close and no intraday range. These are the only deliberately-null columns, and a test asserts the note is present.
- `macro_monthly.json` publishes `fii_net`/`dii_net` with a `flows_note` on every row. Eight of 414 months are populated, from `scripts/repair_fii_dii.py`; the scrape holds 158 trading days of 2026 only. The earlier years are null on purpose, and nothing in the project depends on the values. The note is emitted whenever coverage is incomplete, not only when it is zero, so a partly-populated column is never presented as a whole one.
- This is a research dashboard, not investment advice or an automated trading system.
