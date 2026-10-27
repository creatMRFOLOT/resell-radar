"""Общие поддельные данные для тестов: страницы Avito, браузер и Telegram."""
from resell_radar.browser import Blocked


def card(item_id, title, price, city="ekaterinburg", snippet=""):
    desc = f'<div data-marker="item-description">{snippet}</div>' if snippet else ""
    return (f'<div data-marker="item" data-item-id="{item_id}">'
            f'<a data-marker="item-title" href="/{city}/telefony/phone_{item_id}?context=H4sIAAAA&x=1">'
            f'<h3 itemprop="name">{title}</h3></a>'
            f'<meta itemprop="price" content="{price}">{desc}</div>')


def search_page(cards):
    return "<html><body>" + "".join(cards) + "</body></html>"


def item_page(description, params=None, title=None):
    h1 = f'<h1 itemprop="name">{title}</h1>' if title else ""
    li = "".join(f"<li>{k}: {v}</li>" for k, v in (params or {}).items())
    return (f'<html><body>{h1}<div data-marker="item-view/item-description">{description}</div>'
            f'<ul data-marker="item-view/item-params">{li}</ul>'
            '<span data-marker="item-view/item-date">сегодня в 12:00</span>'
            '<span data-marker="item-view/total-views">120 просмотров</span>'
            '<span data-marker="item-view/today-views">+30 сегодня</span></body></html>')


class FakeBrowser:
    """get_html(url, selector) -> страница из словаря. Blocked, если url в blocked."""

    def __init__(self, search=None, items=None, blocked=(), favorite_status="added"):
        self.search = search or {}      # подстрока url -> html
        self.items = items or {}        # id объявления -> html
        self.blocked = set(blocked)
        self.opened = []
        self.favorites = []
        self.favorite_status = favorite_status

    def get_html(self, url, wait_selector, timeout_ms=0):
        self.opened.append(url)
        if any(b in url for b in self.blocked):
            raise Blocked("капча")
        for key, html in self.search.items():
            if key in url and "/telefony/phone_" not in url:
                return html
        for item_id, html in self.items.items():
            if url.endswith(f"phone_{item_id}"):
                return html
        return None

    def add_favorite(self, url):
        if any(b in url for b in self.blocked):
            raise Blocked("капча")
        self.favorites.append(url)
        return self.favorite_status

    def close(self):
        pass
