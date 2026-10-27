"""Маржа, окупаемость и оценка риска объявления."""
from __future__ import annotations

from dataclasses import dataclass, field

from .condition import Condition, Decision
from .config import REPAIR_LABELS, ItemConfig, Settings
from .market import Stats
from .models import Listing


@dataclass
class Assessment:
    listing: Listing
    item: ItemConfig
    group: str
    market: int                 # медиана рынка
    market_count: int
    below_pct: float            # на сколько % цена ниже медианы (может быть < 0)
    sell_price: int
    repair_cost: int
    repairs: list[str]
    margin: int                 # чистая прибыль, ₽
    roi_pct: float              # прибыль к цене закупки, %
    risk: int                   # 0..100
    risk_reasons: list[str] = field(default_factory=list)
    battery_pct: int | None = None
    description_checked: bool = False

    @property
    def risk_level(self) -> str:
        return "низкий" if self.risk < 25 else "средний" if self.risk < 50 else "высокий"


def sell_price_for(item: ItemConfig, stats: Stats | None, settings: Settings) -> int | None:
    """Цена, за которую рассчитываем продать: твоя из конфига или оценка по рынку.

    Цены в объявлениях выше реальных цен сделок (покупатели торгуются), поэтому по
    умолчанию берётся нижняя четверть рынка (q1), а не медиана.
    """
    if item.sell_price:
        return item.sell_price
    if stats:
        base = stats.q1 if settings.sell_basis == "q1" else stats.median
        return round(base * (1 - settings.sell_discount_pct / 100))
    return None


def margin_for(price: int, sell_price: int, settings: Settings, repair_cost: int = 0) -> tuple[int, float]:
    margin = sell_price * (1 - settings.commission_pct / 100) - price - repair_cost
    roi = margin / price * 100 if price else 0.0
    return round(margin), roi


def risk_score(price: int, stats: Stats | None, cond: Condition | None,
               description: str | None, accepted_repairs: list[str]) -> tuple[int, list[str]]:
    score, reasons = 0, []
    if stats:
        ratio = price / stats.median
        pct = round((1 - ratio) * 100)
        if ratio < 0.5:
            score += 45; reasons.append(f"цена на {pct}% ниже рынка, так не бывает без причины")
        elif ratio < 0.6:
            score += 35; reasons.append(f"цена на {pct}% ниже рынка")
        elif ratio < 0.7:
            score += 25; reasons.append(f"цена на {pct}% ниже рынка")
        elif ratio < 0.8:
            score += 10; reasons.append(f"цена на {pct}% ниже рынка")
        if stats.used < 5:
            score += 10; reasons.append(f"мало данных по рынку ({stats.used} объявл.)")
        if stats.approx:
            score += 10; reasons.append("вариант (память, комплектация) не определён, рынок оценён по всей модели")
    else:
        score += 20; reasons.append("нет оценки рынка")

    if description is None:
        score += 10; reasons.append("описание не удалось проверить")
    elif len(description.strip()) < 40:
        score += 15; reasons.append("описание пустое или совсем короткое")

    if cond:
        if cond.replaced:
            score += 15; reasons.append("был ремонт или замена деталей")
        if cond.soft:
            score += 5; reasons.append("есть следы использования")
    if accepted_repairs:
        score += 10; reasons.append("известные неисправности: " + ", ".join(REPAIR_LABELS.get(r, r) for r in accepted_repairs))
    return min(score, 100), reasons


def assess(listing: Listing, item: ItemConfig, group: str, stats: Stats | None,
           cond: Condition | None, decision: Decision | None, description: str | None,
           settings: Settings) -> Assessment | None:
    """Полная оценка. None, если нечем считать (нет цены продажи)."""
    sell = sell_price_for(item, stats, settings)
    if sell is None:
        return None
    repair_cost = decision.repair_cost if decision else 0
    margin, roi = margin_for(listing.price, sell, settings, repair_cost)
    market = stats.median if stats else sell
    below = (1 - listing.price / market) * 100 if market else 0.0
    risk, reasons = risk_score(listing.price, stats, cond, description,
                               decision.repairs if decision else [])
    return Assessment(
        listing=listing, item=item, group=group, market=market,
        market_count=stats.used if stats else 0, below_pct=below, sell_price=sell,
        repair_cost=repair_cost, repairs=decision.repairs if decision else [],
        margin=margin, roi_pct=roi, risk=risk, risk_reasons=reasons,
        battery_pct=cond.battery_pct if cond else None,
        description_checked=description is not None,
    )
