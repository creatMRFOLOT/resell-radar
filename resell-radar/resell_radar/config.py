"""Настройки проекта: чтение и запись config.toml.

Старые разделы [telegram] в файле игнорируются: уведомлений в Telegram больше нет,
находки пишутся в таблицу Excel (data/results.xlsx).
"""
from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_PATH = Path("config.toml")

# Что пользователь может уметь чинить. Ключи используются в condition.py.
REPAIR_CATEGORIES: dict[str, str] = {
    "screen": "экран (разбит, полосы, пятна, мерцает)",
    "back_glass": "заднее стекло / крышка",
    "battery": "аккумулятор (сильный износ, вздутие)",
    "board": "плата и электроника (не включается, камера, звук, связь, перезагрузки)",
    "water": "после воды / залитые",
    "locked": "заблокированные (iCloud, Google-аккаунт). Рискованно: часто не снять",
}
REPAIR_LABELS: dict[str, str] = {
    "screen": "экран", "back_glass": "заднее стекло", "battery": "аккумулятор",
    "board": "плата / электроника", "water": "после воды", "locked": "блокировка",
}
# Цены ремонта зависят от модели и города, у программы нет надёжной базы. Поэтому
# по умолчанию 0 (ремонт в марже не считается): пользователь вводит свои цены в мастере.
DEFAULT_REPAIR_COSTS: dict[str, int] = {key: 0 for key in REPAIR_CATEGORIES}

SELLER_CHOICES = ("private", "company", "any")
# На чём основана цена продажи. Цены в объявлениях выше реальных цен сделок (торг),
# поэтому по умолчанию берём нижнюю четверть рынка, а не медиану.
SELL_BASIS_CHOICES = ("q1", "median")


@dataclass
class ItemConfig:
    """Что искать: одна модель устройства."""
    name: str
    query: str
    category: str = "telefony"       # раздел Avito (telefony, igry_pristavki_i_programmy, ...)
    match: str = ""                  # регулярка по заголовку (нижний регистр)
    brand: str = ""                  # регулярка бренда в заголовке (необязательно)
    exclude: str = ""                # регулярка, которая отбрасывает заголовок
    min_price: int = 0               # ниже этой цены считаем мусором
    max_buy: int | None = None       # свой лимит закупки для этой модели
    sell_price: int | None = None    # твоя цена продажи; пусто = берём рынок
    example: str = ""                # ссылка на объявление-образец: запрос и фильтры выводятся из него
    url: str = ""                    # ссылка поиска Avito со всеми твоими фильтрами (приоритетнее query)
    # По чему делить рынок на группы: "storage" (объём памяти), "none" (вся модель одной группой)
    # или регулярка, первая скобка которой даёт название варианта, например "(digital|с приводом)".
    variant: str = "storage"


@dataclass
class Settings:
    check_every_min: int = 15
    block_pause_min: int = 30
    headless: bool = True             # True: Chrome работает скрыто, окно появляется только для проверки Avito
    region: str = "rossiya"           # rossiya, ekaterinburg, sverdlovskaya_oblast, ...
    favorite: bool = False            # добавлять найденное в избранное на Avito
    seller: str = "private"           # private = только частные лица, company = магазины, any = все
    profile_dir: str = "chrome_profile"
    data_dir: str = "data"

    max_buy: int = 0                  # 0 = не задан: укажите свой лимит закупки в мастере (setup)
    min_margin: int = 1000
    commission_pct: float = 11.0
    sell_basis: str = "q1"            # q1 = нижняя четверть рынка (осторожно), median = медиана
    sell_discount_pct: float = 0.0    # дополнительная скидка от выбранной базы, %

    repairable: list[str] = field(default_factory=list)   # пусто = только целые
    repair_costs: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_REPAIR_COSTS))
    risk_max: int = 60                # выше этого риска не присылаем
    min_group_size: int = 3           # минимум объявлений для оценки рынка
    market_window_days: int = 14

    items: list[ItemConfig] = field(default_factory=list)

    @property
    def only_working(self) -> bool:
        return not self.repairable


def _int_or_none(value) -> int | None:
    return int(value) if value not in (None, "") else None


def load(path: Path = CONFIG_PATH) -> Settings:
    """Прочитать config.toml. Если файла нет, вернуть настройки по умолчанию."""
    data: dict = {}
    if Path(path).exists():
        data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    mon = data.get("monitor", {})
    money, cond = data.get("money", {}), data.get("condition", {})

    s = Settings(
        check_every_min=int(mon.get("check_every_min", 15)),
        block_pause_min=int(mon.get("block_pause_min", 30)),
        headless=bool(mon.get("headless", True)),
        region=mon.get("region", "rossiya"),
        favorite=bool(mon.get("favorite", False)),
        seller=mon.get("seller", "private") if mon.get("seller", "private") in SELLER_CHOICES else "private",
        profile_dir=mon.get("profile_dir", "chrome_profile"),
        data_dir=mon.get("data_dir", "data"),
        max_buy=int(money.get("max_buy", 0)),
        min_margin=int(money.get("min_margin", 1000)),
        commission_pct=float(money.get("commission_pct", 11.0)),
        sell_basis=money.get("sell_basis", "q1") if money.get("sell_basis", "q1") in SELL_BASIS_CHOICES else "q1",
        sell_discount_pct=float(money.get("sell_discount_pct", 0.0)),
        repairable=[c for c in cond.get("repairable", []) if c in REPAIR_CATEGORIES],
        risk_max=int(cond.get("risk_max", 60)),
        min_group_size=int(cond.get("min_group_size", 3)),
        market_window_days=int(cond.get("market_window_days", 14)),
    )
    costs = dict(DEFAULT_REPAIR_COSTS)
    costs.update({k: int(v) for k, v in cond.get("repair_costs", {}).items() if k in costs})
    s.repair_costs = costs
    s.items = [
        ItemConfig(
            name=i["name"], query=i["query"],
            category=i.get("category", "telefony"),
            match=i.get("match", ""), brand=i.get("brand", ""), exclude=i.get("exclude", ""),
            min_price=int(i.get("min_price", 0)),
            max_buy=_int_or_none(i.get("max_buy")),
            sell_price=_int_or_none(i.get("sell_price")),
            url=i.get("url", ""),
            example=i.get("example", ""),
            variant=i.get("variant", "storage"),
        )
        for i in data.get("items", [])
    ]
    return s


def _q(value) -> str:
    """Строка в формате TOML (JSON-экранирование подходит для basic string)."""
    return json.dumps(value, ensure_ascii=False)


def dumps(s: Settings) -> str:
    lines = [
        "# resell-radar: настройки. Находки пишутся в data/results.xlsx.",
        "",
        "[monitor]",
        f"check_every_min = {s.check_every_min}",
        f"block_pause_min = {s.block_pause_min}",
        f"headless = {str(s.headless).lower()}",
        f"region = {_q(s.region)}",
        f"favorite = {str(s.favorite).lower()}   # true: ещё и кладёт находки в избранное на Avito (нужен вход: команда login)",
        f"seller = {_q(s.seller)}   # private (частные лица), company (магазины), any (все)",
        f"profile_dir = {_q(s.profile_dir)}",
        f"data_dir = {_q(s.data_dir)}",
        "",
        "[money]",
        f"max_buy = {s.max_buy}   # максимальная цена закупки, ₽ (обязательно укажите свою)",
        f"min_margin = {s.min_margin}   # минимальная чистая прибыль с одной сделки, ₽",
        f"commission_pct = {s.commission_pct}",
        f"sell_basis = {_q(s.sell_basis)}   # q1 (нижняя четверть рынка, осторожно) или median",
        f"sell_discount_pct = {s.sell_discount_pct}",
        "",
        "[condition]",
        "# Что умеешь чинить. Пусто = только целые телефоны.",
        f"# Варианты: {', '.join(REPAIR_CATEGORIES)}",
        f"repairable = {json.dumps(s.repairable)}",
        f"risk_max = {s.risk_max}",
        f"min_group_size = {s.min_group_size}",
        f"market_window_days = {s.market_window_days}",
        "",
        "[condition.repair_costs]",
    ]
    lines += [f"{k} = {int(v)}" for k, v in s.repair_costs.items()]
    for it in s.items:
        lines += ["", "[[items]]", f"name = {_q(it.name)}", f"query = {_q(it.query)}",
                  f"category = {_q(it.category)}"]
        for key in ("match", "brand", "exclude"):
            if getattr(it, key):
                lines.append(f"{key} = {_q(getattr(it, key))}")
        lines.append(f"min_price = {it.min_price}")
        if it.max_buy is not None:
            lines.append(f"max_buy = {it.max_buy}")
        if it.sell_price is not None:
            lines.append(f"sell_price = {it.sell_price}")
        if it.url:
            lines.append(f"url = {_q(it.url)}")
        if it.example:
            lines.append(f"example = {_q(it.example)}")
        if it.variant != "storage":
            lines.append(f"variant = {_q(it.variant)}")
    return "\n".join(lines) + "\n"


def save(s: Settings, path: Path = CONFIG_PATH) -> None:
    Path(path).write_text(dumps(s), encoding="utf-8")
