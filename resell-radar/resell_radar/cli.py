"""Командная строка: setup, run, once, top, export, login, debug."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import __version__, wizard
from . import config as cfg
from .app import run_forever
from .browser import ChromeBrowser
from .engine import Engine
from .storage import ResultsLog


def _load_or_exit(path: Path) -> cfg.Settings:
    if not Path(path).exists():
        sys.exit(f"Нет файла {path}. Сначала запусти настройку: python -m resell_radar setup")
    s = cfg.load(path)
    if s.max_buy <= 0:
        sys.exit("Не задан лимит закупки (max_buy). Запусти настройку: python -m resell_radar setup")
    if not s.items:
        sys.exit("В настройках нет моделей для поиска. Запусти: python -m resell_radar setup")
    return s


def cmd_top(s: cfg.Settings, limit: int = 15) -> None:
    rows = ResultsLog(Path(s.data_dir) / "results.csv").rows()
    if not rows:
        print("Пока ничего не найдено.")
        return
    rows.sort(key=lambda r: int(r["margin"]), reverse=True)
    print(f"{'Модель':<30}{'Цена':>8}{'Маржа':>8}{'Риск':>6}  Ссылка")
    for r in rows[:limit]:
        print(f"{r['item'][:29]:<30}{r['price']:>8}{r['margin']:>8}{r['risk']:>6}  {r['url']}")


def cmd_debug(s: cfg.Settings) -> None:
    """Сохранить страницу выдачи и показать, что из неё понял разбор. Для поиска причин."""
    from . import parser as page_parser
    from .engine import Engine
    out = Path(s.data_dir) / "debug"
    out.mkdir(parents=True, exist_ok=True)
    browser = ChromeBrowser(s.profile_dir, False)
    try:
        engine = Engine(s, browser)
        for n, item in enumerate(s.items, 1):
            url = engine.search_url(item)
            print(f"\n[{item.name}] {url}")
            html = browser.get_html(url, page_parser.CARD_SELECTOR)
            if html is None:
                print("  Карточки не найдены (пустая выдача, капча или сменилась вёрстка).")
                html = ""
            (out / f"search_{n}.html").write_text(html, encoding="utf-8")
            listings = page_parser.parse_search(html)
            ok = [l for l in listings if engine.title_ok(item, l.title)]
            print(f"  Объявлений разобрано: {len(listings)}, подошло по названию: {len(ok)}")
            for l in listings[:8]:
                mark = "+" if l in ok else "-"
                print(f"   {mark} {l.price:>7} ₽  {l.title[:60]}")
            if n >= 3:
                break
    finally:
        browser.close()
    print(f"\nСтраницы сохранены в {out}. Если разбор пустой, пришлите файл search_1.html.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="resell_radar", description="Поиск выгодных объявлений на Avito для перекупов")
    parser.add_argument("command", choices=["setup", "run", "once", "top", "login", "debug", "export"])
    parser.add_argument("--config", default=str(cfg.CONFIG_PATH), help="путь к config.toml")
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    path = Path(args.config)

    if args.command == "setup":
        wizard.run(path)
        return
    s = _load_or_exit(path)
    if args.command == "export":
        results = ResultsLog(Path(s.data_dir) / "results.csv")
        ok = results.export_xlsx()
        print(f"Таблица: {results.xlsx_path}" if ok else "Не удалось записать таблицу: закройте её в Excel и повторите.")
    elif args.command == "login":
        browser = ChromeBrowser(s.profile_dir, False)
        try:
            browser.open("https://www.avito.ru/")
            input("Войдите в свой аккаунт Avito в открытом окне Chrome, затем нажмите Enter здесь: ")
        finally:
            browser.close()
    elif args.command == "debug":
        cmd_debug(s)
    elif args.command == "top":
        cmd_top(s)
    elif args.command == "once":
        browser = ChromeBrowser(s.profile_dir, s.headless)
        try:
            engine = Engine(s, browser)
            blocked = engine.run_cycle()
            print("Avito просит проверку: запустите run.bat, там окно появится само." if blocked else f"Цикл завершён. Таблица: {engine.results.xlsx_path}")
        finally:
            browser.close()
    elif args.command == "run":
        run_forever(s)


if __name__ == "__main__":
    main()
