# Data Sharing Guide

## What is in GitHub

The repository includes the files needed for teammates to run and work on the project:

- React dashboard source code
- Python ingestion/model pipeline scripts
- LangGraph orchestration script
- Runtime dashboard snapshots in `public/data/*.json`
- Baseline processed database at `data_input/processed_financial_data.sqlite`

With this, a teammate can clone the repo, install dependencies, and run:

```powershell
npm install
npm run dev:5174
```

They can also rerun the daily refresh and pipeline:

```powershell
npm run eod
```

or:

```powershell
npm run dev:eod
```

## What is not in GitHub

The full raw folder from:

```text
C:\Users\JKRFamily\Downloads\data
```

is not committed. It is around 2.25 GB and contains thousands of raw files. Keeping it out of Git avoids slow clones, repository bloat, and GitHub large-file problems.

## If someone needs the raw data

Share the raw data separately using one of these:

- Google Drive / OneDrive / Dropbox zip
- GitHub Release asset
- External storage used only for raw archives

Recommended archive name:

```text
indian-factor-raw-data-2026-09-23.zip
```

After downloading, place/extract it beside the project like:

```text
C:\Users\<name>\Downloads\data
```

The normal dashboard workflow does not require this raw folder. It is only needed if someone wants to re-audit or rebuild the original processed database from raw source files.
