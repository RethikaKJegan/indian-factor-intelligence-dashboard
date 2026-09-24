# Data Input

This folder contains the processed SQLite database used by the local pipeline.

Committed:

- `processed_financial_data.sqlite` - compact processed Indian market/factor/macro/news database used by `npm run eod` and the LangGraph pipeline.

Not committed:

- Raw scraped/downloaded files from `C:\Users\JKRFamily\Downloads\data`
- Temporary databases or local experiment copies

The full raw data folder is intentionally not stored in Git because it is large. The processed SQLite plus `public/data/*.json` is enough for teammates to run the dashboard and regenerate outputs.
