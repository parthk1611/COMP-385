"""Small, row-preserving cache regressions without scanning production inputs."""
import csv
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd

from scripts.build_ignition_feature_panel import output_fields
from scripts.ignition_modeling import contract, data
from scripts.ignition_modeling.weather import WEATHER_NAMES, sha256


def panel_fixture(root, *, invalid=None):
    """Use the real 1840-date universe and an explicitly supplied two-cell grid."""
    root = Path(root)
    grid_path = root / "data/interim/ontario_fire_region_10km_grid.csv"
    grid_path.parent.mkdir(parents=True)
    grid = pd.DataFrame({
        "grid_id": ["a", "b"], "grid_x_m": [-20000, 30000],
        "grid_y_m": [40000, -50000], "centroid_longitude": [-85., -84.],
        "centroid_latitude": [48., 49.],
    })
    grid.to_csv(grid_path, index=False)
    dates = [day for year in range(2010, 2020)
             for day in pd.date_range(f"{year}-05-01", f"{year}-10-31")]
    weather = dict.fromkeys(WEATHER_NAMES, 1.)
    weather.update(cwfis_station_count=1., cwfis_nearest_station_km=10.,
                   cwfis_observation_coverage_fraction=.25,
                   cwfis_imputed_station_fraction=0.,
                   cwfis_calcstatus_nonzero_fraction=0., cwfis_missing=0.,
                   cwfis_temp_c=-3.123456789012345, cwfis_rh_pct=50.,
                   cwfis_ffmc=80., cwfis_precip_7d_mm=7.,
                   cwfis_precip_7d_coverage_days=7.)
    rows, source_values, corrected_values, labels = [], [], [], []
    for day_index, day in enumerate(dates):
        corrected = np.array([[weather[name] for name in WEATHER_NAMES]] * 2)
        corrected[:, WEATHER_NAMES.index("cwfis_temp_c")] += 2
        if day_index % 3 == 0:
            corrected[0, WEATHER_NAMES.index("cwfis_station_count")] = 0
            corrected[0, WEATHER_NAMES.index("cwfis_missing")] = 1
            corrected[0, WEATHER_NAMES.index("cwfis_observation_coverage_fraction")] = 0
            for name in contract.INDICATOR_FEATURES:
                if name in WEATHER_NAMES:
                    corrected[0, WEATHER_NAMES.index(name)] = np.nan
            corrected[0, WEATHER_NAMES.index("cwfis_precip_7d_coverage_days")] = 6
        # Reverse alternate dates to ensure correction follows grid IDs, not row order.
        for cell in ([0, 1] if day_index % 2 == 0 else [1, 0]):
            values = dict.fromkeys(contract.FEATURE_NAMES, 0.)
            phase = 2 * np.pi * day.dayofyear / (366 if day.is_leap_year else 365)
            declination = np.deg2rad(-23.44) * np.cos(2 * np.pi * (day.dayofyear + 10) / 365.2422)
            hour_angle = np.arccos(np.clip(-np.tan(np.deg2rad(grid.centroid_latitude[cell]))
                                          * np.tan(declination), -1, 1))
            values.update(weather)
            values.update(calendar_day_of_year=day.dayofyear,
                          calendar_doy_sin=np.sin(phase), calendar_doy_cos=np.cos(phase),
                          calendar_is_weekend=int(day.dayofweek >= 5),
                          calendar_day_length_hours=24 * hour_angle / np.pi,
                          terrain_elevation_mean_m=123.12345678901235,
                          terrain_slope_deg=0., terrain_aspect_sin=0., terrain_aspect_cos=1.,
                          terrain_ruggedness_m=1., terrain_sample_count=9., terrain_coverage_fraction=1.,
                          cell_centroid_easting_m=float(grid.grid_x_m[cell] + 5000),
                          cell_centroid_northing_m=float(grid.grid_y_m[cell] + 5000))
            if cell == 0:
                for name in ("terrain_elevation_mean_m", "terrain_slope_deg", "terrain_aspect_sin",
                             "terrain_aspect_cos", "terrain_ruggedness_m", contract.HISTORY_FEATURE):
                    values[name] = np.nan
                values.update(terrain_sample_count=0., terrain_coverage_fraction=0.)
                values[contract.HISTORY_CENSOR_FEATURE] = 1.
            else:
                values[contract.HISTORY_FEATURE] = 5.
                for name in ("fire_history_same_cell_30d", "fire_history_neighborhood_30d",
                             "fire_history_same_cell_365d", "fire_history_neighborhood_365d"):
                    values[name] = 1.
            if invalid is not None and not rows:
                values.update(invalid)
            label = int(cell == 1 and day_index % 7 == 0)
            rows.append({**values, "grid_id": grid.grid_id[cell],
                         "ignition_date": day.strftime("%Y-%m-%d"), "ignition": label,
                         "ignition_count": label, "large_fire_200ha": 0,
                         "feature_set_version": contract.FEATURE_SET_VERSION,
                         "issue_time_utc": day.tz_localize("America/Toronto").tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
                         "terrain_source_id": "nrcan_cdem_1945_2011", "terrain_source_vintage_end_year": 2011,
                         "cwfis_source_id": "cwfis_fwi_2010s_v3_ll",
                         "cwfis_observation_date": (day - pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
                         "fire_history_source_id": "nfdb_ontario_ignition_labels"})
            source_values.append([values[name] for name in contract.FEATURE_NAMES])
            corrected_values.append(corrected[cell])
            labels.append(label)
    source = root / "panel.csv"
    with source.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=output_fields())
        writer.writeheader()
        writer.writerows(rows)
    audit = {
        "status": "PASS", "full_scan_completed": True,
        "source": {"filename": source.name, "sha256": sha256(source), "bytes": source.stat().st_size},
        "schema": {"feature_set_version": contract.FEATURE_SET_VERSION,
                   "predictors": list(contract.FEATURE_NAMES), "predictor_count": len(contract.FEATURE_NAMES),
                   "columns": output_fields(), "target": "ignition",
                   "excluded_labels": contract.FEATURE_SELECTION["other_labels"],
                   "metadata_excluded_from_predictors": contract.FEATURE_SELECTION["metadata"]},
        "inputs": {"reference_grid": {"sha256": sha256(grid_path)},
                   "feature_selection": {"sha256": sha256(contract.SELECTION_PATH)}},
        "totals": {"rows": len(rows), "expected_rows": len(rows), "grid_cells": 2,
                   "fire_season_dates": len(dates), "positive_cell_days": sum(labels)},
    }
    audit_path = root / "panel_validation.json"
    audit_path.write_text(json.dumps(audit))
    return SimpleNamespace(root=root, source=source, grid=grid_path, audit_path=audit_path,
                           audit=audit, dates=[day.strftime("%Y-%m-%d") for day in dates],
                           source_values=np.array(source_values), labels=np.array(labels, dtype=np.uint8),
                           corrected_values=np.array(corrected_values), weather=weather)


def prepare_fixture(fixture, cache, *, report_path=None, weather_days=None):
    if weather_days is None:
        def weather_days(_db, _grid, dates):
            for i, day in enumerate(dates):
                values = fixture.corrected_values[2 * i:2 * i + 2]
                # Stored expected values follow panel row order; iterator returns grid order.
                yield day, values if i % 2 == 0 else values[::-1]
    with patch.object(data, "index_archive", return_value={"status": "PASS", "source": "fixture"}), \
            patch.object(data, "corrected_weather_days", side_effect=weather_days):
        return data.prepare_cache(fixture.source, cache, 73, audit_path=fixture.audit_path,
                                  report_path=report_path, grid_path=fixture.grid)


class IgnitionCacheTests(unittest.TestCase):
    def test_writes_and_reloads_all_39_predictors_and_only_corrects_weather(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:  # Windows keeps memory-mapped cache files open
            fixture = panel_fixture(temporary)
            cache = fixture.root / "cache"
            archival = fixture.root / "docs/modeling/corrected_weather_audit.json"
            archival.parent.mkdir(parents=True)
            archival.write_text("archival report must stay untouched\n")
            input_audit = fixture.audit_path.read_bytes()
            with patch.object(data, "ROOT", fixture.root):
                manifest = prepare_fixture(fixture, cache)
            X, y, restored = data.load_cache(cache)
            weather_columns = [contract.FEATURE_NAMES.index(name) for name in WEATHER_NAMES]
            expected = fixture.source_values.copy()
            expected[:, weather_columns] = fixture.corrected_values
            self.assertEqual(X.shape, (3680, 39))
            np.testing.assert_array_equal(X, expected)
            np.testing.assert_array_equal(y, fixture.labels)
            self.assertEqual(restored, manifest)
            self.assertEqual(manifest["features"], list(contract.FEATURE_NAMES))
            self.assertEqual(len(manifest["date_slices"]), 1840)
            self.assertEqual(manifest["panel_audit_sha256"], sha256(fixture.audit_path))
            censor = X[:, contract.FEATURE_NAMES.index(contract.HISTORY_CENSOR_FEATURE)]
            history = X[:, contract.FEATURE_NAMES.index(contract.HISTORY_FEATURE)]
            np.testing.assert_array_equal(censor, np.isnan(history))
            self.assertTrue(np.any(X[:, -2] < 0))
            self.assertTrue(np.any(X[:, -1] < 0))
            self.assertTrue(np.isnan(X[:, contract.FEATURE_NAMES.index("cwfis_temp_c")]).any())
            self.assertGreater(manifest["changed_cell_values"]["cwfis_temp_c"], 0)
            report = json.loads((cache / "corrected_weather_audit.json").read_text())
            self.assertEqual(report["cache_version"], contract.CACHE_VERSION)
            self.assertNotIn("date_slices", report)
            self.assertEqual(archival.read_text(), "archival report must stay untouched\n")
            self.assertEqual(fixture.audit_path.read_bytes(), input_audit)
            explicit_report = fixture.root / "reports/corrected.json"
            # Reusing the cache does not rebuild weather and honors an explicit report destination.
            reused = data.prepare_cache(fixture.source, cache, audit_path=fixture.audit_path,
                                        grid_path=fixture.grid, report_path=explicit_report)
            self.assertEqual(reused, manifest)
            self.assertEqual(json.loads(explicit_report.read_text()), report)

    def test_rejects_archival_audits_and_wrong_schema_or_provenance(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:  # Windows keeps memory-mapped cache files open
            fixture = panel_fixture(temporary)
            changes = [
                ("schema", "feature_set_version", "ignition-feature-v1.0.0"),
                ("schema", "predictor_count", 36),
                ("schema", "predictors", list(contract.FEATURE_NAMES[:36])),
                ("schema", "predictors", list(reversed(contract.FEATURE_NAMES))),
                ("schema", "columns", list(reversed(output_fields()))),
                ("source", "sha256", "0" * 64),
                ("source", "bytes", fixture.source.stat().st_size + 1),
                ("totals", "fire_season_dates", 1),
                ("totals", "rows", 2),
            ]
            for section, key, value in changes:
                with self.subTest(section=section, key=key, value=value):
                    audit = json.loads(json.dumps(fixture.audit))
                    audit[section][key] = value
                    fixture.audit_path.write_text(json.dumps(audit))
                    with self.assertRaises(ValueError):
                        data.prepare_cache(fixture.source, fixture.root / "cache",
                                           audit_path=fixture.audit_path, grid_path=fixture.grid)
                    self.assertFalse((fixture.root / "cache").exists())
            audit = json.loads(json.dumps(fixture.audit))
            audit["inputs"]["reference_grid"]["sha256"] = "0" * 64
            fixture.audit_path.write_text(json.dumps(audit))
            with self.assertRaisesRegex(ValueError, "provenance"):
                data.prepare_cache(fixture.source, fixture.root / "cache",
                                   audit_path=fixture.audit_path, grid_path=fixture.grid)

    def test_rejects_reordered_source_even_with_a_matching_checksum(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:  # Windows keeps memory-mapped cache files open
            fixture = panel_fixture(temporary)
            frame = pd.read_csv(fixture.source, float_precision="round_trip")
            frame[list(reversed(frame.columns))].to_csv(fixture.source, index=False)
            fixture.audit["source"].update(sha256=sha256(fixture.source), bytes=fixture.source.stat().st_size)
            fixture.audit_path.write_text(json.dumps(fixture.audit))
            with self.assertRaisesRegex(ValueError, "column order"):
                data.prepare_cache(fixture.source, fixture.root / "cache",
                                   audit_path=fixture.audit_path, grid_path=fixture.grid)

    def test_production_grid_size_is_not_relaxed_by_fixture_support(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:  # Windows keeps memory-mapped cache files open
            fixture = panel_fixture(temporary)
            with patch.object(data, "ROOT", fixture.root), self.assertRaisesRegex(ValueError, "9673"):
                data.prepare_cache(fixture.source, fixture.root / "cache", audit_path=fixture.audit_path)

    def test_rejects_native_censor_and_coordinate_violations_before_weather(self):
        for invalid in ({contract.HISTORY_CENSOR_FEATURE: 0.},
                        {contract.HISTORY_CENSOR_FEATURE: 2.},
                        {contract.HISTORY_FEATURE: 0., contract.HISTORY_CENSOR_FEATURE: 0.},
                        {contract.COORDINATE_FEATURES[0]: 15000.},
                        {contract.COORDINATE_FEATURES[1]: -45000.}):
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:  # Windows keeps memory-mapped cache files open
                fixture = panel_fixture(temporary, invalid=invalid)
                with patch.object(data, "index_archive") as index_archive, self.assertRaises(ValueError):
                    data.prepare_cache(fixture.source, fixture.root / "cache",
                                       audit_path=fixture.audit_path, grid_path=fixture.grid)
                index_archive.assert_not_called()
                self.assertFalse((fixture.root / "cache/manifest.json").exists())

    def test_rejects_incomplete_corrected_weather_dates(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:  # Windows keeps memory-mapped cache files open
            fixture = panel_fixture(temporary)
            with self.assertRaisesRegex(ValueError, "dates are incomplete"):
                prepare_fixture(fixture, fixture.root / "cache", weather_days=lambda *_: iter(()))
            self.assertFalse((fixture.root / "cache/manifest.json").exists())

    def test_load_rejects_old_version_reordering_and_wrong_file_sizes(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:  # Windows keeps memory-mapped cache files open
            root = Path(temporary)
            matrix = np.arange(3 * len(contract.FEATURE_NAMES), dtype=np.float64).reshape(3, -1)
            matrix[1, contract.FEATURE_NAMES.index(contract.HISTORY_FEATURE)] = np.nan
            matrix.tofile(root / "X.f64")
            np.array([0, 1, 0], dtype=np.uint8).tofile(root / "y.u8")
            manifest = {"rows": 3, "features": list(contract.FEATURE_NAMES), "cache_version": contract.CACHE_VERSION}
            path = root / "manifest.json"
            path.write_text(json.dumps(manifest))
            X, y, _ = data.load_cache(root)
            np.testing.assert_array_equal(X, matrix)
            np.testing.assert_array_equal(y, [0, 1, 0])
            del X, y
            for change in ({"cache_version": "ignition-v1-weather-asof-global-date-v2"},
                           {"features": list(contract.FEATURE_NAMES[:36])},
                           {"features": list(reversed(contract.FEATURE_NAMES))},
                           {"rows": 0}, {"rows": -1}, {"rows": 3.0}, {"rows": True}):
                with self.subTest(change=change):
                    path.write_text(json.dumps(manifest | change))
                    with self.assertRaises(ValueError):
                        data.load_cache(root)
            path.write_text(json.dumps(manifest))
            for name, wrong_size in (("X.f64", matrix.nbytes - 8),
                                     ("X.f64", matrix.nbytes + 8),
                                     ("X.f64", 3 * 36 * 8),
                                     ("y.u8", 2), ("y.u8", 4), ("grid.u16", 5)):
                with self.subTest(name=name, wrong_size=wrong_size):
                    target = root / name
                    original = target.read_bytes() if target.exists() else None
                    target.write_bytes(b"\0" * wrong_size)
                    with self.assertRaisesRegex(ValueError, "file size mismatch"):
                        data.load_cache(root)
                    if original is None:
                        target.unlink()
                    else:
                        target.write_bytes(original)
            (root / "y.u8").unlink()
            with self.assertRaisesRegex(ValueError, "file size mismatch"):
                data.load_cache(root)


if __name__ == "__main__":
    unittest.main()
