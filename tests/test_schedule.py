"""The morning run (every store, then IGDB) and the light evening run (no network, no database)."""
import scheduler.run_all_scrapers as run_all


def run(monkeypatch, light):
    calls = {"stores": [], "igdb": 0}
    monkeypatch.setattr(run_all, "setup_logging", lambda: None)
    monkeypatch.setattr(run_all, "active_store_slugs",
                        lambda: ["press_start", "mega-mania", "cstech", "darty", "gaming_replay"])
    monkeypatch.setattr(run_all, "run_store", lambda slug, light=False: calls["stores"].append((slug, light)) or {})
    for name in ("enrich_games", "fill_videos", "fill_tags", "fill_time_to_beat"):
        monkeypatch.setattr(run_all, name, lambda *a, **k: calls.__setitem__("igdb", calls["igdb"] + 1))
    monkeypatch.setattr(run_all, "complete_overdue", lambda: 0)
    monkeypatch.setattr(run_all, "notify", lambda *a: None)
    run_all.main(light=light)
    return calls


def test_morning_run_does_every_store_and_igdb(monkeypatch):
    calls = run(monkeypatch, light=False)
    assert [s for s, _ in calls["stores"]] == ["press_start", "mega-mania", "cstech", "darty", "gaming_replay"]
    assert all(not light for _, light in calls["stores"]) and calls["igdb"] == 4


def test_evening_run_is_light(monkeypatch):
    calls = run(monkeypatch, light=True)
    assert calls["stores"] == [("press_start", True), ("mega-mania", True), ("gaming_replay", True)]
    assert calls["igdb"] == 0
