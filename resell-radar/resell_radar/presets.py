"""Готовые наборы моделей для мастера настройки.

Регулярки работают по заголовку в нижнем регистре. Если нужной модели нет,
в мастере можно добавить свою или дописать [[items]] в config.toml.
"""
from __future__ import annotations

from .config import ItemConfig

SAMSUNG = r"samsung|galaxy|самсунг|галакси"
APPLE = r"iphone|айфон|apple"
NINTENDO = r"nintendo|нинтендо|switch|свич|свитч"
CONSOLE_JUNK = (r"switch\s?2|свич\s?2|свитч\s?2|чехол|кейс|сумка|плёнк|пленк|"
                r"только игр|игры для|аккаунт|подписк")
PHONE_MIN = 6000


def _samsung_series(n: int) -> list[ItemConfig]:
    s = rf"s\s?{n}"
    return [
        ItemConfig(f"Samsung Galaxy S{n}", f"Samsung Galaxy S{n}", brand=SAMSUNG,
                   match=rf"\b{s}\b", exclude=rf"{s}\s?(\+|plus|плюс|ultra|ультра|fe|edge)",
                   min_price=PHONE_MIN),
        ItemConfig(f"Samsung Galaxy S{n}+", f"Samsung Galaxy S{n}+", brand=SAMSUNG,
                   match=rf"\b{s}\s?(\+|plus|плюс)", exclude=r"ultra|ультра",
                   min_price=PHONE_MIN),
        ItemConfig(f"Samsung Galaxy S{n} Ultra", f"Samsung Galaxy S{n} Ultra", brand=SAMSUNG,
                   match=rf"\b{s}\s?(ultra|ультра)", min_price=PHONE_MIN),
    ]


def _pixel(n: int) -> list[ItemConfig]:
    p = rf"pixel\s?{n}"
    return [
        ItemConfig(f"Google Pixel {n}", f"Google Pixel {n}",
                   match=rf"{p}\b", exclude=rf"{p}\s?(pro|a\b|xl)", min_price=PHONE_MIN),
        ItemConfig(f"Google Pixel {n} Pro", f"Google Pixel {n} Pro",
                   match=rf"{p}\s?pro", min_price=PHONE_MIN),
    ]


def _iphone(n: int) -> list[ItemConfig]:
    i = rf"(?:iphone|айфон)\s?{n}"
    return [
        ItemConfig(f"iPhone {n}", f"iPhone {n}",
                   match=rf"{i}\b", exclude=rf"{i}\s?(pro|про|mini|мини|plus|плюс|max|макс|se)",
                   min_price=PHONE_MIN),
        ItemConfig(f"iPhone {n} Pro", f"iPhone {n} Pro",
                   match=rf"{i}\s?(pro|про)\b", exclude=r"max|макс", min_price=PHONE_MIN),
        ItemConfig(f"iPhone {n} Pro Max", f"iPhone {n} Pro Max",
                   match=rf"{i}\s?(pro|про)\s?(max|макс)", min_price=PHONE_MIN),
    ]


def _console(name: str, query: str, match: str, exclude: str, modded: bool,
             max_buy: int | None = None) -> ItemConfig:
    label = f"{name} (прошитая)" if modded else name
    return ItemConfig(label, f"{query} прошитая" if modded else query,
                      category="igry_pristavki_i_programmy", brand=NINTENDO,
                      match=match, exclude=f"{exclude}|{CONSOLE_JUNK}",
                      min_price=6000, max_buy=max_buy, variant="none")


def _generic(name: str, query: str, match: str, exclude: str = "", min_price: int = 3000,
             category: str = "", variant: str = "none") -> ItemConfig:
    """Устройство не из телефонов: ищем по всему Avito (category пустая), заголовок режет регулярка.

    variant="none": цены всей модели считаются одной группой (подходит наушникам и консолям);
    для планшетов и ноутбуков передаём "storage": цена сильно зависит от памяти.
    """
    return ItemConfig(name, query, category=category, match=match, exclude=exclude,
                      min_price=min_price, variant=variant)


# Разделы Avito для своих моделей в мастере. Пустой раздел = поиск по всему Avito.
CATEGORIES: list[tuple[str, str]] = [
    ("Весь Avito (любой раздел)", ""),
    ("Телефоны", "telefony"),
    ("Планшеты", "planshety_i_elektronnye_knigi"),
    ("Ноутбуки", "noutbuki"),
    ("Игры, приставки и программы", "igry_pristavki_i_programmy"),
    ("Аудио и видео", "audio_i_video"),
    ("Фототехника", "fototehnika"),
]


AIRPODS = r"(?:airpods|аирподс|эйрподс|эирподс)"
PRO = r"(?:pro|про)"
IPAD = r"(?:ipad|айпад)"
MACBOOK_AIR = r"(?:macbook|макбук)\s?(?:air|эйр)"
CONSOLE_CAT = "igry_pristavki_i_programmy"


def _audio() -> list[ItemConfig]:
    return [
        _generic("AirPods Pro 2", "AirPods Pro 2", rf"{AIRPODS}\s?{PRO}\s?(?:2|ii|второго)", min_price=3000),
        _generic("AirPods Pro", "AirPods Pro", rf"{AIRPODS}\s?{PRO}\b", rf"{PRO}\s?(?:2|ii|второго)", 2500),
        _generic("AirPods 3", "AirPods 3", rf"{AIRPODS}\s?3\b|{AIRPODS}\s?3rd", PRO, 2500),
    ]


def _tablets() -> list[ItemConfig]:
    return [
        _generic("iPad 9", "iPad 9", rf"{IPAD}\s?(?:9\b|9(?:th|-го|\s?gen|\s?поколени)|10[.,]2)",
                 r"pro|air|mini|про|эйр", 8000, variant="storage"),
        _generic("iPad 10", "iPad 10", rf"{IPAD}\s?(?:10(?![.,]2)\b|10(?:th|-го|\s?gen|\s?поколени)|10[.,]9)",
                 r"pro|air|mini|про|эйр", 12000, variant="storage"),
        _generic("iPad Air 5", "iPad Air 5", rf"{IPAD}\s?(?:air|эйр)\s?(?:5\b|5th|m1)", "", 15000, variant="storage"),
    ]


def _laptops() -> list[ItemConfig]:
    return [
        _generic("MacBook Air M1", "MacBook Air M1",
                 rf"{MACBOOK_AIR}[^,]{{0,25}}\bm1\b|\bm1\b[^,]{{0,25}}{MACBOOK_AIR}", r"pro|про", 25000, variant="storage"),
        _generic("MacBook Air M2", "MacBook Air M2",
                 rf"{MACBOOK_AIR}[^,]{{0,25}}\bm2\b|\bm2\b[^,]{{0,25}}{MACBOOK_AIR}", r"pro|про", 35000, variant="storage"),
    ]


def _consoles_other() -> list[ItemConfig]:
    return [
        _generic("PlayStation 5", "PlayStation 5", r"(?:ps\s?5|playstation\s?5|плейстейшн\s?5|пс\s?5)\b",
                 r"pro|про|джойстик|геймпад\s+(?:для|dual)", 15000, CONSOLE_CAT),
        _generic("PlayStation 4 Pro", "PlayStation 4 Pro", r"(?:ps\s?4|playstation\s?4|плейстейшн\s?4|пс\s?4)\s?(?:pro|про)",
                 "", 6000, CONSOLE_CAT),
        _generic("PlayStation 4", "PlayStation 4", r"(?:ps\s?4|playstation\s?4|плейстейшн\s?4|пс\s?4)\b",
                 r"pro|про", 5000, CONSOLE_CAT),
        _generic("Xbox Series S", "Xbox Series S", r"xbox\s?series\s?s\b|xbox\s?s\b|икс\s?бокс\s?s\b",
                 "", 10000, CONSOLE_CAT),
        _generic("Xbox Series X", "Xbox Series X", r"xbox\s?series\s?x\b|xbox\s?x\b|икс\s?бокс\s?x\b",
                 "", 20000, CONSOLE_CAT),
        _generic("Steam Deck", "Steam Deck", r"steam\s?deck|стим\s?дек", "", 20000, CONSOLE_CAT),
    ]


def _catalog() -> dict[str, list[ItemConfig]]:
    samsung: list[ItemConfig] = []
    for n in (22, 23, 24, 25):
        samsung += _samsung_series(n)
    pixel: list[ItemConfig] = []
    for n in (7, 8, 9):
        pixel += _pixel(n)
    iphone: list[ItemConfig] = []
    for n in (11, 12, 13, 14, 15):
        iphone += _iphone(n)
    switch: list[ItemConfig] = []
    for modded in (True, False):
        switch.append(_console("Nintendo Switch Lite", "Nintendo Switch Lite",
                               r"switch\s?lite|свич\s?лайт|свитч\s?лайт|\blite\b|лайт",
                               r"oled|олед", modded))
        switch.append(_console("Nintendo Switch OLED", "Nintendo Switch OLED",
                               r"oled|олед", r"lite|лайт", modded))
    return {
        "Samsung": samsung, "Google Pixel": pixel, "iPhone": iphone,
        "Nintendo Switch": switch, "Другие консоли": _consoles_other(),
        "Наушники": _audio(), "Планшеты": _tablets(), "Ноутбуки": _laptops(),
    }


def groups() -> dict[str, list[ItemConfig]]:
    """Пресеты по группам для мастера настройки."""
    return _catalog()


def all_presets() -> list[ItemConfig]:
    return [item for items in _catalog().values() for item in items]
