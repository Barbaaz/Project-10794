"""The scraper log: one file per day, shared by every process, old ones removed (no network, no database)."""
import logging
import os
import time
from datetime import date

import scheduler.jobs as jobs


def test_a_line_goes_to_the_file_of_its_day(tmp_path, monkeypatch):
    handler = jobs.DailyFileHandler(tmp_path)
    handler.setFormatter(logging.Formatter("%(message)s"))
    record = lambda text: logging.LogRecord("x", logging.INFO, "", 0, text, None, None)
    handler.emit(record("first"))

    class Tomorrow(date):
        @classmethod
        def today(cls):
            return date(2099, 1, 2)
    monkeypatch.setattr(jobs, "date", Tomorrow)
    handler.emit(record("after midnight"))
    handler.close()

    assert (tmp_path / f"scraper-{date.today().isoformat()}.log").read_text(encoding="utf-8") == "first\n"
    assert (tmp_path / "scraper-2099-01-02.log").read_text(encoding="utf-8") == "after midnight\n"


def test_two_processes_append_to_the_same_file(tmp_path):
    one, two = jobs.DailyFileHandler(tmp_path), jobs.DailyFileHandler(tmp_path)
    for handler, text in ((one, "a"), (two, "b"), (one, "c")):
        handler.emit(logging.LogRecord("x", logging.INFO, "", 0, text, None, None))
    one.close(), two.close()
    assert (tmp_path / f"scraper-{date.today().isoformat()}.log").read_text(encoding="utf-8").split() == ["a", "b", "c"]


def test_old_files_are_removed(tmp_path):
    old, new, rotated = tmp_path / "scraper-2026-08-01.log", tmp_path / "scraper-2026-10-09.log", tmp_path / "scraper.log.2026-08-01"
    for path in (old, new, rotated):
        path.write_text("x")
    month_ago = time.time() - 40 * 86400
    os.utime(old, (month_ago, month_ago))
    os.utime(rotated, (month_ago, month_ago))
    jobs.remove_old_logs(tmp_path)
    assert [p.name for p in tmp_path.iterdir()] == [new.name]
