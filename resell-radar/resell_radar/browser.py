"""Chrome через Playwright: открываем страницы как обычный пользователь.

По умолчанию Chrome работает скрыто (без окна). Мы не обходим защиту Avito и не решаем капчу
автоматически: если Avito просит проверку, программа на время показывает окно, ты проходишь
проверку руками, и окно снова скрывается. Профиль Chrome сохраняется в папке, поэтому куки
(в том числе вход в аккаунт) живут между запусками.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

log = logging.getLogger("resell_radar.browser")

BLOCK_MARKERS = ("captcha", "доступ ограничен", "проблема с ip", "firewall",
                 "подтвердите, что вы не робот")


# Кнопка «в избранное» на странице объявления. Avito меняет вёрстку, поэтому
# перечислено несколько вариантов. Если кнопка не найдена, правьте этот список.
FAVORITE_SELECTORS = (
    '[data-marker="item-view/favorite-button"]',
    '[data-marker="favorite-button"]',
    'button[aria-label*="збранн"]',
)


class Blocked(Exception):
    """Avito показал капчу или ограничил доступ."""


def favorite_active(label: str, pressed: str | None = None) -> bool:
    """Уже ли объявление в избранном, по подписи кнопки и aria-pressed."""
    if pressed == "true":
        return True
    low = (label or "").lower()
    return "удалить из избранного" in low or "в избранном" in low


class ChromeBrowser:
    def __init__(self, profile_dir: str = "chrome_profile", headless: bool = True):
        self.profile_dir = str(Path(profile_dir).resolve())
        self.headless = headless
        self._pw = None
        self._ctx = None
        self._page = None
        self._last_url = ""

    def _page_ready(self):
        if self._page is not None and not self._page.is_closed():
            return self._page
        self.close()
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._ctx = self._pw.chromium.launch_persistent_context(
            user_data_dir=self.profile_dir, channel="chrome", headless=self.headless,
            locale="ru-RU", viewport={"width": 1280, "height": 900},
            # Avito должен видеть обычный IP, поэтому системный прокси/VPN не используем.
            args=["--no-proxy-server", "--start-minimized"],
        )
        self._page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
        return self._page

    def get_html(self, url: str, wait_selector: str, timeout_ms: int = 25000) -> str | None:
        """HTML страницы после появления wait_selector.

        None: страница открылась, но нужного элемента нет (пустая выдача, сменилась вёрстка).
        Blocked: Avito просит проверку.
        """
        try:
            page = self._page_ready()
            self._last_url = url
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            try:
                page.wait_for_selector(wait_selector, timeout=timeout_ms)
            except Exception:
                text = (page.title() + " " + page.content()[:6000]).lower()
                if any(marker in text for marker in BLOCK_MARKERS):
                    raise Blocked("Avito просит проверку")
                return None
            return page.content()
        except Blocked:
            raise
        except Exception as exc:
            log.warning("ошибка браузера: %s", exc)
            self.close()  # закрыли окно или завис: в следующий раз откроем заново
            return None

    def let_human_check(self, timeout_s: int = 600) -> bool:
        """Показать окно Chrome, пока человек проходит проверку Avito, потом вернуть прежний режим.

        True, если проверка пройдена (страница больше не похожа на капчу).
        """
        was_headless = self.headless
        self.close()
        self.headless = False
        passed = False
        try:
            page = self._page_ready()
            page.goto(self._last_url or "https://www.avito.ru/", wait_until="domcontentloaded", timeout=60000)
            deadline = time.time() + timeout_s
            while time.time() < deadline:
                page.wait_for_timeout(3000)
                text = (page.title() + " " + page.content()[:6000]).lower()
                if not any(marker in text for marker in BLOCK_MARKERS):
                    passed = True
                    break
        except Exception as exc:
            log.warning("не удалось показать окно для проверки: %s", exc)
        finally:
            self.close()
            self.headless = was_headless
        return passed

    def open(self, url: str) -> None:
        """Просто открыть страницу в окне Chrome (например, чтобы войти в аккаунт)."""
        self._page_ready().goto(url, wait_until="domcontentloaded", timeout=60000)

    def add_favorite(self, url: str) -> str:
        """Нажать «в избранное» на странице объявления.

        Возвращает: added, already, not_found (кнопки нет, возможно сменилась вёрстка)
        или unconfirmed (нажали, но состояние не изменилось: вероятно, не выполнен вход).
        Blocked: Avito просит проверку.
        """
        try:
            page = self._page_ready()
            if page.url.split("?")[0] != url.split("?")[0]:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
            union = ", ".join(FAVORITE_SELECTORS)
            try:
                page.wait_for_selector(union, timeout=12000)
            except Exception:
                text = (page.title() + " " + page.content()[:6000]).lower()
                if any(marker in text for marker in BLOCK_MARKERS):
                    raise Blocked("Avito просит проверку")
                return "not_found"
            button = page.locator(union).first

            def state() -> bool:
                label = button.get_attribute("aria-label") or button.get_attribute("title") or button.inner_text()
                return favorite_active(label, button.get_attribute("aria-pressed"))

            if state():
                return "already"
            button.click(timeout=8000)
            page.wait_for_timeout(1500)
            return "added" if state() else "unconfirmed"
        except Blocked:
            raise
        except Exception as exc:
            log.warning("не удалось нажать «в избранное»: %s", exc)
            return "not_found"

    def close(self):
        for obj, method in ((self._ctx, "close"), (self._pw, "stop")):
            try:
                if obj:
                    getattr(obj, method)()
            except Exception:
                pass
        self._pw = self._ctx = self._page = None
