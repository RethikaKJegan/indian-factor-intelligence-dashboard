$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Python = "C:\Users\JKRFamily\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
Set-Location $ProjectDir
& powershell -ExecutionPolicy Bypass -File scripts\run_daily_eod_pipeline.ps1 *> daily_update.log
