"""Load the shared spread viewer with current-weather data for one requested day."""
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[1] / "team_repository/capability_2_fire_spread/viewer/viewer_template.html"
LOADER = r"""
<script>
const statusText = document.getElementById("outlook-status");
const view = document.getElementById("outlook-viewer");
const selection = new URLSearchParams(location.search);
const request = new URLSearchParams({date: selection.get("date") || ""});
if (selection.has("incident")) request.set("incident", selection.get("incident"));
else statusText.textContent = "Checking the highest-ranked ignition cells for usable spread inputs…";
(async () => {
  try {
    const response = await fetch("/api/spread-outlook?" + request, {cache: "no-store"});
    const data = await response.json();
    if (!response.ok || data.operational !== false || !data.settings?.forecastScenario || !data.fires?.length) {
      throw new Error(data.message || "Forecast spread is unavailable for this date.");
    }
    view.classList.remove("pending");
    window.mountSpreadViewer(data);
    statusText.hidden = true;
  } catch (error) {
    view.classList.add("pending");
    statusText.hidden = false;
    statusText.textContent = error.message;
  }
})();
</script>
"""


def page():
    html = TEMPLATE.read_text()
    html = html.replace('<script src="spread_viewer_data.js"></script>', "", 1)
    html = html.replace('<div class="page">',
                        '<p id="outlook-status" class="page" role="status">Getting current forecast weather…</p>'
                        '<div id="outlook-viewer" class="page pending">', 1)
    return ("""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="icon" href="data:,"><style>.page.pending{display:none}</style>"""
            + html + LOADER + "</html>")
