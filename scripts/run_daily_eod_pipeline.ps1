$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$LocalPython = Join-Path $ProjectDir ".venv\Scripts\python.exe"
$BundledPython = "C:\Users\Admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$Python = if (Test-Path $LocalPython) { $LocalPython } elseif (Test-Path $BundledPython) { $BundledPython } else { "python" }
$Today = Get-Date -Format "yyyy-MM-dd"

Set-Location $ProjectDir

Write-Host "[$(Get-Date -Format o)] Starting daily EOD refresh for $Today"
& $Python scripts\daily_eod_refresh.py --date $Today --allow-no-data

Write-Host "[$(Get-Date -Format o)] Running dashboard pipeline after EOD refresh"
& $Python scripts\run_pipeline.py

Write-Host "[$(Get-Date -Format o)] Daily EOD pipeline complete"
