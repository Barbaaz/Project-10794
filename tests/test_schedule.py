"""The morning run (every store, then IGDB) and the light evening run (no network, no database)."""
import scheduler.run_all_scrapers as run_all


def run(monkeypatch, light):
    calls = {"stores": [], "igdb": 0}
    monkeypatch.setattr(run_all, "setup_logging", lambda: None)
    monkeypatch.setattr(run_all, "active_store_slugs",
                        lambda: ["press_start", "mega-mania", "cstech", "radio_popular", "gaming_replay"])
    monkeypatch.setattr(run_all, "run_store", lambda slug, light=False: calls["stores"].append((slug, light)) or {})
    for name in ("enrich_games", "fill_videos", "fill_tags", "fill_names", "fill_time_to_beat"):
        monkeypatch.setattr(run_all, name, lambda *a, **k: calls.__setitem__("igdb", calls["igdb"] + 1))
    monkeypatch.setattr(run_all, "complete_overdue", lambda: 0)
    monkeypatch.setattr(run_all, "notify", lambda *a: None)
    run_all.main(light=light)
    return calls


def test_morning_run_does_every_store_and_igdb(monkeypatch):
    calls = run(monkeypatch, light=False)
    assert [s for s, _ in calls["stores"]] == ["press_start", "mega-mania", "cstech", "radio_popular", "gaming_replay"]
    assert all(not light for _, light in calls["stores"]) and calls["igdb"] == 5


def test_evening_run_is_light(monkeypatch):
    calls = run(monkeypatch, light=True)
    assert calls["stores"] == [("press_start", True), ("mega-mania", True), ("gaming_replay", True)]
    assert calls["igdb"] == 0


def test_server_schedule_times():
    """The server's daemon: 06:00 morning, 18:00 light evening, Lisbon wall-clock time."""
    from datetime import datetime
    from scheduler.daemon import TIMEZONE, next_run

    def at(*args):
        return datetime(*args, tzinfo=TIMEZONE)

    assert next_run(at(2026, 10, 4, 5, 59)) == (at(2026, 10, 4, 6, 0), [])
    assert next_run(at(2026, 10, 4, 6, 0)) == (at(2026, 10, 4, 18, 0), ["--light"])
    assert next_run(at(2026, 10, 4, 23, 0)) == (at(2026, 10, 5, 6, 0), [])
    # Summer time ends on 2026-10-25: still 06:00 on the clock, not 05:00
    when, _ = next_run(at(2026, 10, 24, 19, 0))
    assert when.hour == 6 and when.utcoffset().total_seconds() == 0


def test_run_problems_are_emailed(monkeypatch):
    """On a server nobody sees the Windows notification: ALERT_EMAIL gets the problems."""
    from app import config
    from scheduler import notify

    sent = []
    monkeypatch.setattr(config, "ALERT_EMAIL", "admin@example.invalid")
    monkeypatch.setattr(notify.mail_service, "send", lambda *a: sent.append(a))
    monkeypatch.setattr(notify, "toast", lambda *a: None)
    notify.notify("Game Price Tracker", "Falhou: cstech")
    assert sent == [("admin@example.invalid", "Game Price Tracker", "Falhou: cstech")]

    monkeypatch.setattr(config, "ALERT_EMAIL", "")
    notify.notify("Game Price Tracker", "Falhou: cstech")
    assert len(sent) == 1
