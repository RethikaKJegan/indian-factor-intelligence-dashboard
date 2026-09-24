# Indian Factor Intelligence Dashboard

A full-stack local dashboard for Indian equity regime detection, factor scoring, dynamic factor allocation, portfolio rebalance signals, backtesting, RSS news evidence, and LangGraph-style pipeline orchestration.

The project is built around the Nifty 200 universe and uses Indian market/factor/news data. It is intended for research, simulation, and decision-support workflows, not direct investment advice.

## Features

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
- local SQLite databases in `data_input/`
- `output_csv/`
- local runtime logs/reports

## Setup

Install frontend dependencies:

```powershell
npm install
```

Create your local environment file:

```powershell
copy .env.example .env
```

Then edit `.env` and add your Groq API key if you want optional LLM explanations:

```env
GROQ_API_KEY=your_key_here
```

The dashboard can run from the committed JSON files immediately.

```powershell
npm run dev:5174
```

Open:

```text
http://127.0.0.1:5174/
```

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

## SQLite Data

The main local database is expected at:

```text
data_input/processed_financial_data.sqlite
```

This database is intentionally not committed because it is large and local.

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

## Notes

- The EOD refresh script does not create mock data. If NSE data is unavailable, it records a failure or no-data status.
- Index data may be unavailable from the NiftyIndices API on some runs; the script records this rather than inventing index rows.
- RSS feeds are optional supporting evidence. The pipeline uses working Economic Times and Google News RSS feeds.
- This is a research dashboard, not investment advice or an automated trading system.
