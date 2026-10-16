import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import server

S = dict(server.DEFAULT_SETTINGS)


class Cleanup(unittest.TestCase):
    def test_numbers(self):
        self.assertEqual(server.to_number("1,234.50"), 1234.5)
        self.assertEqual(server.to_number("Rs. 9,759.75"), 9759.75)
        self.assertEqual(server.to_number("1.234,50"), 1234.5)
        self.assertEqual(server.to_number("12,50"), 12.5)
        self.assertIsNone(server.to_number(""))

    def test_dates(self):
        self.assertEqual(server.to_iso_date("03/10/2026"), "2026-10-03")
        self.assertEqual(server.to_iso_date("03/10/2026", day_first=False), "2026-03-10")
        self.assertEqual(server.to_iso_date("09-Oct-26"), "2026-10-09")
        self.assertEqual(server.to_iso_date("5 October 2026"), "2026-10-05")
        self.assertEqual(server.to_iso_date("2026-10-12"), "2026-10-12")
        self.assertEqual(server.to_iso_date("31/02/2026"), "")

    def test_flags_missing_total(self):
        r = server.normalise({"vendor": "X", "date": "01/10/2026", "category": "dairy"}, S, "x.png")
        self.assertEqual(r["status"], "review")
        self.assertIn("total missing", r["problems"])

    def test_unknown_category_falls_back(self):
        r = server.normalise({"vendor": "X", "date": "01/10/2026", "total": 5, "category": "spaceships"}, S, "x.png")
        self.assertEqual(r["category"], "other")
        self.assertEqual(r["status"], "ok")

    def test_item_sum_mismatch_is_flagged(self):
        raw = {"vendor": "X", "date": "01/10/2026", "total": 1000, "category": "dairy",
               "items": [{"name": "a", "amount": 100}, {"name": "b", "amount": 50}]}
        self.assertIn("line items do not add up to the total", server.normalise(raw, S, "x")["problems"])

    def test_demo_table_is_consistent(self):
        table = server._read_json(os.path.join(server.SAMPLES, "samples.json"), {})
        self.assertEqual(len(table), 8)
        for name, raw in table.items():
            self.assertEqual(server.normalise(raw, S, name)["status"], "ok", name)


if __name__ == "__main__":
    unittest.main()
