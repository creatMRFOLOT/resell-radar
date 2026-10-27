import unittest
from datetime import datetime, timedelta

from resell_radar import condition as c
from resell_radar import market as m
from resell_radar import scoring as s
from resell_radar.config import ItemConfig, Settings
from resell_radar.models import Listing


class StorageTests(unittest.TestCase):
    def test_parse(self):
        cases = {
            "Samsung Galaxy S22, 8/128 ГБ, SIM+eSIM": 128,
            "Pixel 8 128gb": 128,
            "iPhone 13 256 ГБ": 256,
            "12/512 gb": 512,
            "Nintendo Switch Lite 1 ТБ карта": 1024,
            "Samsung Galaxy S22 8 ГБ ОЗУ 128 ГБ": 128,
            "Просто телефон": None,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(m.storage_gb(text), expected)


class VariantTests(unittest.TestCase):
    def test_labels(self):
        self.assertEqual(m.variant_label("storage", "Pixel 8, 8/128 ГБ"), "128 ГБ")
        self.assertIsNone(m.variant_label("storage", "Pixel 8 без памяти"))
        self.assertEqual(m.variant_label("none", "что угодно"), m.ALL)
        self.assertEqual(m.variant_label(r"(digital|цифров\w*|с приводом)", "PS5 Digital Edition"), "digital")
        self.assertIsNone(m.variant_label(r"(digital)", "PS5 обычная"))
        self.assertIsNone(m.variant_label("([", "битая регулярка"))

    def test_group_keys(self):
        self.assertEqual(m.group_key("S22", 128), "S22 | 128 ГБ")
        self.assertEqual(m.group_key("S22", "128 ГБ"), "S22 | 128 ГБ")
        self.assertEqual(m.group_key("S22", None), "S22 | ?")

    def test_whole_model_group_has_no_approximate_fallback(self):
        book = m.MarketBook(min_size=3)
        now = datetime(2026, 10, 25)
        for i, p in enumerate([20000, 21000, 22000]):
            book.observe(m.group_key("AirPods Pro", m.ALL), f"a{i}", p, now)
        st = book.stats("AirPods Pro", m.ALL, now)
        self.assertFalse(st.approx)
        self.assertEqual(st.median, 21000)
        self.assertIsNone(book.stats("AirPods Pro 2", m.ALL, now))


class StatsTests(unittest.TestCase):
    def test_too_few(self):
        self.assertIsNone(m.trimmed_stats("g", [100, 200]))

    def test_outliers_dropped(self):
        prices = [20000, 21000, 19500, 20500, 20200, 3000, 60000]
        st = m.trimmed_stats("g", prices)
        self.assertEqual(st.count, 7)
        self.assertEqual(st.used, 5)
        self.assertTrue(19500 <= st.median <= 21000)
        self.assertEqual(st.low, 19500)
        self.assertEqual(st.high, 21000)


class MarketBookTests(unittest.TestCase):
    def test_groups_by_storage(self):
        book = m.MarketBook(min_size=3)
        now = datetime(2026, 10, 25, 12, 0)
        for i, p in enumerate([20000, 21000, 20500]):
            book.observe(m.group_key("S22", 128), f"a{i}", p, now)
        for i, p in enumerate([25000, 26000, 25500]):
            book.observe(m.group_key("S22", 256), f"b{i}", p, now)
        self.assertEqual(book.stats("S22", 128, now).median, 20500)
        self.assertEqual(book.stats("S22", 256, now).median, 25500)

    def test_fallback_to_whole_model_when_storage_unknown(self):
        book = m.MarketBook(min_size=3)
        now = datetime(2026, 10, 25)
        for i, p in enumerate([20000, 21000, 22000]):
            book.observe(m.group_key("S22", 128), f"a{i}", p, now)
        st = book.stats("S22", None, now)
        self.assertTrue(st.approx)

    def test_old_observations_ignored_and_pruned(self):
        book = m.MarketBook(window_days=14, min_size=3)
        now = datetime(2026, 10, 25)
        old = now - timedelta(days=30)
        for i, p in enumerate([20000, 21000, 22000]):
            book.observe(m.group_key("S22", 128), f"o{i}", p, old)
        self.assertIsNone(book.stats("S22", 128, now))
        book.prune(now)
        self.assertEqual(book.data, {})

    def test_persistence(self):
        import tempfile, pathlib
        path = pathlib.Path(tempfile.mkdtemp()) / "m.json"
        book = m.MarketBook(path, min_size=3)
        for i, p in enumerate([20000, 21000, 22000]):
            book.observe(m.group_key("S22", 128), f"a{i}", p)
        book.save()
        again = m.MarketBook(path, min_size=3)
        self.assertEqual(again.stats("S22", 128).median, 21000)


class ScoringTests(unittest.TestCase):
    settings = Settings(sell_basis="median", sell_discount_pct=5.0)
    item = ItemConfig("S22", "Samsung Galaxy S22")

    def stats(self, median=20000, used=10, approx=False):
        return m.Stats("S22 | 128 ГБ", used + 2, used, median - 1500, median - 700,
                       median, median + 700, median + 1500, approx)

    def listing(self, price):
        return Listing("1", "Samsung Galaxy S22", price, "https://www.avito.ru/x_1")

    def test_margin_uses_commission_on_sale_price(self):
        margin, roi = s.margin_for(15000, 19000, self.settings)
        self.assertEqual(margin, 1910)       # 19000 * 0.89 - 15000
        self.assertAlmostEqual(roi, 12.7, 1)

    def test_repair_cost_reduces_margin(self):
        margin, _ = s.margin_for(12000, 19000, self.settings, repair_cost=5000)
        self.assertEqual(margin, -90)         # 19000 * 0.89 - 12000 - 5000

    def test_sell_price_prefers_user_value(self):
        item = ItemConfig("S22", "q", sell_price=22000)
        self.assertEqual(s.sell_price_for(item, self.stats(), self.settings), 22000)
        self.assertEqual(s.sell_price_for(self.item, self.stats(20000), self.settings), 19000)
        self.assertIsNone(s.sell_price_for(self.item, None, self.settings))

    def test_default_sell_price_is_cautious_q1(self):
        st = Settings()
        self.assertEqual(st.sell_basis, "q1")
        self.assertEqual(s.sell_price_for(self.item, self.stats(20000), st), 19300)   # q1 = 20000 - 700
        median = Settings(sell_basis="median", sell_discount_pct=0.0)
        self.assertEqual(s.sell_price_for(self.item, self.stats(20000), median), 20000)

    def test_risk_grows_when_price_too_low(self):
        normal, _ = s.risk_score(18000, self.stats(), c.analyze("Хорошее состояние, комплект, коробка, чек"),
                                 "Хорошее состояние, комплект, коробка, чек, гарантия магазина", [])
        cheap, reasons = s.risk_score(9000, self.stats(), None,
                                      "Хорошее состояние, комплект, коробка, чек, гарантия магазина", [])
        self.assertLess(normal, 25)
        self.assertGreaterEqual(cheap, 45)
        self.assertTrue(any("ниже рынка" in r for r in reasons))

    def test_empty_description_adds_risk(self):
        a, _ = s.risk_score(18000, self.stats(), None, "Продам", [])
        b, _ = s.risk_score(18000, self.stats(), None,
                            "Отличное состояние, полный комплект, коробка и документы есть", [])
        self.assertGreater(a, b)

    def test_full_assessment(self):
        cond = c.analyze("Идеальное состояние, АКБ 93%, полный комплект и коробка в наличии")
        decision = c.decide(cond, [], self.settings.repair_costs)
        a = s.assess(self.listing(14800), self.item, "S22 | 128 ГБ", self.stats(20000),
                     cond, decision, "Идеальное состояние, АКБ 93%, полный комплект и коробка в наличии",
                     self.settings)
        self.assertEqual(a.sell_price, 19000)
        self.assertEqual(a.margin, round(19000 * 0.89 - 14800))
        self.assertEqual(a.battery_pct, 93)
        self.assertAlmostEqual(a.below_pct, 26.0, 1)
        self.assertTrue(a.description_checked)

    def test_no_assessment_without_sell_price(self):
        a = s.assess(self.listing(14000), self.item, "g", None, None, None, None, self.settings)
        self.assertIsNone(a)


if __name__ == "__main__":
    unittest.main()
