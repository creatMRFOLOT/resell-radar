"""Мастер первой настройки: пользователь сам выбирает, что искать и что он умеет чинить.

bot-помощник: собирает кандидатов в таблицу, а решение и проверку фото человек берёт на себя."""
from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

from . import config as cfg
from . import examples, presets, urls


def parse_selection(text: str, size: int) -> list[int]:
    """'1,3-5' -> [1, 3, 4, 5]; 'all' -> все; пустое -> []. Номера с единицы."""
    text = (text or "").strip().lower()
    if not text:
        return []
    if text in ("all", "все"):
        return list(range(1, size + 1))
    chosen: list[int] = []
    for part in re.split(r"[,\s]+", text):
        if not part:
            continue
        if "-" in part:
            a, _, b = part.partition("-")
            if a.isdigit() and b.isdigit():
                chosen += range(int(a), int(b) + 1)
        elif part.isdigit():
            chosen.append(int(part))
    seen: list[int] = []
    for n in chosen:
        if 1 <= n <= size and n not in seen:
            seen.append(n)
    return seen


_words_to_regex = examples.words_to_regex


def run(path: Path = cfg.CONFIG_PATH, ask=input, say=print) -> cfg.Settings:
    s = cfg.load(path) if Path(path).exists() else cfg.Settings()

    def prompt(text: str, default="") -> str:
        shown = f" [{default}]" if default not in ("", None) else ""
        answer = ask(f"{text}{shown}: ").strip()
        return answer if answer else str(default)

    def prompt_int(text: str, default: int) -> int:
        while True:
            raw = prompt(text, default)
            try:
                return int(raw.replace(" ", ""))
            except ValueError:
                say("Нужно целое число.")

    def prompt_positive(text: str, default: int) -> int:
        """Обязательное число больше нуля: без своего лимита бот не запускается."""
        while True:
            value = prompt_int(text, default) if default > 0 else prompt_int(text, "")
            if value > 0:
                return value
            say("Нужно число больше нуля.")

    say("\n=== resell-radar: первая настройка ===\n")

    say("1/7. Находки. Все подходящие объявления записываются в таблицу Excel: data/results.xlsx")
    say("  (лучшие сверху, ссылка на объявление кликабельна, файл обновляется сам).")
    say("  Это помощник: он отбирает кандидатов, а смотреть фото и решать, брать ли, будешь ты.")
    say("  Дополнительно бот может класть их в избранное на Avito. Для этого нужен вход в аккаунт (login.bat).")
    s.favorite = _yes(prompt("Добавлять ещё и в избранное Avito? (да/нет)", "да" if s.favorite else "нет"))
    if s.favorite:
        say("  Перед запуском выполни login.bat и один раз войди в аккаунт в открывшемся окне Chrome.")

    say("\n2/7. Деньги.")
    say("  Лимиты зависят от вашего бюджета и товара, поэтому у них нет значений по умолчанию.")
    s.max_buy = prompt_positive("Максимальная цена закупки одного устройства, ₽ (всё, что дороже, бот не покажет)", s.max_buy)
    s.min_margin = prompt_int("Минимальная чистая прибыль с одной сделки, ₽ (с учётом комиссии и ремонта)", s.min_margin)
    say("  Как оценивать цену, за которую ты потом продашь?")
    say("    1. Осторожно: нижняя четверть цен рынка (рекомендую: в объявлениях цены завышены, покупатели торгуются)")
    say("    2. По медиане рынка со скидкой на торг 5%")
    if prompt("  Номер", "2" if s.sell_basis == "median" else "1") == "2":
        s.sell_basis, s.sell_discount_pct = "median", 5.0
    else:
        s.sell_basis, s.sell_discount_pct = "q1", 0.0
    say("  Знаешь свою цену продажи для конкретной модели? Впиши sell_price в config.toml.")

    say("\n3/7. Продавцы.")
    say("    1. Только частные лица (рекомендую: торгуются, реже подделки и «перебитые» устройства)")
    say("    2. Все")
    say("    3. Только магазины и компании")
    seller_default = {"private": "1", "any": "2", "company": "3"}.get(s.seller, "1")
    s.seller = {"1": "private", "2": "any", "3": "company"}.get(prompt("  Номер", seller_default), "private")

    say("\n4/7. Состояние. Что ты умеешь и готов чинить?")
    keys = list(cfg.REPAIR_CATEGORIES)
    for n, key in enumerate(keys, 1):
        say(f"  {n}. {cfg.REPAIR_CATEGORIES[key]}")
    say("  Enter, если нужны только целые, рабочие устройства.")
    picked = parse_selection(prompt("Номера через запятую", ""), len(keys))
    s.repairable = [keys[n - 1] for n in picked]
    for key in s.repairable:
        s.repair_costs[key] = prompt_int(
            f"  Сколько в среднем стоит у тебя ремонт: {cfg.REPAIR_CATEGORIES[key].split(' (')[0]}, ₽",
            s.repair_costs.get(key, 0))

    say("\n5/7. Где искать?")
    say("  Enter = вся Россия. Или вставь название региона/города из ссылки Avito,")
    say("  например: ekaterinburg, sverdlovskaya_oblast, moskva")
    s.region = prompt("Регион", s.region)

    say("\n6/7. Что искать? Выбери готовые модели: телефоны, консоли, планшеты, ноутбуки, наушники.")
    flat: list[cfg.ItemConfig] = []
    for group, items in presets.groups().items():
        say(f"  {group}:")
        for it in items:
            flat.append(it)
            say(f"    {len(flat):>3}. {it.name}")
    say("  Пример ответа: 1-6, 20, 21   или   all   (Enter, если нужны только свои устройства)")
    chosen = parse_selection(prompt("Номера", ""), len(flat))
    s.items = [replace(flat[n - 1]) for n in chosen]
    say("  Можно добавить любое своё устройство.")
    while True:
        how = prompt("Добавить своё? 1 = по ссылке Avito (на поиск или на объявление-пример), 2 = по названию, Enter = хватит", "")
        if how == "1":
            item = _item_from_url(prompt, say)
        elif how == "2":
            item = _item_by_name(prompt, prompt_int, say)
        else:
            break
        if item:
            s.items.append(item)
    if not s.items:
        say("Ничего не выбрано. Добавлю Samsung Galaxy S22 для примера.")
        s.items = [replace(presets.all_presets()[0])]

    say("\n7/7. Как часто проверять?")
    s.check_every_min = prompt_int("Раз в сколько минут (рекомендую 15 и больше)", s.check_every_min)

    say("\nОкно Chrome. Скрыто работает незаметно, окно появится само, только если Avito попросит проверку.")
    s.headless = _yes(prompt("Скрывать окно Chrome? (да/нет)", "да" if s.headless else "нет"))

    cfg.save(s, path)
    say(f"\nГотово. Настройки сохранены в {path}. Запуск: команда `run` или файл run.bat.")
    say("Результаты: data/results.xlsx (открой в Excel, лучшие варианты сверху).")
    if s.favorite:
        say("Не забудь сначала login.bat: без входа в аккаунт избранное не заработает.")
    say("Если фильтр по типу продавца не сработает: выбери нужные фильтры на сайте Avito, скопируй ссылку")
    say("из адресной строки и добавь устройство «по ссылке». Параметры из неё программа не меняет.")
    return s


def _wants_memory_split(url_or_category: str) -> bool:
    """Телефоны, планшеты и ноутбуки: цена сильно зависит от памяти."""
    return any(part in url_or_category for part in ("telefony", "planshety", "noutbuki"))


def _yes(text: str) -> bool:
    return text.strip().lower() in ("y", "yes", "д", "да", "1")


def _item_from_example(url: str, prompt, say) -> cfg.ItemConfig:
    """Ссылка на объявление-образец: бот сам найдёт похожие. Запрос уточнится по заголовку на странице."""
    d = examples.derive(examples.slug_title(url), url)
    say(f"  Образец понят как «{d.query or '?'}». Похожие объявления бот будет искать сам.")
    name = prompt("  Название", d.name)
    return cfg.ItemConfig(name, d.query or name, category=d.category, match=d.match, exclude=d.exclude,
                          example=url.strip(), variant=d.variant)


def _item_from_url(prompt, say) -> cfg.ItemConfig | None:
    url = prompt("  Ссылка Avito: на объявление-образец (найдём похожие) или на поиск с твоими фильтрами", "")
    if not urls.is_avito_url(url):
        say("  Это не ссылка avito.ru, пропускаю.")
        return None
    if examples.is_listing_url(url):
        return _item_from_example(url, prompt, say)
    query = urls.query_from_url(url)
    name = prompt("  Название", query or "Свой поиск")
    split = prompt("  Различать цены по объёму памяти? (да/нет)", "да" if _wants_memory_split(url) else "нет")
    return cfg.ItemConfig(name, query or name, category="", url=url.strip(),
                          variant="storage" if _yes(split) else "none")


def _item_by_name(prompt, prompt_int, say) -> cfg.ItemConfig | None:
    name = prompt("  Название устройства", "")
    if not name:
        return None
    query = prompt("  Что вводить в поиск Avito", name)
    say("  Раздел Avito:")
    for n, (title, _slug) in enumerate(presets.CATEGORIES, 1):
        say(f"    {n}. {title}")
    picked = parse_selection(prompt("  Номер раздела", "1"), len(presets.CATEGORIES))
    category = presets.CATEGORIES[(picked[0] if picked else 1) - 1][1]
    words = prompt("  Слова, которые обязаны быть в заголовке (через пробел, Enter = любые)", "")
    min_price = prompt_int("  Минимальная цена, ниже это мусор, ₽", 0)
    split = prompt("  Различать цены по объёму памяти? (да/нет)", "да" if _wants_memory_split(category) else "нет")
    return cfg.ItemConfig(name, query, category=category, match=_words_to_regex(words),
                          min_price=min_price, variant="storage" if _yes(split) else "none")
