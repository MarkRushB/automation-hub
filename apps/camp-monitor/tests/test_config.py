import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

SYNC_API = types.ModuleType("playwright.sync_api")
SYNC_API.Page = object
SYNC_API.sync_playwright = lambda: None
sys.modules.setdefault("playwright", types.ModuleType("playwright"))
sys.modules.setdefault("playwright.sync_api", SYNC_API)

MODULE_PATH = Path(__file__).parents[1] / "camp_monitor.py"
SPEC = importlib.util.spec_from_file_location("camp_monitor", MODULE_PATH)
camp_monitor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(camp_monitor)


class ConfigTests(unittest.TestCase):
    def load(self, payload):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            return camp_monitor.load_config(str(path))

    def test_multi_watch_config_inherits_shared_defaults(self):
        config = self.load({
            "site_type": "tent",
            "sites": ["A12"],
            "watches": [
                {"id": "first", "campground": "Camp A", "arrival": "2026-08-14", "nights": 2},
                {"id": "second", "campground": "Camp B", "arrival": "2026-08-20", "nights": 3, "sites": []},
            ],
        })
        self.assertEqual([watch["id"] for watch in config["watches"]], ["first", "second"])
        self.assertEqual(config["watches"][0]["site_type"], "tent")
        self.assertEqual(config["watches"][0]["sites"], ["A12"])
        self.assertEqual(config["watches"][1]["sites"], [])

    def test_legacy_single_watch_is_wrapped_and_given_an_id(self):
        config = self.load({
            "campground": "Salisbury Beach State Reservation, MA",
            "arrival": "2026-08-14",
            "nights": 2,
        })
        self.assertEqual(len(config["watches"]), 1)
        self.assertEqual(config["watches"][0]["id"], "salisbury-beach-state-reservation-ma-2026-08-14")

    def test_duplicate_watch_ids_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate watch id"):
            self.load({"watches": [
                {"id": "same", "campground": "Camp A", "arrival": "2026-08-14", "nights": 2},
                {"id": "same", "campground": "Camp B", "arrival": "2026-08-15", "nights": 2},
            ]})

    def test_empty_watch_list_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "non-empty list"):
            self.load({"watches": []})


if __name__ == "__main__":
    unittest.main()
