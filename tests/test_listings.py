"""The marketplace: listings with photos (on a throwaway database, photos in a temporary folder)."""
import io

import pytest
from PIL import Image

from app.services import photo_storage
from app.services.photo_storage import PhotoError, process_photo
from helpers import HEADERS, jpeg, new_listing, sign_up


def png():
    out = io.BytesIO()
    Image.new("RGBA", (500, 500), (0, 0, 255, 128)).save(out, "PNG")
    return out.getvalue()


# --- photos ----------------------------------------------------------------------------------

def test_photos_lose_their_hidden_data_and_are_resized():
    original = jpeg(gps=True)
    assert Image.open(io.BytesIO(original)).getexif().get(0x8825)       # the upload has a location

    photo, thumb = process_photo(original)
    for data, size in ((photo, photo_storage.MAX_SIZE), (thumb, photo_storage.THUMB_SIZE)):
        image = Image.open(io.BytesIO(data))
        assert image.format == "JPEG" and max(image.size) == size
        assert not image.getexif()                                       # no location, no phone model


def test_only_real_images_are_accepted():
    assert process_photo(png())                                          # PNG is fine (saved as JPEG)
    for bad in (b"not an image at all", b"%PDF-1.4 fake", b"GIF89a" + b"\0" * 100):
        with pytest.raises(PhotoError):
            process_photo(bad)
    with pytest.raises(PhotoError, match="photo_too_big"):
        process_photo(b"\xff" * (photo_storage.MAX_UPLOAD_BYTES + 1))


# --- listings through the API ------------------------------------------------------------------

def test_selling_needs_an_account(market):
    assert new_listing(market).status_code == 401


def test_create_listing(market):
    sign_up(market["client"], "seller_1")
    response = new_listing(market)
    assert response.status_code == 201
    listing = response.get_json()
    assert (listing["price"], listing["condition"], listing["status"]) == (24.9, "good", "active")
    assert (listing["title"], listing["edition"], listing["seller_username"]) == ("Market Test Game", "Standard", "seller_1")
    assert "email" not in str(listing).lower()                       # the seller's email is never shown
    assert len(listing["photos"]) == 3

    # the files exist, and are served
    photo = listing["photos"][0]
    assert (market["dir"] / photo["photo_key"]).exists() and (market["dir"] / photo["thumb_key"]).exists()
    served = market["client"].get(photo["url"])
    assert served.status_code == 200 and not Image.open(io.BytesIO(served.data)).getexif()

    # on the game's list for everyone
    market["client"].post("/api/auth/logout", headers=HEADERS)
    shown = market["client"].get(f"/api/listings?game_id={market['game']}").get_json()
    assert [l["id"] for l in shown] == [listing["id"]]


@pytest.mark.parametrize("fields, photos, error", [
    ({}, 2, "photo_count"),                                   # at least 3 photos
    ({}, 11, "photo_count"),                                  # at most 10
    ({"price": "0"}, 3, "price_invalid"),
    ({"price": "abc"}, 3, "price_invalid"),
    ({"condition": "broken"}, 3, "condition_invalid"),
    ({"description": "x" * 2001}, 3, "description_long"),
])
def test_listing_rules(market, fields, photos, error):
    sign_up(market["client"], "seller_2")
    response = new_listing(market, photos=photos, **fields)
    assert (response.status_code, response.get_json()["error"]) == (400, error)
    assert not list(market["dir"].rglob("*.jpg"))             # nothing kept from a refused listing


def test_edition_must_belong_to_the_game(market):
    sign_up(market["client"], "seller_3")
    assert new_listing(market, edition_id=market["other_edition"]).get_json()["error"] == "edition_invalid"


def test_only_the_seller_changes_a_listing(market):
    client = market["client"]
    sign_up(client, "seller_4")
    listing = new_listing(market).get_json()
    client.post("/api/auth/logout", headers=HEADERS)

    sign_up(client, "buyer_4")
    response = client.patch(f"/api/listings/{listing['id']}", json={"price": 1}, headers=HEADERS)
    assert (response.status_code, response.get_json()["error"]) == (403, "not_yours")
    client.post("/api/auth/logout", headers=HEADERS)

    client.post("/api/auth/login", json={"login": "seller_4", "password": "segredo123"}, headers=HEADERS)
    changed = client.patch(f"/api/listings/{listing['id']}", json={"price": "19.99", "status": "reserved"},
                           headers=HEADERS).get_json()
    assert (changed["price"], changed["status"]) == (19.99, "reserved")


def test_sold_listings_are_only_shown_to_the_seller(market):
    client = market["client"]
    sign_up(client, "seller_5")
    listing = new_listing(market).get_json()
    sold = client.patch(f"/api/listings/{listing['id']}", json={"status": "sold"}, headers=HEADERS).get_json()
    assert sold["status"] == "sold" and sold["sold_at"]
    assert [l["id"] for l in client.get("/api/listings/mine").get_json()] == [listing["id"]]

    client.post("/api/auth/logout", headers=HEADERS)
    assert client.get(f"/api/listings/{listing['id']}").status_code == 404
    assert client.get(f"/api/listings?game_id={market['game']}").get_json() == []


def test_photos_can_be_added_and_removed_within_the_limits(market):
    client = market["client"]
    sign_up(client, "seller_6")
    listing = new_listing(market).get_json()
    first = listing["photos"][0]

    response = client.delete(f"/api/listings/{listing['id']}/photos/{first['id']}", headers=HEADERS)
    assert response.get_json()["error"] == "photo_count"           # can't go below 3

    added = client.post(f"/api/listings/{listing['id']}/photos", headers=HEADERS, content_type="multipart/form-data",
                        data={"photos": [(io.BytesIO(jpeg()), "extra.jpg")]}).get_json()
    assert len(added["photos"]) == 4
    after = client.delete(f"/api/listings/{listing['id']}/photos/{first['id']}", headers=HEADERS).get_json()
    assert len(after["photos"]) == 3
    assert not (market["dir"] / first["photo_key"]).exists()        # its files are deleted too
