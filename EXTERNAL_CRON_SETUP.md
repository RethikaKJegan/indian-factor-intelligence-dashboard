# External Cron Setup

GitHub scheduled workflows are best-effort and can be delayed or dropped during high load. For reliable daily EOD refresh, use a free external scheduler such as [cron-job.org](https://cron-job.org/) to trigger the GitHub workflow.

The workflow supports three trigger methods:

- Manual GitHub button: `workflow_dispatch`
- GitHub cron backup: `schedule`
- External scheduler webhook: `repository_dispatch`

## 1. Create A GitHub Token

Create a GitHub Personal Access Token that can trigger repository workflows.

Recommended: fine-grained token.

Repository:

```text
RethikaKJegan/indian-factor-intelligence-dashboard
```

Permissions:

```text
Metadata: Read
Contents: Read and write
Actions: Read and write
```

Keep the token private. Do not commit it to GitHub.

## 2. Create A Free cron-job.org Job

Create a free account at:

```text
https://cron-job.org/
```

Create a new cron job.

Basic settings:

```text
Title: Indian Factor EOD Refresh
URL: https://api.github.com/repos/RethikaKJegan/indian-factor-intelligence-dashboard/dispatches
Schedule timezone: Asia/Kolkata
Schedule: Monday-Friday at 18:30
Request method: POST
```

Headers:

```text
Accept: application/vnd.github+json
Authorization: Bearer YOUR_GITHUB_TOKEN
X-GitHub-Api-Version: 2022-11-28
Content-Type: application/json
User-Agent: cron-job.org
```

Request body:

```json
{
  "event_type": "daily-eod-refresh",
  "client_payload": {
    "source": "cron-job.org",
    "market": "india",
    "pipeline": "daily-eod-refresh"
  }
}
```

## 3. Expected Result

At the scheduled time:

```text
cron-job.org
        ↓
GitHub repository_dispatch API
        ↓
Daily EOD Refresh workflow
        ↓
daily_eod_refresh.py
        ↓
run_langgraph_pipeline.py
        ↓
updated public/data/*.json and SQLite snapshot
        ↓
GitHub commit
        ↓
Vercel auto-redeploy
```

In GitHub Actions, the run should show:

```text
event_name=repository_dispatch
repository_dispatch_action=daily-eod-refresh
```

## 4. Testing

In cron-job.org, run the job manually once after saving it.

Then check:

```text
GitHub → Actions → Daily EOD Refresh
```

You should see a new run triggered by `repository_dispatch`.

If the cron job returns HTTP `204`, that is good. GitHub returns `204 No Content` when the dispatch event is accepted.

## 5. Backup

The workflow still keeps GitHub's native scheduled cron as backup. If cron-job.org works reliably, it becomes the main scheduler, and GitHub cron is only a fallback.
