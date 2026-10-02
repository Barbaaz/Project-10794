from flask import Flask, request, jsonify, render_template
from werkzeug.exceptions import HTTPException

from app.routes import games, prices, stores
from app.services.game_service import search_offers

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


@app.route("/game/<int:game_id>")
def game_page(game_id):
    """Editions, offers and price history; the page loads its data from /api/games/<id>."""
    return render_template("game.html", game_id=game_id)


@app.route("/search")
def search():
    """Used by templates/index.html: one group per game edition with its offers."""
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify([])
    return jsonify(search_offers(query))


if __name__ == "__main__":
    # Development server; restarts by itself when a .py file changes
    app.run(debug=True)
