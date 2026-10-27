"""Запуск мониторинга в вечном цикле."""
from __future__ import annotations

import logging
import time

from .browser import ChromeBrowser
from .config import Settings
from .engine import Engine

log = logging.getLogger("resell_radar.app")


def run_forever(settings: Settings, engine: Engine | None = None,
                sleep=time.sleep, max_cycles: int | None = None) -> None:
    browser = None
    if engine is None:
        browser = ChromeBrowser(settings.profile_dir, settings.headless)
        engine = Engine(settings, browser)
    mode = "только целые" if settings.only_working else "можно с ремонтом: " + ", ".join(settings.repairable)
    log.info("resell-radar запущен. Моделей: %d. Состояние: %s. Таблица: %s",
             len(settings.items), mode, engine.results.xlsx_path)
    engine.results.export_xlsx()           # пустая таблица сразу, чтобы было видно, куда пойдут находки
    cycles = 0
    try:
        while True:
            blocked = engine.run_cycle()
            if blocked:
                helper = getattr(engine.browser, "let_human_check", None)
                if helper and settings.headless:
                    log.warning("Avito просит проверку. Открываю окно Chrome: пройдите её, окно скроется само.")
                    if helper():
                        log.info("Проверка пройдена, продолжаю.")
                        cycles += 1
                        if max_cycles and cycles >= max_cycles:
                            break
                        continue
                log.error("Avito показал проверку. Следующая попытка через %s мин.", settings.block_pause_min)
                wait = settings.block_pause_min * 60
            else:
                wait = settings.check_every_min * 60
            cycles += 1
            if max_cycles and cycles >= max_cycles:
                break
            log.info("Следующая проверка через %d мин.", round(wait / 60))
            sleep(wait)
    except KeyboardInterrupt:
        pass
    finally:
        if browser:
            browser.close()
