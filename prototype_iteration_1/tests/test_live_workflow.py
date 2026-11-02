import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from scripts.workflow_sources import collect_layer, arcgis_json
from scripts.research_alerts import save_notices, notice_key
from scripts.live_workflow import (
    DistrictIndex,
    normalize_incidents,
    reconstruction_footprint,
    read_snapshot,
)
from shapely.geometry import box, mapping
import base64
import numpy as np


class SourceTests(unittest.TestCase):
    def session(self, documents):
        session = Mock()
        responses = []
        for d in documents:
            response = Mock()
            response.json.return_value = d
            responses.append(response)
        session.get.side_effect = responses
        return session

    def test_empty_feed_is_successful_empty_not_an_error_or_synthetic_fire(self):
        session = self.session(
            [
                {"fields": [{"name": "FIREID", "type": "esriFieldTypeOID"}]},
                {"objectIds": []},
            ]
        )
        with tempfile.TemporaryDirectory() as d:
            data, record = collect_layer("fires", Path(d), session)
            self.assertEqual(data["features"], [])
            self.assertEqual(record["features"], 0)

    def test_arcgis_error_and_truncated_feature_page_are_rejected(self):
        with self.assertRaises(ValueError):
            arcgis_json(self.session([{"error": {"code": 500}}]), "x", {})
        session = self.session(
            [
                {"fields": [{"name": "ID", "type": "esriFieldTypeOID"}]},
                {"objectIds": [1]},
                {
                    "type": "FeatureCollection",
                    "features": [],
                    "exceededTransferLimit": True,
                },
            ]
        )
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                collect_layer("fires", Path(d), session)

    def test_changed_or_missing_source_ids_are_rejected(self):
        session = self.session(
            [
                {"fields": [{"name": "ID", "type": "esriFieldTypeOID"}]},
                {"objectIds": [1]},
                {"type": "FeatureCollection", "features": [{"properties": {"ID": 2}}]},
            ]
        )
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                collect_layer("fires", Path(d), session)


class RegionTests(unittest.TestCase):
    def index(self):
        return DistrictIndex(
            {
                "features": [
                    {
                        "properties": {
                            "OBJECTID": 1,
                            "DISTRICT_NAME": "A",
                            "REGION_NAME": "R",
                        },
                        "geometry": mapping(box(0, 0, 10, 10)),
                    }
                ]
            },
            projected=True,
        )

    def test_area_intersection_uses_square_metres_and_boundary_touch_is_not_area(self):
        index = self.index()
        self.assertAlmostEqual(
            index.overlaps(box(5, 0, 15, 10))[0]["overlap_ha"], 0.005
        )
        self.assertEqual(index.overlaps(box(10, 0, 20, 10)), [])

    def test_reported_point_is_not_a_perimeter_or_predicted_cause(self):
        f = {
            "features": [
                {
                    "properties": {
                        "FIREID": 3,
                        "FIRE_NAME": "Test",
                        "CURRENT_SIZE": 10,
                        "CONFIRMED_DATE": 0,
                        "ESTIMATED_FIRE_CAUSE": "lightning",
                    },
                    "geometry": {"type": "Point", "coordinates": [-85, 49]},
                }
            ]
        }
        r = normalize_incidents(f)[0]
        self.assertIsNone(r["perimeter"])
        self.assertEqual(r["reported_cause"], "lightning")
        self.assertIsNone(r["state_observed_at_utc"])

    def test_reconstruction_decoder_filters_horizon_and_checks_dimensions(self):
        case = {
            "rows": 1,
            "columns": 2,
            "pixel": 90,
            "west": 0,
            "north": 90,
            "ignition": {
                "cells": base64.b64encode(np.array([0, 1], dtype="<u4")).decode(),
                "minutes": base64.b64encode(np.array([0, 120], dtype="<u2")).decode(),
            },
        }
        shape = reconstruction_footprint(case, 1)
        self.assertAlmostEqual(shape.area, 8100)
        case["ignition"]["minutes"] = ""
        with self.assertRaises(ValueError):
            reconstruction_footprint(case, 1)

    def test_stale_snapshot_is_marked_and_cannot_supply_live_predictions(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "current.json"
            p.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "collected_at_utc": "2026-01-01T00:00:00Z",
                        "live_ignition_probability": None,
                        "live_spread": None,
                        "notices": [],
                    }
                )
            )
            self.assertEqual(
                read_snapshot(p, now="2026-01-02T00:00Z")["freshness"], "stale"
            )
            v = json.loads(p.read_text())
            v["live_ignition_probability"] = 0.3
            p.write_text(json.dumps(v))
            with self.assertRaises(ValueError):
                read_snapshot(p, now="2026-01-02T00:00Z")


class NoticeTests(unittest.TestCase):
    def notice(self):
        return {
            "id": notice_key("observation", 1, 2),
            "kind": "observation",
            "actionable": False,
            "delivery": "local_only",
            "message": "Reported fire",
        }

    def test_repeat_is_idempotent_and_first_seen_is_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "n.sqlite"
            a = save_notices(p, [self.notice()], "first")
            b = save_notices(p, [self.notice()], "second")
            self.assertEqual(a[0]["revision"], b[0]["revision"])
            self.assertEqual(b[0]["first_seen_utc"], "first")
            self.assertEqual(save_notices(p, [], "third"), [])

    def test_actionable_delivery_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            n = {**self.notice(), "actionable": True}
            with self.assertRaises(ValueError):
                save_notices(Path(d) / "n.sqlite", [n], "now")


class PublicationTests(unittest.TestCase):
    def test_failed_json_publication_keeps_previous_snapshot(self):
        from scripts.workflow_sources import atomic_json

        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "latest.json"
            atomic_json(p, {"version": 1})
            with self.assertRaises(ValueError):
                atomic_json(p, {"bad": float("nan")})
            self.assertEqual(json.loads(p.read_text()), {"version": 1})
            self.assertEqual(list(Path(d).glob("*.partial")), [])

    def test_weather_context_expires_against_actual_time(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "latest.json"
            value = {
                "schema_version": 1,
                "collected_at_utc": "2026-01-01T00:00Z",
                "live_ignition_probability": None,
                "live_spread": None,
                "notices": [],
                "weather": {
                    "available_at_utc": "2026-01-01T00:00Z",
                    "valid_until_utc": "2026-01-01T08:00Z",
                    "future_six_hours_covered": True,
                },
                "incidents": [
                    {
                        "weather_context": {
                            "hours": [
                                {"valid_time_utc": "2026-01-01T01:00Z"},
                                {"valid_time_utc": "2026-01-01T08:00Z"},
                            ]
                        }
                    }
                ],
            }
            p.write_text(json.dumps(value))
            r = read_snapshot(p, now="2026-01-01T04:00Z")
            self.assertFalse(r["weather"]["future_six_hours_covered"])
            self.assertEqual(len(r["incidents"][0]["weather_context"]["hours"]), 1)

    def test_changed_notice_updates_revision_without_creating_new_identity(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "n.sqlite"
            n = {
                "id": "one",
                "actionable": False,
                "delivery": "local_only",
                "message": "first",
            }
            a = save_notices(p, [n], "2026-01-01T00:00Z")
            b = save_notices(p, [{**n, "message": "updated"}], "2026-01-02T00:00Z")
            self.assertNotEqual(a[0]["revision"], b[0]["revision"])
            self.assertEqual(a[0]["first_seen_utc"], b[0]["first_seen_utc"])
            with self.assertRaises(ValueError):
                save_notices(p, [n, n], "now")
