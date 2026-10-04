"""
The daily runs on a server (docker-compose.production.yml), in place of the Windows tasks:
the morning run at 06:00 and the evening run at 18:00, Lisbon time.

    python -m scheduler.daemon

Each run is a separate process (python -m scheduler.run_all_scrapers), so a crash or a stuck
import in one run doesn't take the schedule down. A run missed while the server was off is not
made up: the next one comes at its time (the 8 h gap per store applies as on the PC).
"""
import logging
import subprocess
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from scheduler.jobs import setup_logging

log = logging.getLogger(__name__)

TIMEZONE = ZoneInfo("Europe/Lisbon")

# (hour, minute, arguments for run_all_scrapers), as the PC's two Windows tasks
RUNS = [
    (6, 0, []),
    (18, 0, ["--light"]),
]


def next_run(now):
    """The next scheduled (time, arguments) after `now` (an aware datetime in TIMEZONE)."""
    candidates = []
    for hour, minute, args in RUNS:
        at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if at <= now:
            # Tomorrow at the same wall-clock time (the date moves, not 24 h: summer time changes)
            at = (at + timedelta(days=1)).replace(hour=hour, minute=minute)
        candidates.append((at, args))
    return min(candidates, key=lambda c: c[0])


def main():
    setup_logging()
    while True:
        at, args = next_run(datetime.now(TIMEZONE))
        log.info("Next run: %s %s", at.strftime("%Y-%m-%d %H:%M %Z"), " ".join(args) or "(morning)")
        # Sleep in steps, so a clock change or a suspended server doesn't push the run hours late
        while (left := (at - datetime.now(TIMEZONE)).total_seconds()) > 0:
            time.sleep(min(left, 600))
        result = subprocess.run([sys.executable, "-m", "scheduler.run_all_scrapers", *args])
        log.info("Run finished (exit code %d)", result.returncode)


if __name__ == "__main__":
    main()
