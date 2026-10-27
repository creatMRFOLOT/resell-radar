"""Разбор HTML Avito. Все селекторы собраны здесь: если Avito сменит вёрстку,
чинить нужно только этот файл (и фикстуры в tests/)."""
from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from .models import ItemPage, Listing

BASE = "https://www.avito.ru"
CARD_SELECTOR = 'div[data-marker="item"]'
DESCRIPTION_SELECTOR = '[data-marker="item-view/item-description"], [itemprop="description"]'
SNIPPET_SELECTORS = ('[data-marker="item-description"]', '[class*="item-description"]',
                     '[class*="description-description"]')


def _digits(text: str) -> int | None:
    d = re.sub(r"\D", "", text or "")
    return int(d) if d else None


def _price(card: Tag) -> int | None:
    meta = card.find("meta", itemprop="price")
    if meta and str(meta.get("content", "")).isdigit():
        return int(meta["content"])
    el = card.select_one('[data-marker="item-price"]')
    return _digits(el.get_text()) if el else None


def clean_url(href: str) -> str:
    """Полная ссылка без трекинг-параметров (?context=...)."""
    return urljoin(BASE, href).split("?")[0]


def parse_search(html: str) -> list[Listing]:
    soup = BeautifulSoup(html or "", "html.parser")
    out: list[Listing] = []
    for card in soup.select(CARD_SELECTOR):
        try:
            link = card.select_one('a[data-marker="item-title"]') or card.find("a", href=True)
            title_el = card.select_one('[itemprop="name"]') or card.find("h3")
            price = _price(card)
            if not (link and title_el and price):
                continue
            url = clean_url(link["href"])
            item_id = card.get("data-item-id") or url.rsplit("_", 1)[-1]
            snippet = ""
            for sel in SNIPPET_SELECTORS:
                el = card.select_one(sel)
                if el:
                    snippet = el.get_text(" ", strip=True)
                    break
            date_el = card.select_one('[data-marker="item-date"]')
            parts = [p for p in url.replace(BASE, "").split("/") if p]
            out.append(Listing(
                id=str(item_id), title=title_el.get_text(" ", strip=True), price=price,
                url=url, snippet=snippet, city=parts[0] if parts else "",
                published=date_el.get_text(" ", strip=True) if date_el else "",
            ))
        except Exception:  # одна кривая карточка не должна ронять разбор
            continue
    return out


def parse_item(html: str) -> ItemPage:
    soup = BeautifulSoup(html or "", "html.parser")
    desc_el = soup.select_one(DESCRIPTION_SELECTOR)
    params: dict[str, str] = {}
    params_el = soup.select_one('[data-marker="item-view/item-params"]')
    if params_el:
        for li in params_el.find_all("li"):
            text = li.get_text(" ", strip=True).replace("\xa0", " ")
            if ":" in text:
                key, _, value = text.partition(":")
                params[key.strip().lower()] = value.strip()
    date_el = soup.select_one('[data-marker="item-view/item-date"]')
    total = soup.select_one('[data-marker="item-view/total-views"]')
    today = soup.select_one('[data-marker="item-view/today-views"]')
    title_el = soup.select_one('[data-marker="item-view/title-info"], h1[itemprop="name"], h1')
    return ItemPage(
        title=title_el.get_text(" ", strip=True) if title_el else "",
        description=desc_el.get_text(" ", strip=True) if desc_el else "",
        params=params,
        published=date_el.get_text(" ", strip=True) if date_el else "",
        total_views=_digits(total.get_text()) if total else None,
        today_views=_digits(today.get_text()) if today else None,
    )
