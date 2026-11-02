import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from scripts.runtime_cache import parquet_lookup, explanation_lookup


class RuntimeCacheTests(unittest.TestCase):
    def test_parquet_cache_reuses_keyed_reads_and_returns_independent_frames(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "p.parquet"
            p.write_text("fixture")
            with patch(
                "scripts.runtime_cache.pd.read_parquet",
                return_value=pd.DataFrame({"p": [0.1]}),
            ) as read:
                a = parquet_lookup(p, ("p",), "2019-05-01", "a")
                a.loc[0, "p"] = 0.9
                b = parquet_lookup(p, ("p",), "2019-05-01", "a")
                self.assertEqual(read.call_count, 1)
                self.assertEqual(b.p.iloc[0], 0.1)
                parquet_lookup(p, ("p",), "2019-05-02", "a")
                self.assertEqual(read.call_count, 2)

    def test_replacing_a_file_invalidates_lookup(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "p.parquet"
            p.write_text("first")
            with patch(
                "scripts.runtime_cache.pd.read_parquet",
                return_value=pd.DataFrame({"p": [0.1]}),
            ) as read:
                parquet_lookup(p, ("p",), "2019-05-01", "a")
                p.write_text("replacement with a different size")
                parquet_lookup(p, ("p",), "2019-05-01", "a")
                self.assertEqual(read.call_count, 2)

    def test_explanation_index_and_file_invalidation(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "e.json"
            p.write_text(
                json.dumps(
                    {
                        "date": "2019-05-01",
                        "rows": [{"grid_id": "a", "top_factors": []}],
                    }
                )
            )
            date, row = explanation_lookup(p, "a")
            self.assertEqual(date, "2019-05-01")
            self.assertIsNotNone(row)
            p.write_text('{"date":"2019-05-02","rows":[]}')
            self.assertIsNone(explanation_lookup(p, "a")[1])

    def test_duplicate_explanation_keys_fail(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "e.json"
            p.write_text('{"date":"x","rows":[{"grid_id":"a"},{"grid_id":"a"}]}')
            with self.assertRaises(OSError):
                explanation_lookup(p, "a")
