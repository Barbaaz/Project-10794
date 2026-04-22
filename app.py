from flask import Flask, request, jsonify, render_template
from db_insert import insert_products
from db_queries import get_recent_products
from scrapers.press_start.scraper import PressStartScraper
from scrapers.mega_mania.scraper import MegaManiaScraper

from core.matcher import match_products

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/search")
def search():
    query = request.args.get("q")

    recent = get_recent_products(query)

    if recent:
        print("A usar dados da BD")
        all_products = recent
    else:
        print("🌐 A fazer scraping")
        ps = PressStartScraper().run(query)
        mm = MegaManiaScraper().run(query)

        all_products = ps + mm

        insert_products(all_products)

    matched = match_products(all_products)

    return jsonify(matched)

    # ps = PressStartScraper().run(query)
    # mm = MegaManiaScraper().run(query)

    # all_products = ps + mm

    # print("ANTES DB")
    # insert_products(all_products)
    # print("DEPOIS DB")

    # matched = match_products(all_products)

    # return jsonify(matched)

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)