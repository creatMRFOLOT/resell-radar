import tempfile
import unittest
from pathlib import Path

from resell_radar import config as cfg
from resell_radar import presets, wizard


class ConfigTests(unittest.TestCase):
    def test_roundtrip_with_regex_and_unicode(self):
        path = Path(tempfile.mkdtemp()) / "config.toml"
        s = cfg.Settings(max_buy=17000, repairable=["screen", "battery"],
                         seller="company", favorite=True, sell_basis="median", sell_discount_pct=3.0,
                         items=presets.all_presets() + [
                             cfg.ItemConfig("Свой", "q", url="https://www.avito.ru/x?q=a&user=1",
                                            variant=r"(digital|с приводом)",
                                            example="https://www.avito.ru/x/telefony/a_4012345678")])
        s.repair_costs["screen"] = 4200
        cfg.save(s, path)
        back = cfg.load(path)
        self.assertEqual(back.items, s.items)          # регулярки с \ и кириллицей не испортились
        self.assertEqual(back.repairable, ["screen", "battery"])
        self.assertEqual(back.repair_costs["screen"], 4200)
        self.assertEqual(back.max_buy, 17000)
        self.assertTrue(back.favorite)
        self.assertEqual((back.seller, back.sell_basis, back.sell_discount_pct), ("company", "median", 3.0))
        self.assertEqual(back.items[-1].variant, r"(digital|с приводом)")

    def test_old_telegram_section_is_ignored(self):
        path = Path(tempfile.mkdtemp()) / "config.toml"
        path.write_text('[telegram]\ntoken = "x"\nchat_id = "1"\n[money]\nmax_buy = 15000\n', encoding="utf-8")
        self.assertEqual(cfg.load(path).max_buy, 15000)
        self.assertNotIn("telegram", cfg.dumps(cfg.load(path)).lower())

    def test_missing_file_gives_defaults(self):
        s = cfg.load(Path(tempfile.mkdtemp()) / "none.toml")
        self.assertEqual(s.max_buy, 0)               # своего лимита у проекта нет: его задаёт пользователь
        self.assertTrue(s.only_working)

    def test_defaults_are_cautious(self):
        s = cfg.Settings()
        self.assertEqual((s.seller, s.sell_basis, s.sell_discount_pct), ("private", "q1", 0.0))
        self.assertTrue(all(v == 0 for v in s.repair_costs.values()))   # чужие цены ремонта не выдумываем

    def test_invalid_choices_fall_back(self):
        path = Path(tempfile.mkdtemp()) / "config.toml"
        path.write_text('[monitor]\nseller = "bogus"\n[money]\nsell_basis = "max"\n', encoding="utf-8")
        s = cfg.load(path)
        self.assertEqual((s.seller, s.sell_basis), ("private", "q1"))

    def test_unknown_repair_keys_are_dropped(self):
        path = Path(tempfile.mkdtemp()) / "config.toml"
        path.write_text('[condition]\nrepairable = ["screen", "magic"]\n', encoding="utf-8")
        self.assertEqual(cfg.load(path).repairable, ["screen"])


class SelectionTests(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(wizard.parse_selection("1,3-5", 10), [1, 3, 4, 5])
        self.assertEqual(wizard.parse_selection("all", 3), [1, 2, 3])
        self.assertEqual(wizard.parse_selection("", 3), [])
        self.assertEqual(wizard.parse_selection("0, 2, 2, 99, x", 5), [2])


class WizardTests(unittest.TestCase):
    def run_wizard(self, answers):
        path = Path(tempfile.mkdtemp()) / "config.toml"
        it = iter(answers)
        said = []
        s = wizard.run(path, ask=lambda _prompt: next(it, ""), say=lambda *a, **k: said.append(" ".join(map(str, a))))
        self.said = said
        return s, cfg.load(path)

    def test_favorites_are_optional_and_off_by_default(self):
        s, back = self.run_wizard(["", "18000", "1500", "", "", "", "", "1", "", ""])
        self.assertFalse(back.favorite)

    def test_chrome_is_hidden_by_default_and_can_be_shown(self):
        _, back = self.run_wizard(["", "18000", "1500", "", "", "", "", "1", "", ""])
        self.assertTrue(back.headless)
        _, back = self.run_wizard(["", "18000", "1500", "", "", "", "", "1", "", "", "нет"])
        self.assertFalse(back.headless)

    def test_favorites_can_be_enabled(self):
        s, back = self.run_wizard(["да", "18000", "1500", "", "", "", "", "1", "", ""])
        self.assertTrue(back.favorite)
        self.assertTrue(any("login" in line for line in self.said))

    def test_repairer_setup(self):
        s, back = self.run_wizard([
            "",                           # избранное не нужно
            "20000", "2000", "2",         # деньги, оценка продажи по медиане
            "2",                          # продавцы: все
            "1,3", "4000", "1800",        # умеет чинить экран и аккумулятор + цены
            "ekaterinburg",               # регион
            "1-3", "",                    # модели, свою не добавляем
            "20",                         # интервал
        ])
        self.assertEqual(back.repairable, ["screen", "battery"])
        self.assertEqual(back.repair_costs["screen"], 4000)
        self.assertEqual(back.repair_costs["battery"], 1800)
        self.assertEqual(back.region, "ekaterinburg")
        self.assertEqual(len(back.items), 3)
        self.assertEqual(back.max_buy, 20000)
        self.assertEqual(back.check_every_min, 20)
        self.assertEqual((back.sell_basis, back.sell_discount_pct), ("median", 5.0))
        self.assertEqual(back.seller, "any")

    def test_defaults_private_sellers_cautious_price_only_working(self):
        s, back = self.run_wizard([
            "",
            "18000", "1500", "",          # базa продажи по умолчанию
            "",                           # продавцы по умолчанию
            "",                           # только целые
            "",                           # регион по умолчанию
            "1", "",                      # одна модель, больше не добавляем
            "",                           # интервал по умолчанию
        ])
        self.assertTrue(back.only_working)
        self.assertEqual(back.region, "rossiya")
        self.assertEqual(back.seller, "private")
        self.assertEqual((back.sell_basis, back.sell_discount_pct), ("q1", 0.0))

    def test_custom_item_by_name_in_other_category(self):
        s, back = self.run_wizard([
            "",
            "18000", "1500", "", "", "", "",
            "1", "2",                     # модель из списка, потом «своё по названию»
            "Ноутбук Lenovo", "Lenovo ThinkPad T14", "4", "thinkpad t14", "15000", "",
            "",                           # больше своих нет
            "",
        ])
        custom = back.items[-1]
        self.assertEqual(custom.category, "noutbuki")
        self.assertEqual(custom.min_price, 15000)
        self.assertEqual(custom.variant, "storage")      # для ноутбуков по умолчанию делим по памяти
        import re
        self.assertTrue(re.search(custom.match, "lenovo thinkpad t14 gen 2"))
        self.assertFalse(re.search(custom.match, "lenovo ideapad"))

    def test_custom_item_by_avito_url(self):
        url = "https://www.avito.ru/rossiya/audio_i_video?q=AirPods+Pro&user=1&pmin=5000"
        s, back = self.run_wizard([
            "",
            "18000", "1500", "", "", "", "",
            "",                           # готовые модели не выбираем
            "1", url, "AirPods Pro", "нет",
            "", "",
        ])
        self.assertEqual(len(back.items), 1)
        item = back.items[0]
        self.assertEqual((item.name, item.url, item.variant, item.category), ("AirPods Pro", url, "none", ""))

    def test_listing_url_becomes_example_item(self):
        url = "https://www.avito.ru/ekaterinburg/telefony/samsung_galaxy_s22_8_128_gb_4012345678"
        s, back = self.run_wizard([
            "", "18000", "1500", "", "", "", "",
            "",                           # готовые модели не выбираем
            "1", url, "",                 # образец, название по умолчанию
            "", "",
        ])
        item = back.items[0]
        self.assertEqual(item.example, url)
        self.assertEqual(item.query, "samsung galaxy s22")
        self.assertEqual((item.category, item.variant, item.name), ("telefony", "storage", "Samsung Galaxy S22"))

    def test_non_avito_url_is_rejected(self):
        s, back = self.run_wizard([
            "",
            "18000", "1500", "", "", "", "",
            "1",
            "1", "https://evil.example/search?q=x",
            "", "",
        ])
        self.assertTrue(all(not it.url for it in back.items))
        self.assertTrue(any("не ссылка" in line for line in self.said))

    def test_buy_limit_is_required(self):
        s, back = self.run_wizard([
            "", "", "0", "-5", "25000", "800", "", "", "", "",     # пусто, ноль и минус не принимаются
            "1", "", "",
        ])
        self.assertEqual((back.max_buy, back.min_margin), (25000, 800))
        self.assertEqual(sum("больше нуля" in line for line in self.said), 2)

    def test_invalid_number_is_asked_again(self):
        s, back = self.run_wizard([
            "",
            "много", "18000", "1500", "", "", "", "",
            "1", "", "",
        ])
        self.assertEqual(back.max_buy, 18000)


if __name__ == "__main__":
    unittest.main()
