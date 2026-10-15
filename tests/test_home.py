"""The home page is the landing page, at / (user, 2026-10-15); the tabs and the search moved to /browse, and the old
/?tab=… and /?q=… links (bookmarks, shared links, e-mails) still reach them with their filters."""
import pytest


@pytest.mark.parametrize("old, new", [
    ("/?tab=releases", "/browse?tab=releases"),
    ("/?q=zelda&page=2&store=cstech", "/browse?q=zelda&page=2&store=cstech"),
    ("/?tab=catalog&platform=PS5&tags=historical_low", "/browse?tab=catalog&platform=PS5&tags=historical_low"),
    ("/?tab=wishlist", "/wishlist"),
    ("/browse?tab=favorites", "/wishlist"),
])
def test_old_links_reach_the_tabs(web_client, old, new):
    response = web_client.get(old)
    assert response.status_code == 301 and response.headers["Location"] == new


def test_home_and_browse_pages(web_client):
    home = web_client.get("/").get_data(as_text=True)
    assert "/static/pages/home.js" in home and "/static/slider.js" in home
    assert '<h1 class="site-brand' in home and 'action="/browse"' in home       # the name is the page's title
    browse = web_client.get("/browse").get_data(as_text=True)
    assert "/static/pages/index.js" in browse and "/static/slider.js" in browse
    assert 'data-go-home' not in browse and 'id="home-btn"' not in browse        # the name opens the home page; the
                                                                                 # tabs leave a search (no "Secções")


def test_recent_releases_api(web_client):
    response = web_client.get("/api/releases/recent?platform=PS5")
    assert response.status_code == 200 and response.get_json() == []
