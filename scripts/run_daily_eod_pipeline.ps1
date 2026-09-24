$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Python = "C:\Users\JKRFamily\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$Today = Get-Date -Format "yyyy-MM-dd"

Set-Location $ProjectDir

Write-Host "[$(Get-Date -Format o)] Starting daily EOD refresh for $Today"
& $Python scripts\daily_eod_refresh.py --date $Today

Write-Host "[$(Get-Date -Format o)] Running LangGraph pipeline after EOD refresh"
& $Python scripts\run_langgraph_pipeline.py

Write-Host "[$(Get-Date -Format o)] Daily EOD pipeline complete"
