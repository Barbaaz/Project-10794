# Registers the Windows scheduled tasks that scrape the stores. Safe to re-run (replaces them).
# Usage, from the project folder:
#
#   powershell -ExecutionPolicy Bypass -File scheduler\register_daily_task.ps1
#   powershell -ExecutionPolicy Bypass -File scheduler\register_daily_task.ps1 -Time 03:30 -EveningTime 17:00
#
# Two tasks:
#   Project10794-Scrapers          every store, then IGDB (morning)
#   Project10794-Scrapers-Evening  Press Start, Mega Mania, Gaming Replay again, listing pages only
#                                  (python -m scheduler.run_all_scrapers --light); -EveningTime "" to skip
#
# Remove them with:  Unregister-ScheduledTask -TaskName Project10794-Scrapers* -Confirm:$false
# Run one now with:  Start-ScheduledTask -TaskName Project10794-Scrapers
# Logs:              logs\scraper.log   and the scrape_runs table

param(
    [string]$Time = "06:00",
    [string]$EveningTime = "18:00",
    [string]$TaskName = "Project10794-Scrapers"
)

$ErrorActionPreference = "Stop"

$projectDir = Split-Path -Parent $PSScriptRoot

# pythonw.exe runs without opening a console window
$python = (Get-Command python).Source
$pythonw = Join-Path (Split-Path -Parent $python) "pythonw.exe"
if (-not (Test-Path $pythonw)) { $pythonw = $python }

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
function Register-ScraperTask($name, $at, $arguments, $description) {
    $action = New-ScheduledTaskAction -Execute $pythonw -Argument $arguments -WorkingDirectory $projectDir
    $trigger = New-ScheduledTaskTrigger -Daily -At $at
    Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings `
        -Description $description -Force | Out-Null
    Write-Host "Task '$name' registered: daily at $at"
    Write-Host "  $pythonw $arguments"
}

Register-ScraperTask $TaskName $Time "-m scheduler.run_all_scrapers" `
    "Scrapes store prices and stock into the Project10794 database (every store), then IGDB."

$evening = "$TaskName-Evening"
if ($EveningTime) {
    Register-ScraperTask $evening $EveningTime "-m scheduler.run_all_scrapers --light" `
        "Refreshes prices and stock of Press Start, Mega Mania and Gaming Replay (listing pages only)."
} elseif (Get-ScheduledTask -TaskName $evening -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $evening -Confirm:$false
    Write-Host "Task '$evening' removed"
}
Write-Host "  in $projectDir"
