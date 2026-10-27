"""Один цикл мониторинга: выдача -> рынок -> кандидаты -> описание -> оценка -> таблица Excel."""
from __future__ import annotations

import logging
import random
import re
import time
from collections import Counter
from pathlib import Path

import json
from dataclasses import asdict, replace

from . import condition, examples, parser
from .browser import Blocked
from .config import ItemConfig, Settings
from .market import MarketBook, group_key, variant_label
from .models import Listing
from .scoring import assess, margin_for, sell_price_for
from .storage import ResultsLog, SeenStore
from .urls import build_search_url, prepare_url

log = logging.getLogger("resell_radar.engine")

# Заголовки, которые точно не устройство целиком: аксессуары, запчасти, объявления о покупке.
JUNK_TITLE = re.compile(
    r"чехол|бампер|защитн|плёнк|пленк|кабель|держател|подставк|корпус|шлейф|"
    r"модуль|аккумулятор\b|запчаст|аренда|прокат|муляж|макет|куплю|скупка|выкуп", re.I)

MAX_FAVORITES_PER_CYCLE = 15   # лишних кликов под аккаунтом не делаем


class Engine:
    def __init__(self, settings: Settings, browser, market: MarketBook | None = None,
                 seen: SeenStore | None = None, results: ResultsLog | None = None, sleep=time.sleep):
        self.s = settings
        self.browser = browser
        data = Path(settings.data_dir)
        self.market = market or MarketBook(data / "market.json", settings.market_window_days,
                                           settings.min_group_size)
        self.seen = seen or SeenStore(data / "seen.json")
        self.results = results or ResultsLog(data / "results.csv")
        self.sleep = sleep
        self._examples_path = data / "examples.json"
        self._examples: dict[str, dict] = self._load_examples()
        self._favorites_this_cycle = 0
        self.reasons: Counter = Counter()

    # --- поиск по образцу ------------------------------------------------
    def _load_examples(self) -> dict:
        try:
            return json.loads(self._examples_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _resolve(self, item: ItemConfig) -> ItemConfig:
        """Для устройства «по образцу» выводит запрос и фильтры из заголовка объявления-образца."""
        if not item.example:
            return item
        fields = self._examples.get(item.example)
        if fields is None:
            title = ""
            html = self.browser.get_html(item.example, parser.DESCRIPTION_SELECTOR)   # может бросить Blocked
            self._pause()
            if html:
                title = parser.parse_item(html).title
            derived = examples.derive(title or examples.slug_title(item.example), item.example)
            fields = {k: v for k, v in asdict(derived).items() if k != "name"}
            if title and fields["query"]:      # кэшируем, только если заголовок взят со страницы
                self._examples[item.example] = fields
                self._examples_path.parent.mkdir(parents=True, exist_ok=True)
                self._examples_path.write_text(json.dumps(self._examples, ensure_ascii=False), encoding="utf-8")
                log.info("%s: по образцу «%s» ищем «%s»", item.name, title, fields["query"])
        return replace(item, query=fields["query"] or item.query, match=fields["match"],
                       exclude=fields["exclude"], category=fields["category"] or item.category,
                       variant=fields["variant"], url="")

    # --- вспомогательное -------------------------------------------------
    def search_url(self, item: ItemConfig) -> str:
        if item.url:                       # ссылка со всеми фильтрами пользователя
            return prepare_url(item.url, self.s.seller)
        url = build_search_url(self.s.region, item.category, item.query, item.min_price)
        return prepare_url(url, self.s.seller)

    @staticmethod
    def title_ok(item: ItemConfig, title: str) -> bool:
        t = title.lower()
        if JUNK_TITLE.search(t):
            return False
        if item.brand and not re.search(item.brand, t):
            return False
        if item.match and not re.search(item.match, t):
            return False
        if item.exclude and re.search(item.exclude, t):
            return False
        return True

    def _pause(self):
        self.sleep(random.uniform(4, 8))

    # --- основной цикл ---------------------------------------------------
    def run_cycle(self) -> bool:
        """Вернуть True, если Avito попросил проверку."""
        blocked = False
        self._favorites_this_cycle = 0
        try:
            for item in self.s.items:
                try:
                    item = self._resolve(item)
                    html = self.browser.get_html(self.search_url(item), parser.CARD_SELECTOR)
                except Blocked:
                    blocked = True
                    break
                if html is None:
                    log.warning("%s: карточки не найдены (пусто или сменилась вёрстка)", item.name)
                    continue
                found = parser.parse_search(html)
                listings = [l for l in found if self.title_ok(item, l.title)]
                self._observe(item, listings)
                self.reasons = Counter()
                stop = self._review_all(item, listings)
                cheapest = f", самое дешёвое {min(l.price for l in listings)} ₽ при лимите " \
                           f"{min(self.s.max_buy, item.max_buy or self.s.max_buy)} ₽" if listings else ""
                log.info("%s: на странице %d, подошло по названию %d%s. Итог: %s", item.name, len(found),
                         len(listings), cheapest,
                         ", ".join(f"{k} {v}" for k, v in self.reasons.items()) or "нечего разбирать")
                if stop:
                    blocked = True
                    break
                self._pause()
        finally:
            self.market.prune()
            self.market.save()
            self.seen.save()
        return blocked

    def _observe(self, item: ItemConfig, listings: list[Listing]):
        """Копим цены для оценки рынка. Дефектные устройства рынок не искажают."""
        for l in listings:
            cond = condition.analyze(f"{l.title} {l.snippet}")
            if cond.defects or cond.is_fake:
                continue
            variant = variant_label(item.variant, f"{l.title} {l.snippet}")
            self.market.observe(group_key(item.name, variant), l.id, l.price)

    def _review_all(self, item: ItemConfig, listings: list[Listing]) -> bool:
        limit = min(self.s.max_buy, item.max_buy or self.s.max_buy)
        for l in listings:
            if l.price > limit or l.price < item.min_price:
                self.reasons["вне лимита цены"] += 1
                continue
            if not self.seen.needs_review(l.id, l.price):
                self.reasons["уже разобрано"] += 1
                continue
            if self._review(item, l):
                return True
        return False

    def _review(self, item: ItemConfig, l: Listing) -> bool:
        """Разобрать одно объявление. True, если Avito просит проверку."""
        variant = variant_label(item.variant, f"{l.title} {l.snippet}")
        group = group_key(item.name, variant)
        stats = self.market.stats(item.name, variant)
        sell = sell_price_for(item, stats, self.s)
        if sell is None:
            self.reasons["рынок ещё не оценён"] += 1
            return False  # рынок ещё не известен, разберём в следующем цикле
        pre_margin, _ = margin_for(l.price, sell, self.s)
        if pre_margin < self.s.min_margin:
            self.reasons["мало прибыли"] += 1
            self.seen.mark(l.id, l.price, "low-margin")
            return False

        # Кандидат: открываем объявление и читаем описание.
        try:
            html = self.browser.get_html(l.url, parser.DESCRIPTION_SELECTOR)
        except Blocked:
            return True
        self._pause()
        page = parser.parse_item(html) if html else None
        description = page.description if page else None

        cond = condition.analyze(" ".join([l.title, l.snippet, description or ""]))
        decision = condition.decide(cond, self.s.repairable, self.s.repair_costs)
        if not decision.accepted:
            log.info("Пропуск %s: %s", l.id, "; ".join(decision.reasons))
            self.reasons["дефект / не ваш ремонт"] += 1
            self.seen.mark(l.id, l.price, "rejected")
            return False

        a = assess(l, item, group, stats, cond, decision, description, self.s)
        if a is None or a.margin < self.s.min_margin or a.risk > self.s.risk_max:
            self.reasons["риск или прибыль после проверки"] += 1
            self.seen.mark(l.id, l.price, "skip")
            return False

        if self.s.favorite and self._favorites_this_cycle < MAX_FAVORITES_PER_CYCLE:
            try:
                status = self.browser.add_favorite(l.url)
            except Blocked:
                return True
            self._favorites_this_cycle += 1
            self._pause()
            if status in ("added", "already"):
                log.info("В избранное: %s (%s)", l.title, l.url)
            else:
                self._favorite_failed(status, l)
        self.results.append(a)
        self.reasons["найдено"] += 1
        self.seen.mark(l.id, l.price, "sent")
        return False

    def _favorite_failed(self, status: str, l: Listing) -> None:
        hint = ("кнопка не найдена, возможно, сменилась вёрстка (список FAVORITE_SELECTORS в browser.py)"
                if status == "not_found"
                else "клик не сработал, вероятно, не выполнен вход в Avito (запустите команду login)")
        log.warning("Не удалось добавить в избранное %s: %s. Находка сохранена в таблицу", l.url, hint)
