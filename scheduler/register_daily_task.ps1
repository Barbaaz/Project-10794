# Registers a Windows scheduled task that scrapes every store once per day.
# Safe to re-run (replaces the existing task). Usage, from the project folder:
#
#   powershell -ExecutionPolicy Bypass -File scheduler\register_daily_task.ps1
#   powershell -ExecutionPolicy Bypass -File scheduler\register_daily_task.ps1 -Time 03:30
#
# Remove it with:  Unregister-ScheduledTask -TaskName Project10794-Scrapers -Confirm:$false
# Run it now with: Start-ScheduledTask -TaskName Project10794-Scrapers
# Logs:            logs\scraper.log   and the scrape_runs table

param(
    [string]$Time = "06:00",
    [string]$TaskName = "Project10794-Scrapers"
)

$ErrorActionPreference = "Stop"

$projectDir = Split-Path -Parent $PSScriptRoot

# pythonw.exe runs without opening a console window
$python = (Get-Command python).Source
$pythonw = Join-Path (Split-Path -Parent $python) "pythonw.exe"
if (-not (Test-Path $pythonw)) { $pythonw = $python }

$action = New-ScheduledTaskAction -Execute $pythonw -Argument "-m scheduler.run_all_scrapers" -WorkingDirectory $projectDir
$trigger = New-ScheduledTaskTrigger -Daily -At $Time

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -MultipleInstances IgnoreNew

# Runs as the current user (needed for the database's Windows authentication),
# while that user is logged on. -StartWhenAvailable catches up on a missed run
# as soon as the computer is on again.
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "Scrapes store prices and stock into the Project10794 database once per day." -Force | Out-Null

Write-Host "Task '$TaskName' registered: daily at $Time"
Write-Host "  $pythonw -m scheduler.run_all_scrapers"
Write-Host "  in $projectDir"
