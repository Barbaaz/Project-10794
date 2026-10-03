"""
The web app: the two pages and the JSON API. All data comes from the database, which the
scheduler fills (python -m scheduler.run_all_scrapers). Nothing here scrapes the stores.

    python app.py                     # development server, http://127.0.0.1:5000
    waitress-serve app.web:app        # production server (Docker uses this)
"""
from datetime import timedelta
from pathlib import Path

from flask import Flask, abort, request, jsonify, redirect, render_template, send_from_directory
from werkzeug.exceptions import HTTPException

from app.config import COOKIE_SECURE, SECRET_KEY
from app.routes import auth, chat, collection, games, listings, moderation, prices, ratings, reviews, stores
from app.services.game_service import game_exists, merged_into
from app.services.photo_storage import MAX_UPLOAD_BYTES, storage

ROOT = Path(__file__).resolve().parent.parent

app = Flask(__name__, template_folder=str(ROOT / "templates"), static_folder=str(ROOT / "static"))
app.config.update(
    SECRET_KEY=SECRET_KEY,
    SESSION_COOKIE_HTTPONLY=True,           # page scripts can't read the login cookie
    SESSION_COOKIE_SAMESITE="Lax",          # not sent with requests started by other sites
    SESSION_COOKIE_SECURE=COOKIE_SECURE,    # HTTPS only, once served over HTTPS
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    MAX_CONTENT_LENGTH=11 * MAX_UPLOAD_BYTES,  # a listing's photos (up to 10) in one request
)
for blueprint in (auth.bp, chat.bp, collection.bp, games.bp, listings.bp, moderation.bp, prices.bp,
                  ratings.bp, reviews.bp, stores.bp):
    app.register_blueprint(blueprint)

CHANGING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@app.before_request
def only_our_pages_change_things():
    """
    Requests that change something must come from our own pages' scripts: they send the
    X-Requested-With header, which another site can't add to a request to us (no CORS here).
    Together with the SameSite cookie, this stops other sites acting as a logged-in visitor.
    """
    if request.method in CHANGING_METHODS and request.headers.get("X-Requested-With") != "fetch":
        abort(403, description="missing_request_header")


@app.errorhandler(HTTPException)
def json_error(e):
    if request.path.startswith("/api/"):
        return jsonify(error=e.description), e.code
    return e


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/account")
def account_page():
    """Log in / create an account; the account itself when logged in."""
    return render_template("account.html")


@app.route("/sell")
def sell_page():
    """Put a game up for sale (the page sends logged-out visitors to /account first)."""
    return render_template("sell.html")


@app.route("/listing/<int:listing_id>")
def listing_page(listing_id):
    """A game someone sells: photos, price, seller; the seller manages it here too."""
    return render_template("listing.html", listing_id=listing_id)


@app.route("/messages")
def messages_page():
    """The user's conversations; ?c=<id> opens one."""
    return render_template("messages.html")


@app.route("/user/<username>")
def profile_page(username):
    """A user's public profile: rating, ratings received, listings."""
    return render_template("profile.html", username=username)


@app.route("/collection")
def collection_page():
    """The user's game collection and wishlist (the page sends logged-out visitors to /account)."""
    return render_template("collection.html")


@app.route("/admin")
def admin_page():
    """The moderators' tools: reports, problem purchases, the log, and (admins) the staff list.
    The page is plain HTML; its data comes from /api/mod/…, which checks the role."""
    return render_template("admin.html")


@app.route("/media/<path:key>")
def media(key):
    """Uploaded photos kept on this computer (app/services/photo_storage.py); no paths outside it."""
    return send_from_directory(storage.root, key, max_age=7 * 24 * 3600)


@app.route("/favicon.ico")
def favicon():
    """Browsers ask for /favicon.ico on their own; the pages link the SVG icon."""
    return redirect("/static/favicon.svg", code=301)


@app.route("/game/<int:game_id>")
def game_page(game_id):
    """Editions, offers and price history; the page loads its data from /api/games/<id>."""
    # A game merged into another (pipeline/rematch.py): old links go to the one that replaced it
    if not game_exists(game_id) and (new_id := merged_into("game", [game_id]).get(game_id)):
        return redirect(f"/game/{new_id}", code=301)
    return render_template("game.html", game_id=game_id)
