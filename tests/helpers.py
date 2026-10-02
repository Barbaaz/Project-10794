"""Shared by the marketplace tests: the request header, users, photos and listings."""
import io

from PIL import Image

HEADERS = {"X-Requested-With": "fetch"}   # what our pages send with requests that change something


def jpeg(width=2400, height=1800, gps=False):
    """A photo like a phone's: big, optionally with the place it was taken in its EXIF data."""
    image = Image.new("RGB", (width, height), (200, 30, 30))
    exif = Image.Exif()
    if gps:
        exif[0x8825] = {1: "N", 2: (38.0, 42.0, 0.0), 3: "W", 4: (9.0, 8.0, 0.0)}   # GPSInfo: Lisbon
        exif[0x0110] = "Phone Model X"                                            # Model
    out = io.BytesIO()
    image.save(out, "JPEG", exif=exif)
    return out.getvalue()


def sign_up(client, username):
    """A new account, logged in on `client`."""
    response = client.post("/api/auth/register", headers=HEADERS,
                           json={"username": username, "email": f"{username}@example.pt", "password": "segredo123"})
    assert response.status_code == 201
    return response.get_json()


def log_in(client, username):
    client.post("/api/auth/logout", headers=HEADERS)
    assert client.post("/api/auth/login", headers=HEADERS,
                       json={"login": username, "password": "segredo123"}).status_code == 200


def new_listing(m, photos=3, **fields):
    """Post a listing for the `market` fixture's game as the logged-in user (the response)."""
    data = {"game_id": m["game"], "edition_id": m["edition"], "price": "24.90", "condition": "good",
            "description": "Jogado uma vez.", **fields}
    data["photos"] = [(io.BytesIO(jpeg(gps=True)), f"p{i}.jpg") for i in range(photos)]
    return m["client"].post("/api/listings", data=data, headers=HEADERS, content_type="multipart/form-data")


def completed_purchase(m, seller="seller", buyer="buyer"):
    """A listing by `seller` bought by `buyer`, all steps done (buyer logged in at the end): the conversation id."""
    client = m["client"]
    sign_up(client, seller)
    listing = new_listing(m).get_json()
    sign_up(client, buyer)
    step = lambda cid, action: client.post(f"/api/conversations/{cid}/steps", json={"action": action}, headers=HEADERS)
    conversation_id = client.post(f"/api/listings/{listing['id']}/conversation", json={"buy": True},
                                  headers=HEADERS).get_json()["id"]
    log_in(client, seller)
    step(conversation_id, "accept")
    step(conversation_id, "sent")
    log_in(client, buyer)
    assert step(conversation_id, "received").get_json()["deal_status"] == "completed"
    return conversation_id
