# Registers the Windows scheduled task that scrapes the stores. Safe to re-run (replaces it).
# Usage, from the project folder:
#
#   powershell -ExecutionPolicy Bypass -File scheduler\register_daily_task.ps1
#   powershell -ExecutionPolicy Bypass -File scheduler\register_daily_task.ps1 -EveryHours 3
#
# The PC isn't on at fixed hours (user, 2026-10-08), so there are no fixed times: the task starts
# 10 minutes after logon and again every -EveryHours while the user is logged on, and runs
# python -m scheduler.run_all_scrapers --due, which decides what is due:
#   the full run (every store, then IGDB) if none started in the last 20 hours, else the light run
#   (Press Start, Mega Mania, Gaming Replay, listing pages only). A store ran less than 8 h ago, or
#   one that answered 403 / 429 in the last 24 h, is skipped without a request; one copy runs at a time.
#
# Remove it with:  Unregister-ScheduledTask -TaskName Project10794-Scrapers -Confirm:$false
# Run it now with: Start-ScheduledTask -TaskName Project10794-Scrapers
# Logs:            logs\scraper-<date>.log (one per day)   and the scrape_runs table

param(
    [int]$EveryHours = 2,
    [string]$TaskName = "Project10794-Scrapers"
)

$ErrorActionPreference = "Stop"

$projectDir = Split-Path -Parent $PSScriptRoot

# pythonw.exe runs without opening a console window
$python = (Get-Command python).Source
$pythonw = Join-Path (Split-Path -Parent $python) "pythonw.exe"
if (-not (Test-Path $pythonw)) { $pythonw = $python }

$settings = New-ScheduledTaskSettingsSet `
    -RunOnlyIfNetworkAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -MultipleInstances IgnoreNew

# At logon (after 10 minutes, so the network and PostgreSQL are up), then every $EveryHours hours
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$trigger.Delay = "PT10M"
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Hours $EveryHours)).Repetition

$arguments = "-m scheduler.run_all_scrapers --due"
$action = New-ScheduledTaskAction -Execute $pythonw -Argument $arguments -WorkingDirectory $projectDir
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "Scrapes store prices and stock into the Project10794 database when due (full run about once a day)." `
    -Force | Out-Null

# The old evening task (fixed 18:00), if still there
if (Get-ScheduledTask -TaskName "$TaskName-Evening" -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName "$TaskName-Evening" -Confirm:$false
    Write-Host "Task '$TaskName-Evening' removed"
}

Write-Host "Task '$TaskName' registered: at logon (+10 min), then every $EveryHours h while logged on"
Write-Host "  $pythonw $arguments"
Write-Host "  in $projectDir"
