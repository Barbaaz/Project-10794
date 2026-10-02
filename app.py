from flask import Flask, request, jsonify, redirect, render_template
from werkzeug.exceptions import HTTPException

from app.routes import games, prices, stores
from app.services.game_service import game_exists, merged_into

# All data comes from the database, which the scheduler fills
# (python -m scheduler.run_all_scrapers). Nothing here scrapes the stores.
app = Flask(__name__)
app.register_blueprint(games.bp)
app.register_blueprint(prices.bp)
app.register_blueprint(stores.bp)


@app.errorhandler(HTTPException)
def json_error(e):
    if request.path.startswith("/api/"):
        return jsonify(error=e.description), e.code
    return e


@app.route("/")
def index():
    return render_template("index.html")


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


if __name__ == "__main__":
    # Development server; restarts by itself when a .py file changes
    app.run(debug=True)
