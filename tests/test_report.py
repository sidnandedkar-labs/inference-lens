from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from report import demo_documents, quantile, render, summarize, validate_prices


class ReportTests(unittest.TestCase):
    def test_usage_cost_units(self):
        doc = demo_documents()[0]
        row = summarize(doc, {"Example A": {"input": 2, "output": 4}})
        self.assertAlmostEqual(row["mean_cost"], (500*2+150*4)/1_000_000)
        self.assertEqual(row["priced_requests"], 5)

    def test_failed_and_unpriced_runs_do_not_masquerade_as_zero_cost(self):
        doc = demo_documents()[0]
        doc["runs"][0]["usage"] = None
        doc["runs"].append({"status": "error", "elapsed_s": 100})
        row = summarize(doc, {"Example A": {"input": 1, "output": 1}})
        self.assertEqual(row["errors"], 1)
        self.assertEqual(row["priced_requests"], 4)
        self.assertLess(row["elapsed_p50"], 2)
        self.assertIsNone(summarize(doc, {})["mean_cost"])

    def test_zero_price_is_valid(self):
        prices = validate_prices({"Example A": {"input": 0, "output": 0}})
        self.assertEqual(summarize(demo_documents()[0], prices)["mean_cost"], 0)

    def test_html_script_termination_is_escaped(self):
        doc = demo_documents()[0]; doc["label"] = '</script><script>alert("x")</script>'
        output = render([summarize(doc, {})])
        self.assertNotIn(doc["label"], output)
        self.assertIn("\\u003c/script\\u003e", output)

    def test_invalid_numbers_and_missing_provenance_rejected(self):
        for value in [-1, True, float("inf"), "fast"]:
            doc = demo_documents()[0]; doc["runs"][0]["ttft_s"] = value
            with self.assertRaises(ValueError): summarize(doc, {})
        doc = demo_documents()[0]; del doc["synthetic"]
        with self.assertRaises(ValueError): summarize(doc, {})

    def test_price_validation(self):
        for value in [{"a": {"input": 1}}, {"a": {"input": True, "output": 1}}, []]:
            with self.assertRaises(ValueError): validate_prices(value)

    def test_quantile_interpolation(self):
        self.assertEqual(quantile([1, 2, 3, 4], .5), 2.5)
        self.assertIsNone(quantile([None], .5))


if __name__ == "__main__": unittest.main()
