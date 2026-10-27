"""Поиск «по примеру»: из объявления-образца получаем запрос, фильтр по заголовку и раздел.

Пользователь даёт ссылку на конкретное объявление (например, на нужную модель), программа берёт
заголовок, отбрасывает память, цвета и рекламные слова и ищет такие же устройства. Это эвристика:
результат записывается в data/examples.json, а при ошибке можно задать запрос и фильтр вручную.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

# Слова, которые не говорят о модели.
STOP_WORDS = {
    "б/у", "бу", "новый", "новая", "новое", "новые", "идеал", "идеальное", "идеальный", "идеальном",
    "состояние", "состоянии", "отличное", "отличном", "срочно", "торг", "обмен", "гарантия", "комплект",
    "коробка", "чек", "оригинал", "в", "на", "с", "и", "для", "цвет", "от", "по", "без", "продам",
    "чёрный", "черный", "белый", "серый", "синий", "красный", "зеленый", "зелёный", "золотой", "розовый",
    "фиолетовый", "голубой", "серебристый", "black", "white", "silver", "gold", "blue", "green", "grey",
    "gray", "red", "pink", "purple", "sim", "esim", "dual", "wifi", "wi-fi", "lte", "nfc", "ростест",
    "рст", "gb", "tb", "гб", "тб", "gb.", "ram",
}
STORAGE_NUMBERS = {"16", "32", "64", "128", "256", "512", "1024", "2048"}
RAM_NUMBERS = {"2", "3", "4", "6", "8", "12", "16", "24"}
MAX_TOKENS = 6

# Слова, меняющие устройство: если их нет в образце, объявления с ними отбрасываем.
MODIFIERS: dict[str, tuple[str, ...]] = {
    "pro": ("pro", "про"), "max": ("max", "макс"), "plus": ("plus", "плюс"),
    "ultra": ("ultra", "ультра"), "mini": ("mini", "мини"), "fe": ("fe",),
    "lite": ("lite", "лайт"), "oled": ("oled", "олед"), "slim": ("slim", "слим"),
}
STORAGE_CATEGORIES = ("telefony", "planshety", "noutbuki")


@dataclass
class Derived:
    name: str
    query: str
    match: str
    exclude: str
    category: str
    variant: str


def is_listing_url(url: str) -> bool:
    """Ссылка на конкретное объявление: последний кусок пути заканчивается длинным номером."""
    parts = urlsplit((url or "").strip())
    last = [p for p in parts.path.split("/") if p][-1:] or [""]
    return bool(re.search(r"_\d{6,}$", last[0]))


def slug_title(url: str) -> str:
    """Заголовок из адреса объявления: samsung_galaxy_s22_8_128_gb_4012345678 -> 'samsung galaxy s22 8 128 gb'."""
    last = [p for p in urlsplit(url.strip()).path.split("/") if p][-1:] or [""]
    return re.sub(r"_\d{6,}$", "", last[0]).replace("_", " ").strip()


def category_from_url(url: str) -> str:
    parts = [p for p in urlsplit(url.strip()).path.split("/") if p]
    return parts[1] if len(parts) >= 3 else ""      # /город/раздел/объявление


def words_to_regex(words: str) -> str:
    """Все слова обязаны быть в заголовке (в любом порядке)."""
    parts = [re.escape(w.lower()) for w in words.split() if w.strip()]
    return "".join(f"(?=.*{p})" for p in parts) + ".*" if parts else ""


def tokens_from_title(title: str) -> list[str]:
    text = re.sub(r"\d+\s*/\s*\d+", " | ", title.lower())          # 8/128 -> граница
    text = re.sub(r"\d[\d\s]*\s*(₽|руб\w*)", " ", text)            # цена в тексте
    raw = re.findall(r"[a-zа-яё0-9+]+(?:-[a-zа-яё0-9]+)?|\|", text)
    kept: list[str] = []
    for tok in raw:
        if tok == "|":                                             # дальше пошла память
            break
        if tok in STOP_WORDS:
            continue
        if len(kept) >= 2 and re.fullmatch(r"\d+(gb|tb|гб|тб)", tok):      # 256gb: дальше память
            break
        if len(kept) >= 2 and tok.isdigit() and tok in STORAGE_NUMBERS:
            if len(kept) >= 3 and kept[-1] in RAM_NUMBERS and any(c.isdigit() for c in kept[-2]):
                kept.pop()                                         # «s22 8 128»: 8 это оперативка
            break
        kept.append(tok)
        if len(kept) >= MAX_TOKENS:
            break
    return kept


def derive(title: str, url: str = "") -> Derived:
    tokens = tokens_from_title(title) or tokens_from_title(slug_title(url))
    text = " ".join(tokens)
    present = set(tokens)
    absent = [alts for alts in MODIFIERS.values() if not present.intersection(alts)]
    words = "|".join(re.escape(a) for alts in absent for a in alts)
    exclude = rf"(?<![a-zа-яё0-9])({words})(?![a-zа-яё0-9])" if words else ""
    plus_absent = not present.intersection(MODIFIERS["plus"]) and not any(t.endswith("+") for t in tokens)
    if plus_absent:
        exclude = (exclude + "|" if exclude else "") + r"\d\+"
    category = category_from_url(url)
    name = text.title() if text else "Свой поиск"
    return Derived(name=name, query=text, match=words_to_regex(text), exclude=exclude, category=category,
                   variant="storage" if any(c in category for c in STORAGE_CATEGORIES) else "none")
