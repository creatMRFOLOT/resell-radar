import unittest

from resell_radar import urls


class UrlTests(unittest.TestCase):
    def test_is_avito_url(self):
        self.assertTrue(urls.is_avito_url("https://www.avito.ru/rossiya/telefony?q=s22"))
        self.assertTrue(urls.is_avito_url("https://m.avito.ru/x"))
        self.assertFalse(urls.is_avito_url("https://evil.example/avito.ru"))
        self.assertFalse(urls.is_avito_url("https://avito.ru.evil.example/x"))
        self.assertFalse(urls.is_avito_url("javascript:alert(1)"))
        self.assertFalse(urls.is_avito_url(""))

    def test_query_from_url(self):
        self.assertEqual(urls.query_from_url("https://www.avito.ru/x?q=Samsung+S22&s=104"), "Samsung S22")
        self.assertEqual(urls.query_from_url("https://www.avito.ru/x"), "")

    def test_build_search_url(self):
        url = urls.build_search_url("ekaterinburg", "telefony", "Pixel 8", 6000)
        self.assertEqual(url, "https://www.avito.ru/ekaterinburg/telefony?q=Pixel+8&s=104&pmin=6000")
        self.assertTrue(urls.build_search_url("rossiya", "", "AirPods").startswith("https://www.avito.ru/rossiya?q="))

    def test_prepare_url_private(self):
        out = urls.prepare_url("https://www.avito.ru/rossiya/telefony?q=s22", "private")
        self.assertIn("user=1", out)
        self.assertIn("s=104", out)

    def test_prepare_url_company_and_any(self):
        self.assertIn("user=2", urls.prepare_url("https://www.avito.ru/x?q=a", "company"))
        self.assertNotIn("user=", urls.prepare_url("https://www.avito.ru/x?q=a", "any"))

    def test_prepare_url_respects_user_choices(self):
        out = urls.prepare_url("https://www.avito.ru/x?q=a&user=2&s=1&pmax=5000", "private")
        self.assertIn("user=2", out)
        self.assertNotIn("user=1", out)
        self.assertIn("s=1", out)
        self.assertNotIn("s=104", out)
        self.assertNotIn("pmax", out)


if __name__ == "__main__":
    unittest.main()
