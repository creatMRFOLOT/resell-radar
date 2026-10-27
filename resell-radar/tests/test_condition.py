import unittest

from resell_radar import condition as c
from resell_radar.config import DEFAULT_REPAIR_COSTS


class AnalyzeTests(unittest.TestCase):
    def cats(self, text):
        return c.analyze(text).defects

    def test_clean_descriptions(self):
        clean = [
            "Состояние идеал, трещин нет, без царапин, не греется",
            "Не вскрывался, в ремонте не был",
            "Продаю, никогда не падал, комплект полный",
            "АКБ 91%, всё работает, коробка, гарантия",
            "Сколов и трещин нет, отличное состояние",
            "Экран без трещин и полос",
            "Идеальное состояние, ни разу не ремонтировался",
        ]
        for text in clean:
            with self.subTest(text=text):
                self.assertEqual(self.cats(text), set())

    def test_defects_by_category(self):
        cases = [
            ("Телефон периодически перезагружается сам", "board"),
            ("Телефон не включается", "board"),
            ("Не работает камера", "board"),
            ("Стики дрейфуют, дрейф слева", "board"),
            ("Экран с полосой, работает", "screen"),
            ("Разбит экран, остальное работает", "screen"),
            ("На дисплее пятна и выгорание", "screen"),
            ("Разбито заднее стекло", "back_glass"),
            ("Задняя крышка треснута", "back_glass"),
            ("Быстро разряжается, батарея вздутая", "battery"),
            ("Залит водой, после воды включается", "water"),
            ("Icloud заблокирован", "locked"),
            ("Google аккаунт не снят, FRP", "locked"),
            ("Телефон на запчасти", "board"),
        ]
        for text, cat in cases:
            with self.subTest(text=text):
                self.assertIn(cat, self.cats(text))

    def test_battery_percent(self):
        self.assertEqual(c.analyze("АКБ 92%").battery_pct, 92)
        self.assertEqual(c.analyze("аккумулятор: 87 %").battery_pct, 87)
        self.assertIsNone(c.analyze("без данных").battery_pct)
        self.assertIn("battery", self.cats("Батарея 68%, остальное хорошо"))
        self.assertNotIn("battery", self.cats("Батарея 82%"))

    def test_fake_and_soft_and_replaced(self):
        self.assertTrue(c.analyze("Копия, очень похож на оригинал").is_fake)
        self.assertTrue(c.analyze("Есть царапины на корпусе").soft)
        self.assertFalse(c.analyze("Царапин нет").soft)
        self.assertTrue(c.analyze("Менял экран в сервисе").replaced)
        self.assertTrue(c.analyze("Был в ремонте").replaced)


class DecideTests(unittest.TestCase):
    costs = DEFAULT_REPAIR_COSTS

    def test_only_working_rejects_any_defect(self):
        d = c.decide(c.analyze("Экран с полосой"), [], self.costs)
        self.assertFalse(d.accepted)
        self.assertIn("дефект: screen", d.reasons)

    def test_only_working_accepts_clean(self):
        d = c.decide(c.analyze("Идеальное состояние"), [], self.costs)
        self.assertTrue(d.accepted)
        self.assertEqual(d.repair_cost, 0)

    def test_repairer_accepts_what_he_can_fix(self):
        d = c.decide(c.analyze("Разбит экран"), ["screen"], self.costs)
        self.assertTrue(d.accepted)
        self.assertEqual(d.repairs, ["screen"])
        self.assertEqual(d.repair_cost, self.costs["screen"])

    def test_repairer_rejects_other_defects(self):
        d = c.decide(c.analyze("Разбит экран, не включается"), ["screen"], self.costs)
        self.assertFalse(d.accepted)
        self.assertIn("дефект: board", d.reasons)

    def test_costs_add_up(self):
        d = c.decide(c.analyze("Разбит экран, быстро разряжается"), ["screen", "battery"], self.costs)
        self.assertTrue(d.accepted)
        self.assertEqual(d.repair_cost, self.costs["screen"] + self.costs["battery"])

    def test_fake_always_rejected(self):
        d = c.decide(c.analyze("Реплика"), ["screen", "battery", "board"], self.costs)
        self.assertFalse(d.accepted)

    def test_locked_needs_explicit_choice(self):
        self.assertFalse(c.decide(c.analyze("iCloud"), ["screen"], self.costs).accepted)
        self.assertTrue(c.decide(c.analyze("iCloud"), ["locked"], self.costs).accepted)


if __name__ == "__main__":
    unittest.main()
