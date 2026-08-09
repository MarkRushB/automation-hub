import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "camp-status-generator.py"
SPEC = importlib.util.spec_from_file_location("camp_status_generator", MODULE_PATH)
status = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(status)


class StatusParserTests(unittest.TestCase):
    def setUp(self):
        self.watches = [
            {"id": "first", "campground": "Camp A", "arrival": "2026-08-14", "nights": 2},
            {"id": "second", "campground": "Camp B", "arrival": "2026-08-20", "nights": 3},
        ]

    def test_latest_result_is_kept_for_each_watch(self):
        logs = "\n".join([
            "2026-08-09 INFO [first] available=True; matching sites available=2; url=https://example.com/a",
            "2026-08-09 INFO [second] available=True; matching sites available=1; url=https://example.com/b",
            "2026-08-09 INFO [first] available=False; matching sites available=0; url=https://example.com/a2",
        ])
        results = {item["id"]: item for item in status.parse_watch_results(logs, self.watches)}
        self.assertFalse(results["first"]["available"])
        self.assertEqual(results["first"]["available_count"], 0)
        self.assertEqual(results["first"]["booking_url"], "https://example.com/a2")
        self.assertTrue(results["second"]["available"])
        self.assertEqual(results["second"]["available_count"], 1)

    def test_unchecked_watch_remains_pending(self):
        results = status.parse_watch_results(
            "2026-08-09 INFO [first] available=False; matching sites available=0; url=https://example.com/a",
            self.watches,
        )
        self.assertIsNone(results[1]["available"])
        self.assertIsNone(results[1]["last_check"])

    def test_legacy_single_watch_log_is_supported(self):
        result = status.parse_watch_results(
            "2026-08-09 INFO available=True; matching sites available=3",
            self.watches[:1],
        )[0]
        self.assertTrue(result["available"])
        self.assertEqual(result["available_count"], 3)


if __name__ == "__main__":
    unittest.main()
