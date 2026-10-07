from urllib.parse import quote

from scrapers.base.base_scraper import BaseScraper
from .parser import parse_products, parse_product_page


class MegaManiaScraper(BaseScraper):
    store_slug = "mega-mania"
    base_url = "https://mega-mania.com.pt"

    listing_parser = parse_products
    product_page_parser = parse_product_page

    catalog_urls = {
        "https://mega-mania.com.pt/pt/catalogo/456-ps/457-jogos": "PS5",
        "https://mega-mania.com.pt/pt/catalogo/1-ps/93-jogos": "PS4",
        "https://mega-mania.com.pt/pt/catalogo/5-nintendo/268-jogos/225-nintendo-switch": "Switch",
        "https://mega-mania.com.pt/pt/catalogo/5-nintendo/268-jogos/525-nintendo-switch-2": "Switch2",
        "https://mega-mania.com.pt/pt/catalogo/480-xbox-one-x/481-jogos": "XboxSeries",  # despite the URL, Series X games
        "https://mega-mania.com.pt/pt/catalogo/2-xbox-one/159-jogos": "XboxOne",
        "https://mega-mania.com.pt/pt/catalogo/10-pc/278-jogos": "PC",
    }
    # Consoles (new and used), controllers, headsets and VR (core/hardware.py). Nintendo's pages mix
    # Switch and Switch 2: the platform from the name there
    hardware_urls = {f"https://mega-mania.com.pt/pt/catalogo/{path}": hint for path, hint in {
        "456-ps/460-consolas/478-consolas-novas": ("PS5", "console"),
        "456-ps/460-consolas/479-consolas-ps5-usadas": ("PS5", "console"),
        "456-ps/459-acessorios/470-comandos": ("PS5", "accessory"),
        "456-ps/459-acessorios/471-playstation-vr": ("PS5", "accessory"),
        "456-ps/459-acessorios/472-auscultadores": ("PS5", "accessory"),
        "1-ps/156-consolas/157-consolas-ps4": ("PS4", "console"),
        "1-ps/156-consolas/158-consolas-ps4": ("PS4", "console"),
        "1-ps/148-acessorios/149-comandos": ("PS4", "accessory"),
        "1-ps/148-acessorios/150-playstation-vr": ("PS4", "accessory"),
        "1-ps/148-acessorios/151-auscultadores": ("PS4", "accessory"),
        "480-xbox-one-x/484-consolas/499-consolas-novas": ("XboxSeries", "console"),
        "480-xbox-one-x/484-consolas/500-consolas-usadas": ("XboxSeries", "console"),
        "480-xbox-one-x/483-acessorios/495-comandos": ("XboxSeries", "accessory"),
        "480-xbox-one-x/483-acessorios/496-auscultadores": ("XboxSeries", "accessory"),
        "2-xbox-one/179-consolas/180-consolas-novas": ("XboxOne", "console"),
        "2-xbox-one/179-consolas/181-consolas-usadas": ("XboxOne", "console"),
        "2-xbox-one/172-acessorios/176-comandos": ("XboxOne", "accessory"),
        "2-xbox-one/172-acessorios/177-auscultadores": ("XboxOne", "accessory"),
        "5-nintendo/275-consolas/534-consolas-nitendo-switch": ("Switch2", "console"),
        "5-nintendo/275-consolas/276-consolas-nitendo-switch": ("Switch", "console"),
        "5-nintendo/275-consolas/277-consolas-usadas": (None, "console"),
        "5-nintendo/271-acessorios/272-comandos": (None, "accessory"),
        "5-nintendo/271-acessorios/273-auscutadores": (None, "accessory"),
    }.items()}

    def build_search_url(self, query, page):
        return f"{self.base_url}/pt/catalogo/?p={page}&f={quote(query)}&ppage=50"

    def build_page_url(self, url, page):
        return f"{url}?p={page}&ppage=50"
