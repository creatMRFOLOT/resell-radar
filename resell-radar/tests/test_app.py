import unittest

from resell_radar.app import run_forever
from resell_radar.config import Settings


class FakeEngine:
    def __init__(self, blocked_cycles, human_passes):
        self.blocked_cycles = list(blocked_cycles)
        self.cycles = 0
        outer = self

        class Browser:
            checks = 0

            def let_human_check(self):
                Browser.checks += 1
                return human_passes
        self.browser = Browser()
        self.checks = Browser
        self.results = type("R", (), {"xlsx_path": "x.xlsx", "export_xlsx": lambda self: True})()

    def run_cycle(self):
        self.cycles += 1
        return self.blocked_cycles.pop(0) if self.blocked_cycles else False


class AppTests(unittest.TestCase):
    def test_captcha_shows_window_and_continues_without_long_pause(self):
        waits = []
        engine = FakeEngine([True, False], human_passes=True)
        run_forever(Settings(headless=True), engine, sleep=waits.append, max_cycles=3)
        self.assertEqual(engine.checks.checks, 1)
        self.assertEqual(waits, [Settings().check_every_min * 60])      # длинной паузы после проверки нет

    def test_unsolved_check_waits(self):
        waits = []
        engine = FakeEngine([True], human_passes=False)
        run_forever(Settings(headless=True), engine, sleep=waits.append, max_cycles=1)
        self.assertEqual(engine.cycles, 1)

    def test_visible_mode_does_not_reopen_window(self):
        waits = []
        engine = FakeEngine([True, False], human_passes=True)
        run_forever(Settings(headless=False), engine, sleep=waits.append, max_cycles=2)
        self.assertEqual(engine.checks.checks, 0)
        self.assertEqual(waits[0], Settings().block_pause_min * 60)


if __name__ == "__main__":
    unittest.main()
