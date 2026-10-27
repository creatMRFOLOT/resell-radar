import tempfile
import unittest
from pathlib import Path

from resell_radar import cli
from resell_radar import config as cfg
from resell_radar import presets


class LoadOrExitTests(unittest.TestCase):
    def path(self, settings):
        path = Path(tempfile.mkdtemp()) / "config.toml"
        cfg.save(settings, path)
        return path

    def test_missing_buy_limit_stops_with_hint(self):
        path = self.path(cfg.Settings(items=presets.all_presets()[:1]))
        with self.assertRaises(SystemExit) as ctx:
            cli._load_or_exit(path)
        self.assertIn("max_buy", str(ctx.exception))

    def test_valid_config_loads(self):
        path = self.path(cfg.Settings(max_buy=20000, items=presets.all_presets()[:1]))
        self.assertEqual(cli._load_or_exit(path).max_buy, 20000)

    def test_no_items_stops(self):
        with self.assertRaises(SystemExit):
            cli._load_or_exit(self.path(cfg.Settings(max_buy=20000)))


if __name__ == "__main__":
    unittest.main()
