"""Date-range controls and a local Ontario prediction map."""
PAGE = r'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Daily estimates · Ontario Wildfire</title><style>
:root{color-scheme:light dark;--bg:#f4f6f3;--paper:#fff;--ink:#183429;--muted:#53675d;--line:#d7e1d9;--green:#1c6848}*{box-sizing:border-box}[hidden]{display:none!important}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}main{max-width:1200px;margin:auto;padding:28px}a{color:var(--green)}h1{font-size:32px;margin-bottom:8px}h2{font-size:20px;margin-top:0}.muted{color:var(--muted)}.card{background:var(--paper);border:1px solid var(--line);border-radius:18px;padding:24px;margin-top:22px}.controls,.pager{display:flex;gap:16px;align-items:end;flex-wrap:wrap}label{display:grid;gap:6px}button,input,select{font:inherit;min-height:44px;padding:10px;border:1px solid var(--line);border-radius:9px;background:var(--paper);color:var(--ink)}button{cursor:pointer}button.primary{background:var(--green);color:#fff;padding:10px 24px}button:disabled{opacity:.5;cursor:default}a:focus-visible,button:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid #247bc3;outline-offset:3px}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:12px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap}th{font-weight:600}tr.selected{background:#e4f0e6}.grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:24px}.grid>div{min-width:0}svg{width:100%;height:auto;max-height:460px}#status{min-height:25px}.note{background:#fff2d5;border-radius:10px;padding:14px;color:#654e22}summary{cursor:pointer;min-height:44px}.pager{align-items:center;margin-top:14px}small{font-size:13px}@media(max-width:760px){main{padding:18px}.grid{grid-template-columns:minmax(0,1fr)}.card{padding:17px}h1{font-size:27px}}@media(prefers-color-scheme:dark){:root{--bg:#121c17;--paper:#1c2a22;--ink:#ebf4ed;--muted:#aec3b5;--line:#3b5143;--green:#90d9b3}.primary{color:#173724!important}tr.selected{background:#324f3d}}
</style><main><a href="/">← Wildfire dashboard</a><h1>Daily fire-start estimates</h1><p class="muted">Choose how many days to show, starting today in Ontario. Combine the saved weather forecast with historical fire patterns, or compare with history alone.</p><section class="card"><form id="range-form" class="controls"><label>Number of days<input id="days" name="days" type="number" min="1" step="1" value="14" required></label><label>Area<select id="region"><option>All Ontario</option><option>Northwest</option><option>Northeast</option><option>South (below 46 N)</option></select></label><label>Estimate uses<select id="estimate-model"><option value="weather">Weather + history (research)</option><option value="seasonal">Historical pattern</option></select></label><button class="primary" id="run">Generate estimates</button></form><p id="status" role="status" aria-live="polite">Loading model…</p><p class="note" id="model-note" aria-live="polite">Weather-based estimates are experimental. Today’s estimate covers the full calendar day, including hours already elapsed.</p></section><section class="card"><h2 id="range-title">Your date range</h2><p class="muted">Expected positive cells is the sum of cell probabilities. A positive cell contains at least one recorded start during the day. Forecast-weather coverage is shown separately.</p><a id="export-days" href="#">Download these days as CSV</a><div class="scroll"><table><thead><tr><th>Day</th><th>Expected positive cells</th><th>Highest cell probability</th><th>Weather locations ready</th><th>Estimate uses</th><th>Explore</th></tr></thead><tbody id="daily"></tbody></table></div><div class="pager"><button id="previous" disabled>Previous days</button><span id="page-position"></span><button id="next" disabled>Next days</button></div></section><section class="card" id="map-section"><div class="controls"><label>Map view<select id="map-view"><option value="range">Whole date range</option><option value="day">One day</option></select></label><label id="map-day-label" hidden>Choose day<input id="map-day" type="date"></label></div><div class="grid" style="margin-top:20px"><div><h2 id="map-title">Ontario cells</h2><p class="muted" id="map-description"></p><div id="map-legend" class="muted" style="font-size:12px;display:flex;gap:12px;flex-wrap:wrap"></div><svg id="map" viewBox="0 0 520 420" role="img" aria-label="Estimated daily fire-start probabilities across Ontario cells"></svg></div><div><h2>Highest estimated cells</h2><p id="cell-note" class="muted"></p><a id="export-cells" href="#">Download mapped cells</a><div class="scroll"><table><thead><tr><th>Cell</th><th>Location</th><th id="cell-metric-title">Expected start days</th><th>Weather days</th></tr></thead><tbody id="cells"></tbody></table></div></div></div></section><details class="card"><summary>Model results, sources and coverage</summary><div id="evidence"></div><p>The seasonal model smooths 12 years of past fire starts over nearby land cells and calendar days. The current saved model uses records from 2014–2025 with source timestamps before the November 2026 model build. Later dates reuse this frozen seasonal pattern.</p><p>The target uses IFR fire records from the Ontario agency snapshot. Reporting coverage and publication timing are imperfect. The source timestamp is a historical availability proxy. A zero label means no eligible start was recorded in that snapshot.</p><p>The weather comparison uses 139 geometry-selected sites in 100 km blocks and archived HRDPS predictions. The displayed weather estimate maps each grid cell to its forecast location and passes temperature, humidity, rain, wind and valid-hour count into the saved LightGBM model. The model also receives historical seasonal frequency and calendar features. Missing or expired weather uses the historical estimate for that cell and day. Longer date ranges combine these daily values. Validation covered May–October 2025 and remains a development comparison.</p><p><a href="https://github.com/evankoza/wildfire-forecast" target="_blank" rel="noopener">Canadian wildfire forecast project</a> · <a href="https://github.com/tannerorourke/fire-fusion" target="_blank" rel="noopener">Fire-fusion project</a></p></details></main><script>
const el = id => document.getElementById(id);
let offset = 0, result = null, rangeRequest = 0, cellRequest = 0, inputTimer;
const fmt = (x, digits = 3) => Number(x).toLocaleString('en-CA', {maximumFractionDigits: digits});
const pct = x => (100 * x).toPrecision(3) + '%';
const valueOf = row => row.expected_positive_days ?? row.probability;
const colour = value => {
    const intensity = Math.min(1, Math.log1p(value / .00001) / Math.log1p(100000));
    const hue = 55 * (1 - intensity);
    const lightness = 92 - 58 * intensity;
    return 'hsl(' + hue + ' 95% ' + lightness + '%)';
};
function params() {
    return new URLSearchParams({days: el('days').value, region: el('region').value, offset: String(offset), model: el('estimate-model').value});
}
function cellParams() {
    const query = new URLSearchParams({days: String(result.days), region: result.region, view: el('map-view').value, model: result.requested_model});
    if (el('map-view').value === 'day') query.set('date', el('map-day').value);
    return query;
}
function td(tr, value) {
    const node = document.createElement('td');
    node.textContent = value;
    tr.append(node);
    return node;
}
async function json(url) {
    const response = await fetch(url, {cache: 'no-store'});
    const value = await response.json();
    if (!response.ok) throw Error(value.message || 'The saved prediction files could not be read.');
    return value;
}
function clearMap() {
    el('map').replaceChildren();
    el('cells').replaceChildren();
    el('export-cells').removeAttribute('href');
}
async function run() {
    const request = ++rangeRequest;
    ++cellRequest;
    el('run').disabled = true;
    el('previous').disabled = true;
    el('next').disabled = true;
    el('daily').replaceChildren();
    clearMap();
    el('export-days').removeAttribute('href');
    el('status').textContent = 'Generating daily estimates…';
    try {
        const query = params();
        const data = await json('/api/prediction-range?' + query);
        if (request !== rangeRequest) return;
        result = data;
        const weatherDays = data.estimate_summary.weather_days_used;
        let note = data.requested_model === 'weather' ? 'Weather used on ' + weatherDays + ' of ' + data.days + ' days. Other days use historical patterns. Weather-based estimates are experimental.' : 'Showing historical patterns only.';
        if (data.estimate_summary.outside_evaluated_season) note += ' The weather model was evaluated in May–October. Scores for this season are outside that evaluation.';
        el('model-note').textContent = note + ' Today’s estimate includes hours already elapsed.';
        el('range-title').textContent = data.start + ' to ' + data.end;
        el('status').textContent = fmt(data.days, 0) + (data.days === 1 ? ' day' : ' days') + ' · ' + data.region + ' · ' + fmt(data.rows[0].cells, 0) + ' cells per day';
        for (const row of data.rows) {
            const tr = document.createElement('tr');
            tr.dataset.day = row.date;
            td(tr, row.date);
            td(tr, fmt(row.expected_positive_cell_days, 4));
            td(tr, pct(row.highest_cell_probability));
            td(tr, row.weather.status === 'available' ? row.weather.complete_sites + '/' + row.weather.total_sites : row.weather.status.replaceAll('_', ' '));
            const source = td(tr, row.weather_cells_used ? 'Weather + history' : 'Historical pattern');
            source.title = row.weather_cells_used ? fmt(row.weather_cells_used, 0) + ' cells used weather' : row.fallback_reason.replaceAll('_', ' ');
            if (!row.weather_cells_used && data.requested_model === 'weather') {
                const reason = document.createElement('small');
                reason.style.display = 'block';
                reason.textContent = row.fallback_reason.replaceAll('_', ' ');
                source.append(reason);
            }
            const button = document.createElement('button');
            button.textContent = 'View this day';
            button.onclick = async () => {
                el('map-view').value = 'day';
                el('map-day').value = row.date;
                await loadCells();
                el('map-section').scrollIntoView({block: 'start'});
            };
            td(tr, '').append(button);
            el('daily').append(tr);
        }
        el('previous').disabled = !data.offset;
        el('next').disabled = !data.has_next;
        el('page-position').textContent = 'Days ' + (data.offset + 1) + '–' + (data.offset + data.rows.length) + ' of ' + fmt(data.days, 0);
        query.set('format', 'csv');
        el('export-days').href = '/api/prediction-range?' + query;
        el('map-day').min = data.start;
        el('map-day').max = data.end;
        if (el('map-day').value < data.start || el('map-day').value > data.end) el('map-day').value = data.start;
        const comparison = data.weather_candidate_comparison;
        el('evidence').textContent = 'Same May–October 2025 cases: weather model caught ' + comparison.candidate.hits + '/' + comparison.candidate.positives + ' positive cell-days (' + pct(comparison.candidate.recall) + '); seasonal baseline caught ' + comparison.baseline.hits + '/' + comparison.baseline.positives + ' (' + pct(comparison.baseline.recall) + '). Weather probability errors were worse. Live accuracy remains unmeasured.';
        await loadCells();
    } catch (error) {
        if (request !== rangeRequest) return;
        result = null;
        el('status').textContent = error.message;
        clearMap();
        el('export-days').removeAttribute('href');
    } finally {
        if (request === rangeRequest) el('run').disabled = false;
    }
}
function drawMap(rows, wholeRange) {
    const loX = Math.min(...rows.map(row => row.longitude)), hiX = Math.max(...rows.map(row => row.longitude));
    const loY = Math.min(...rows.map(row => row.latitude)), hiY = Math.max(...rows.map(row => row.latitude));
    const scale = Math.min(480 / (hiX - loX || 1), 380 / (hiY - loY || 1));
    const fragment = document.createDocumentFragment();
    for (const row of [...rows].reverse()) {
        const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        circle.setAttribute('cx', 20 + (row.longitude - loX) * scale);
        circle.setAttribute('cy', 400 - (row.latitude - loY) * scale);
        circle.setAttribute('r', '1.65');
        circle.setAttribute('fill', colour(valueOf(row)));
        const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
        title.textContent = row.grid_id + ' · ' + (wholeRange ? valueOf(row).toPrecision(4) + ' expected start days' : pct(valueOf(row)));
        circle.append(title);
        fragment.append(circle);
    }
    el('map').append(fragment);
    el('map-legend').replaceChildren();
    for (const value of [0, .0001, .001, .01, .1, 1]) {
        const label = document.createElement('span');
        const swatch = document.createElement('span');
        swatch.style.cssText = 'display:inline-block;width:12px;height:12px;margin-right:4px;background:' + colour(value);
        label.append(swatch, wholeRange ? String(value) : pct(value));
        el('map-legend').append(label);
    }
}
async function loadCells() {
    const request = ++cellRequest;
    if (!result) return;
    const wholeRange = el('map-view').value === 'range';
    el('map-day-label').hidden = wholeRange;
    clearMap();
    el('cell-note').textContent = 'Updating map…';
    const query = cellParams();
    try {
        const data = await json('/api/prediction-cells?' + query);
        if (request !== cellRequest) return;
        el('map-title').textContent = wholeRange ? result.start + ' to ' + result.end : 'Estimated starts · ' + el('map-day').value;
        el('map-description').textContent = wholeRange ? 'Expected days with at least one recorded start in each 10 km cell, summed across all ' + result.days + (result.days === 1 ? ' day. Colours' : ' days. Colours') + ' use a fixed logarithmic scale.' : 'Estimated probability of a recorded start in each 10 km cell on the selected day. Colours use a fixed logarithmic scale. Pale yellow indicates lower estimates, with orange and red for higher estimates.';
        el('cell-metric-title').textContent = wholeRange ? 'Expected start days' : 'Daily probability';
        el('cell-note').textContent = fmt(data.cells.length, 0) + ' cells · top 10 shown';
        const weatherDays = data.cells.map(row => row.weather_days_used);
        const minimum = Math.min(...weatherDays), maximum = Math.max(...weatherDays);
        el('cell-note').textContent += minimum === maximum ? ' · ' + maximum + ' weather day(s) per cell' : ' · weather use varies by location';
        for (const row of data.cells.slice(0, 10)) {
            const tr = document.createElement('tr');
            td(tr, row.grid_id);
            td(tr, fmt(row.latitude, 3) + ', ' + fmt(row.longitude, 3));
            td(tr, wholeRange ? valueOf(row).toPrecision(4) : pct(valueOf(row)));
            td(tr, row.weather_days_used);
            el('cells').append(tr);
        }
        drawMap(data.cells, wholeRange);
        query.set('format', 'csv');
        el('export-cells').href = '/api/prediction-cells?' + query;
        document.querySelectorAll('#daily tr').forEach(tr => tr.classList.toggle('selected', !wholeRange && tr.dataset.day === el('map-day').value));
    } catch (error) {
        if (request !== cellRequest) return;
        el('cell-note').textContent = error.message;
        clearMap();
    }
}
function changedRange() {
    clearTimeout(inputTimer);
    ++rangeRequest;
    ++cellRequest;
    clearMap();
    result = null;
    el('run').disabled = false;
    el('export-days').removeAttribute('href');
    el('status').textContent = 'Updating date range…';
    if (!el('days').checkValidity()) return;
    inputTimer = setTimeout(() => {offset = 0; el('map-view').value = 'range'; run();}, 350);
}
el('range-form').onsubmit = event => {event.preventDefault(); clearTimeout(inputTimer); offset = 0; el('map-view').value = 'range'; run();};
el('days').oninput = changedRange;
el('region').onchange = changedRange;
el('estimate-model').onchange = changedRange;
el('map-view').onchange = loadCells;
el('map-day').onchange = loadCells;
el('previous').onclick = () => {offset = Math.max(0, offset - 31); run();};
el('next').onclick = () => {offset += 31; run();};
run();
</script></html>'''


def dashboard_parts(seven_day=False):
    """Reuse the date-range controls inside the dashboard with private element IDs."""
    import re

    body = PAGE.split('<main>', 1)[1].split('</main>', 1)[0]
    body = body[body.index('<section class="card">'):]
    table_start = body.index('<section class="card"><h2 id="range-title">')
    map_start = body.index('<section class="card" id="map-section">')
    map_end = body.index('</section>', map_start) + len('</section>')
    body = body[:table_start] + body[map_start:map_end] + body[table_start:map_start] + body[map_end:]
    script = PAGE.split('<script>', 1)[1].split('</script>', 1)[0]
    if seven_day:
        body = re.sub(r'<label>Number of days<input[^>]+></label>', '', body)
        body = re.sub(r'<label>Estimate uses<select.*?</select></label>', '', body)
        body = body.replace('Generate estimates', 'Refresh outlook').replace('Whole date range', 'All seven days')
        body = body.replace('<input id="map-day" type="date">', '<select id="map-day" aria-label="Outlook day"></select>')
        body = body.replace('<div class="pager">', '<div class="pager" hidden>')
        body = body.replace('Highest estimated cells', 'Higher-ranked cells')
        body = body.replace('Highest cell probability', 'Highest daily estimate')
        body = body.replace('<th>Weather days</th>', '<th id="cell-weather-title">Weather days</th>')
        body = re.sub(r'<p>The weather comparison uses.*?</p>',
                      '<p>Open-Meteo GFS forecasts use the same source and offsets 1–7 in training and prediction. '
                      'Each Ontario calendar day uses maximum temperature, minimum humidity, total precipitation '
                      'and maximum wind speed, plus preceding-week forecast rainfall and its coverage. '
                      'The model also uses past fire frequency, coordinates, calendar, '
                      '2020 canopy and legacy ground terrain, with missing coverage retained. '
                      'Map colours use a fixed pale-yellow, orange and red scale for the estimated values, '
                      'not official danger categories. Missing or stale weather uses a labelled historical estimate. '
                      'The model comparison uses 2024 development blocks and a previously exposed 2025 diagnostic. '
                      'Weather refreshes while the server runs; new data is required for further learning.</p>', body)
        script = script.replace("return new URLSearchParams({days: el('days').value, region: el('region').value, offset: String(offset), model: el('estimate-model').value});",
                                "return new URLSearchParams({region: el('region').value});")
        script = script.replace("{days: String(result.days), region: result.region, view: el('map-view').value, model: result.requested_model}",
                                "{region: result.region, view: el('map-view').value}")
        script = script.replace('/api/prediction-range?', '/api/ignition-outlook?').replace('/api/prediction-cells?', '/api/ignition-cells?')
        script = re.sub(r'        const weatherDays =.*?el\(\x27model-note\x27\).textContent =.*?;',
                        "        el('model-note').textContent = data.model_notice;", script, flags=re.S)
        script = script.replace("el('map-day').min = data.start;", "const chosen = el('map-day').value;\n        el('map-day').replaceChildren(...data.rows.map(row => new Option(row.date, row.date)));\n        if (data.rows.some(row => row.date === chosen)) el('map-day').value = chosen;\n        el('map-day').min = data.start;")
        script = re.sub(r'        const comparison =[^\n]*\n        el\(\x27evidence\x27\).textContent =[^\n]*',
                        "        const comparison = data.comparison;\n        el('evidence').textContent = comparison ? 'Previously examined May–October 2025: candidate recall at the daily top-1% capacity ' + pct(comparison.diagnostic.recall) + '; history ' + pct(comparison.baseline.recall) + '. These are development results, not live accuracy. Forecast received: ' + data.forecast_received_at : 'The matching seven-day model comparison is running. Historical estimates remain active until a candidate passes its ranking checks.';",
                        script, flags=re.S)
        script = script.replace(
            "    el('map-day-label').hidden = wholeRange;",
            "    window.dispatchEvent(new CustomEvent('prediction-spread-selection', {detail: {"
            "mode: wholeRange ? 'range' : 'day', date: el('map-day').value, start: result.start, end: result.end}}));"
            "\n    el('map-day-label').hidden = wholeRange;"
        )
        script = script.replace("el('days').oninput = changedRange;", '').replace("el('estimate-model').onchange = changedRange;", '')
        script = script.replace("    if (!el('days').checkValidity()) return;", '')
        script = script.replace("el('cell-metric-title').textContent = wholeRange ? 'Expected start days' : 'Daily probability';",
                                "el('cell-metric-title').textContent = wholeRange ? 'Expected start days' : 'Daily probability';\n        el('cell-weather-title').textContent = wholeRange ? 'Weather days' : 'Forecast wind';")
        script = script.replace('td(tr, row.weather_days_used);', "td(tr, wholeRange ? row.weather_days_used : row.wind == null ? 'Unavailable' : fmt(row.wind, 1) + ' km/h');")
        script += "\nsetInterval(() => { if (result && !document.getElementById('predict').hidden) run(); }, 60000);\n"
    body = re.sub(r'id="([^"]+)"', lambda match: f'id="prediction-{match[1]}"', body)
    script = script.replace('document.getElementById(id)', "document.getElementById('prediction-' + id)")
    script = script.replace("'#daily tr'", "'#prediction-daily tr'")
    script = script.replace('\nrun();\n', "\nwindow.addEventListener('prediction-tab-opened', () => { if (rangeRequest === 0) run(); });\n")
    script = '<script>\n(() => {\n' + script + '\n})();\n</script>'
    style = '''<style>
#prediction-range{--paper:var(--surface);--green:var(--accent)}
#prediction-range [hidden]{display:none!important}
#prediction-range .card{background:var(--surface);border:1px solid var(--line);border-radius:18px;padding:24px;margin:0 0 22px}
#prediction-range .muted{color:var(--muted)}
#prediction-range .controls,#prediction-range .pager{display:flex;gap:16px;align-items:end;flex-wrap:wrap}
#prediction-range label{display:grid;gap:6px}
#prediction-range input,#prediction-range select,#prediction-range button{font:inherit;min-height:44px;padding:10px;border:1px solid var(--line);border-radius:10px;background:var(--surface);color:var(--ink)}
#prediction-range button.primary{background:var(--accent);color:var(--surface);padding:10px 24px}
#prediction-range button:disabled{opacity:.5;cursor:default}
#prediction-range .grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:24px}
#prediction-range .grid>div{min-width:0}
#prediction-range svg{width:100%;height:auto;max-height:460px}
#prediction-range .scroll{overflow:auto}
#prediction-range table{width:100%;border-collapse:collapse;font-size:14px}
#prediction-range th,#prediction-range td{padding:12px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap}
#prediction-range tr.selected{background:var(--accent-soft)}
#prediction-range .note{padding:14px;border-radius:10px;background:var(--warning-bg);color:var(--warning)}
#prediction-range .pager{align-items:center;margin-top:14px}
#prediction-range summary{cursor:pointer;min-height:44px}
#prediction-range h2{font-size:20px;margin-top:0}
#prediction-status{min-height:25px}
@media(max-width:760px){#prediction-range .grid{grid-template-columns:minmax(0,1fr)}#prediction-range .card{padding:17px}}
</style>'''
    return style, '<div id="prediction-range">' + body + '</div>', script
