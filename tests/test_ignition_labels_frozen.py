"""Rebuilding the daily ignition labels from the tracked frozen grid and filtered events (no boundary)."""
import csv
import gzip
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import build_cpa_daily_ignition_labels as LABELS

EVENT_FIELDS = ["nfdb_fire_id", "ignition_date", "large_fire_200ha", "grid_id"]


def write_inputs(folder, cells, events, counts):
    folder = Path(folder)
    with (folder / "grid.csv").open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=["grid_id", "grid_x_m", "grid_y_m", "centroid_longitude", "centroid_latitude"])
        writer.writeheader()
        writer.writerows({"grid_id": cell, "grid_x_m": 0, "grid_y_m": 0, "centroid_longitude": 0, "centroid_latitude": 0} for cell in cells)
    with (folder / "events.csv").open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=EVENT_FIELDS)
        writer.writeheader()
        writer.writerows(events)
    (folder / "audit.json").write_text(json.dumps({"counts": counts}), encoding="utf-8")
    return {"GRID": folder / "grid.csv", "FILTERED_EVENTS": folder / "events.csv", "AUDIT": folder / "audit.json", "LABELS": folder / "labels.csv.gz"}


class FrozenLabelTests(unittest.TestCase):
    cells = ["ofr10km_0_0", "ofr10km_0_10000"]
    events = [
        {"nfdb_fire_id": "a", "ignition_date": "2010-05-01", "large_fire_200ha": "0", "grid_id": "ofr10km_0_10000"},
        {"nfdb_fire_id": "b", "ignition_date": "2010-05-01", "large_fire_200ha": "1", "grid_id": "ofr10km_0_10000"},
        {"nfdb_fire_id": "c", "ignition_date": "2019-10-31", "large_fire_200ha": "0", "grid_id": "ofr10km_0_0"},
    ]

    def counts(self, **changes):
        days = len(LABELS.fire_season_dates())
        return {"included_events": 3, "grid_cells": 2, "fire_season_days": days, "label_rows": 2 * days,
                "positive_cell_days": 2, "large_fire_positive_cell_days": 1, **changes}

    def test_labels_count_events_per_cell_day_in_the_original_row_order(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = write_inputs(folder, self.cells, self.events, self.counts())
            with mock.patch.multiple(LABELS, **paths):
                LABELS.build_from_frozen()
            with gzip.open(paths["LABELS"], "rt", encoding="utf-8", newline="") as source:
                rows = list(csv.DictReader(source))
        self.assertEqual(len(rows), self.counts()["label_rows"])
        self.assertEqual([r["grid_id"] for r in rows[:2]], self.cells)  # dates outermost, cells in grid order
        self.assertEqual(rows[1], {"grid_id": "ofr10km_0_10000", "ignition_date": "2010-05-01", "ignition": "1", "ignition_count": "2", "large_fire_200ha": "1"})
        self.assertEqual(rows[0]["ignition"], "0")
        self.assertEqual(rows[-2], {"grid_id": "ofr10km_0_0", "ignition_date": "2019-10-31", "ignition": "1", "ignition_count": "1", "large_fire_200ha": "0"})
        self.assertEqual(sum(int(r["ignition"]) for r in rows), 2)

    def test_counts_that_disagree_with_the_tracked_audit_stop_the_build(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = write_inputs(folder, self.cells, self.events, self.counts(positive_cell_days=3))
            with mock.patch.multiple(LABELS, **paths), self.assertRaisesRegex(ValueError, "disagree with the tracked label audit"):
                LABELS.build_from_frozen()
            self.assertFalse(paths["LABELS"].exists())

    def test_events_outside_the_frozen_grid_or_an_unsorted_grid_are_rejected(self):
        outside = self.events + [{"nfdb_fire_id": "d", "ignition_date": "2012-06-01", "large_fire_200ha": "0", "grid_id": "ofr10km_9_9"}]
        for cells, events in [(self.cells, outside), (list(reversed(self.cells)), self.events)]:
            with self.subTest(cells=cells), tempfile.TemporaryDirectory() as folder:
                paths = write_inputs(folder, cells, events, self.counts())
                with mock.patch.multiple(LABELS, **paths), self.assertRaises(ValueError):
                    LABELS.build_from_frozen()


if __name__ == "__main__":
    unittest.main()
