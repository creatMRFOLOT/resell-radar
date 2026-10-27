import unittest

from resell_radar import examples, parser, presets
from resell_radar.engine import Engine
from tests.helpers import card, item_page, search_page


class ParserTests(unittest.TestCase):
    def test_search_cards(self):
        html = search_page([
            card(111, "Samsung Galaxy S22, 8/128 ГБ", 15500, "nalchik", snippet="Хорошее состояние"),
            card(222, "Samsung Galaxy S22", 16000),
        ])
        items = parser.parse_search(html)
        self.assertEqual([i.id for i in items], ["111", "222"])
        self.assertEqual(items[0].price, 15500)
        self.assertEqual(items[0].city, "nalchik")
        self.assertEqual(items[0].snippet, "Хорошее состояние")
        # ссылка без трекинговых параметров
        self.assertEqual(items[0].url, "https://www.avito.ru/nalchik/telefony/phone_111")

    def test_card_without_price_is_skipped(self):
        html = '<div data-marker="item" data-item-id="1"><a data-marker="item-title" href="/x_1">' \
               '<h3 itemprop="name">Нет цены</h3></a></div>'
        self.assertEqual(parser.parse_search(html), [])

    def test_item_page(self):
        page = parser.parse_item(item_page("Телефон в идеале, АКБ 92%", {"Состояние": "Б/у", "Память": "128 ГБ"}))
        self.assertIn("АКБ 92%", page.description)
        self.assertEqual(page.params["состояние"], "Б/у")
        self.assertEqual(page.total_views, 120)
        self.assertEqual(page.today_views, 30)

    def test_empty_html(self):
        self.assertEqual(parser.parse_search(""), [])
        self.assertEqual(parser.parse_item("").description, "")


class ExampleTests(unittest.TestCase):
    def test_slug_and_listing_url(self):
        url = "https://www.avito.ru/ekaterinburg/telefony/samsung_galaxy_s22_8_128_gb_4012345678?context=x"
        self.assertTrue(examples.is_listing_url(url))
        self.assertFalse(examples.is_listing_url("https://www.avito.ru/rossiya/telefony?q=s22"))
        self.assertEqual(examples.slug_title(url), "samsung galaxy s22 8 128 gb")
        self.assertEqual(examples.category_from_url(url), "telefony")

    def test_query_drops_storage_colors_and_ram(self):
        cases = {
            "Samsung Galaxy S22, 8/128 ГБ, чёрный": "samsung galaxy s22",
            "samsung galaxy s22 8 128 gb": "samsung galaxy s22",
            "Apple iPhone 12 128 gb": "apple iphone 12",           # 12 это модель, не оперативка
            "Xiaomi Redmi Note 12 8 256": "xiaomi redmi note 12",
            "Nintendo Switch Lite прошитая 256gb": "nintendo switch lite прошитая",
            "PlayStation 5 825gb": "playstation 5",
        }
        for title, query in cases.items():
            with self.subTest(title=title):
                self.assertEqual(examples.derive(title).query, query)

    def test_filters_separate_similar_models(self):
        import re
        d = examples.derive("Samsung Galaxy S22, 8/128 ГБ", "https://www.avito.ru/x/telefony/a_4012345678")
        ok = lambda t: bool(re.search(d.match, t.lower())) and not re.search(d.exclude, t.lower())
        self.assertTrue(ok("Samsung Galaxy S22 256gb"))
        self.assertFalse(ok("Samsung Galaxy S22 Ultra"))
        self.assertFalse(ok("Samsung Galaxy S22+"))
        self.assertFalse(ok("Samsung Galaxy S21"))
        pro = examples.derive("iPhone 13 Pro 256")
        self.assertTrue(re.search(pro.match, "iphone 13 pro 128") and not re.search(pro.exclude, "iphone 13 pro 128"))
        self.assertTrue(re.search(pro.exclude, "iphone 13 pro max"))
        self.assertEqual(d.variant, "storage")
        self.assertEqual(examples.derive("AirPods Pro", "https://www.avito.ru/x/audio_i_video/a_4012345678").variant, "none")

    def test_item_page_title(self):
        page = parser.parse_item(item_page("текст", title="Samsung Galaxy S22, 8/128"))
        self.assertEqual(page.title, "Samsung Galaxy S22, 8/128")


class FavoriteStateTests(unittest.TestCase):
    def test_states(self):
        from resell_radar.browser import favorite_active
        self.assertFalse(favorite_active("Добавить в избранное"))
        self.assertTrue(favorite_active("Удалить из избранного"))
        self.assertTrue(favorite_active("В избранном"))
        self.assertTrue(favorite_active("", "true"))
        self.assertFalse(favorite_active("", "false"))


class PresetTests(unittest.TestCase):
    def item(self, name):
        return next(i for i in presets.all_presets() if i.name == name)

    def ok(self, name, title):
        return Engine.title_ok(self.item(name), title)

    def test_samsung_variants_are_separated(self):
        self.assertTrue(self.ok("Samsung Galaxy S22", "Samsung Galaxy S22 128gb"))
        self.assertFalse(self.ok("Samsung Galaxy S22", "Samsung Galaxy S22 Ultra 256"))
        self.assertFalse(self.ok("Samsung Galaxy S22", "Galaxy S22+ 256"))
        self.assertTrue(self.ok("Samsung Galaxy S22+", "Samsung S22+ 256"))
        self.assertTrue(self.ok("Samsung Galaxy S22 Ultra", "Самсунг S22 ультра"))
        self.assertFalse(self.ok("Samsung Galaxy S23", "Samsung Galaxy S23 FE"))

    def test_accessories_are_rejected(self):
        self.assertFalse(self.ok("Samsung Galaxy S22", "Чехол Samsung Galaxy S22"))
        self.assertFalse(self.ok("Samsung Galaxy S22", "Корпус Samsung S22"))
        self.assertFalse(self.ok("Samsung Galaxy S22", "Куплю Samsung Galaxy S22"))

    def test_pixel(self):
        self.assertTrue(self.ok("Google Pixel 8", "Google Pixel 8 128"))
        self.assertFalse(self.ok("Google Pixel 8", "Google Pixel 8 Pro"))
        self.assertFalse(self.ok("Google Pixel 8", "Pixel 8a"))
        self.assertTrue(self.ok("Google Pixel 8 Pro", "Pixel 8 Pro 256"))

    def test_iphone(self):
        self.assertTrue(self.ok("iPhone 13", "iPhone 13, 128 ГБ"))
        self.assertFalse(self.ok("iPhone 13", "iPhone 13 Pro Max 256"))
        self.assertFalse(self.ok("iPhone 13", "iPhone 13 mini"))
        self.assertTrue(self.ok("iPhone 13 Pro", "iPhone 13 Pro 256"))
        self.assertFalse(self.ok("iPhone 13 Pro", "iPhone 13 Pro Max"))
        self.assertTrue(self.ok("iPhone 14 Pro Max", "Айфон 14 про макс"))

    def test_consoles(self):
        lite = "Nintendo Switch Lite (прошитая)"
        oled = "Nintendo Switch OLED (прошитая)"
        self.assertTrue(self.ok(lite, "Nintendo Switch Lite прошитая 256gb"))
        self.assertTrue(self.ok(lite, "Нинтендо свич лайт чипованная"))
        self.assertFalse(self.ok(lite, "Nintendo Switch OLED прошитая"))
        self.assertFalse(self.ok(lite, "Чехол для Nintendo Switch Lite"))
        self.assertFalse(self.ok(lite, "Nintendo Switch 2"))
        self.assertTrue(self.ok(oled, "Nintendo Switch OLED прошитая 512"))
        self.assertFalse(self.ok(oled, "Nintendo Switch Lite прошитая"))
        self.assertFalse(self.ok(oled, "Switch OLED аккаунт с играми"))

    def test_other_device_types(self):
        cases = [
            ("AirPods Pro 2", "Apple AirPods Pro 2 оригинал", True),
            ("AirPods Pro 2", "AirPods Pro 1 поколения", False),
            ("AirPods Pro", "AirPods Pro, с зарядным кейсом", True),
            ("PlayStation 5", "Sony PlayStation 5 825gb", True),
            ("PlayStation 5", "PS5 Pro 2TB", False),
            ("PlayStation 5", "Джойстик геймпад для PS5", False),
            ("Steam Deck", "Valve Steam Deck 256", True),
            ("Xbox Series S", "Xbox Series S 512gb", True),
            ("MacBook Air M1", "Apple MacBook Air 13 M1 8/256", True),
            ("MacBook Air M1", "MacBook Pro 14 M1", False),
            ("iPad 9", "iPad 9 64gb wifi", True),
            ("iPad 9", "iPad Pro 11", False),
        ]
        for name, title, expected in cases:
            with self.subTest(name=name, title=title):
                self.assertEqual(self.ok(name, title), expected)

    def test_variants_match_device_type(self):
        by_name = {i.name: i for i in presets.all_presets()}
        self.assertEqual(by_name["Samsung Galaxy S22"].variant, "storage")
        self.assertEqual(by_name["MacBook Air M1"].variant, "storage")
        self.assertEqual(by_name["iPad 9"].variant, "storage")
        self.assertEqual(by_name["AirPods Pro 2"].variant, "none")
        self.assertEqual(by_name["PlayStation 5"].variant, "none")
        self.assertEqual(by_name["Nintendo Switch Lite (прошитая)"].variant, "none")

    def test_categories_list(self):
        slugs = [slug for _, slug in presets.CATEGORIES]
        self.assertEqual(slugs[0], "")          # первый пункт: весь Avito
        self.assertIn("telefony", slugs)
        self.assertIn("noutbuki", slugs)

    def test_console_category(self):
        self.assertEqual(self.item("Nintendo Switch Lite (прошитая)").category,
                         "igry_pristavki_i_programmy")

    def test_names_unique(self):
        names = [i.name for i in presets.all_presets()]
        self.assertEqual(len(names), len(set(names)))


if __name__ == "__main__":
    unittest.main()
