import copy
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.forecast_overview import build_overview
from scripts.live_workflow import read_snapshot


def snapshot():
    return {
        "schema_version": 1,
        "collected_at_utc": "2026-11-02T15:00:00Z",
        "live_ignition_probability": None,
        "live_spread": None,
        "notices": [],
        "live_blockers": ["No verified current fire perimeter"],
        "weather": {
            "available_at_utc": "2026-11-02T15:00:00Z",
            "valid_until_utc": "2026-11-03T06:00:00Z",
            "future_six_hours_covered": True,
        },
        "incidents": [{"incident_id": "one", "weather_context": {
            "hours": [{"valid_time_utc": "2026-11-02T16:00:00Z", "temp_c": 7.0}],
        }}],
    }


def read_at(document, now):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "snapshot.json"
        path.write_text(json.dumps(document))
        return read_snapshot(path, now=now)


def overview(workflow):
    with patch("scripts.forecast_overview.study_metrics", return_value=[]):
        return build_overview(Path("unused"), workflow,
                              {"status": "unavailable", "probability": None})


def test_expired_forecasts_are_removed_and_feed_is_stale():
    result = overview(read_at(snapshot(), "2026-11-06T15:00:00Z"))
    assert result["forecast_weather_status"] == "unavailable"
    assert result["feed_freshness"] == "stale"
    assert result["incidents"][0]["weather_context"]["hours"] == []
    assert result["live_ignition_probability"] is None
    assert result["live_spread"] is None


def test_weather_availability_does_not_activate_wildfire_predictions():
    result = overview(read_at(snapshot(), "2026-11-02T15:01:00Z"))
    assert result["forecast_weather_status"] == "available"
    assert result["operational"] is False
    assert result["live_ignition_probability"] is None
    assert result["live_spread"] is None


@pytest.mark.parametrize("field", ["live_ignition_probability", "live_spread"])
def test_edited_snapshot_cannot_activate_predictions(field):
    document = copy.deepcopy(snapshot())
    document[field] = 0.5
    with pytest.raises(ValueError):
        read_at(document, "2026-11-02T15:01:00Z")


def test_edited_qualification_is_rejected():
    workflow = read_at(snapshot(), "2026-11-02T15:01:00Z")
    with pytest.raises(ValueError), patch("scripts.forecast_overview.study_metrics"):
        build_overview(Path("unused"), workflow, {"status": "ready", "probability": 0.5})


def test_http_overview_rejects_parameters_and_missing_evidence():
    from http.server import ThreadingHTTPServer
    from threading import Thread
    from urllib.error import HTTPError
    from urllib.request import urlopen
    from scripts.capstone_app import Handler

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with patch.object(Handler, "log_message"):
            with pytest.raises(HTTPError) as error:
                urlopen(f"http://127.0.0.1:{server.server_port}/api/forecast-overview?live=true", timeout=5)
            assert error.value.code == 400
            with patch("scripts.capstone_app.workflow_response", side_effect=FileNotFoundError):
                with pytest.raises(HTTPError) as error:
                    urlopen(f"http://127.0.0.1:{server.server_port}/api/forecast-overview", timeout=5)
                assert error.value.code == 503
                assert json.loads(error.value.read())["probability"] is None
            with urlopen(f"http://127.0.0.1:{server.server_port}/", timeout=5) as response:
                assert response.status == 200
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_interrupted_body_does_not_send_a_second_http_response():
    from scripts.capstone_app import Handler

    handler = object.__new__(Handler)

    def partial_response():
        handler._response_started = True
        raise OSError("Socket buffer exhausted after response headers")

    with patch.object(handler, "handle_get", side_effect=partial_response), \
            patch.object(handler, "log_error"), patch.object(handler, "send_json") as send:
        handler.do_GET()
    send.assert_not_called()
    assert handler.close_connection is True
