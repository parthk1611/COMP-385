const $ = id => document.getElementById(id);
const pct = (value, digits = 2) => value == null ? '—' : `${(100 * value).toFixed(digits)}%`;
const number = value => value == null ? '—' : Number(value).toLocaleString('en-CA', {maximumFractionDigits: 2});
const colours = ['#dce8ba', '#b4d38e', '#7fa66b', '#497957', '#b78043', '#913f32'];
const state = {meta: null, grid: null, day: null, selected: null, threshold: 4, zoom: 1, tx: 0, ty: 0, scale: 1, dateRequest: 0, cellRequest: 0, loading: true};
const canvas = $('map');
const ctx = canvas.getContext('2d');
let width = 1, height = 1, dpr = 1, drag = null, abortDate = null;

function text(id, value) { $(id).textContent = value; }
function node(tag, content, className) {
  const element = document.createElement(tag);
  if (content != null) element.textContent = content;
  if (className) element.className = className;
  return element;
}
async function api(path, signal) {
  const response = await fetch(path, {signal});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'The request could not be completed.');
  return result;
}
function error(message) { text('error', message); $('error').hidden = !message; }
function cutoff() { return state.meta.policy.choices[state.threshold].threshold; }
function setBusy(busy) {
  state.loading = busy;
  for (const id of ['date', 'threshold']) $(id).disabled = busy;
  $('previous').disabled = busy || $('date').value <= state.meta.first_date;
  $('next').disabled = busy || $('date').value >= state.meta.last_date;
  $('download').setAttribute('aria-disabled', String(busy));
}

async function loadDay(day) {
  const request = ++state.dateRequest;
  ++state.cellRequest;
  if (abortDate) abortDate.abort();
  abortDate = new AbortController();
  setBusy(true);
  error('');
  text('status', `Scoring ${day} from corrected, past-only inputs…`);
  try {
    const data = await api(`/api/predictions?date=${encodeURIComponent(day)}`, abortDate.signal);
    if (request !== state.dateRequest) return;
    if (data.scores.length !== state.grid.cells.length) throw new Error('Prediction and map grids do not align.');
    state.day = data;
    $('date').value = day;
    $('download').href = `/api/download?date=${day}`;
    text('map-date', new Intl.DateTimeFormat('en-CA', {dateStyle: 'long', timeZone: 'UTC'}).format(new Date(`${day}T12:00:00Z`)) + ' · America/Toronto');
    text('status', `${number(data.summary.cells)} cells scored · ${number(data.summary.weather_missing)} with missing prior-day weather · Reconstructed model`);
    renderMetrics(); renderRanking(); draw();
    if (state.selected != null) await selectCell(state.selected, false);
  } catch (cause) {
    if (cause.name === 'AbortError') return;
    if (request === state.dateRequest) {
      error(cause.message);
      text('status', 'Unable to load the selected day. The last successfully loaded date remains displayed.');
      if (state.day) $('date').value = state.day.date;
    }
  } finally { if (request === state.dateRequest) setBusy(false); }
}

function metric(label, value) {
  const block = node('div', null, 'metric');
  block.append(node('strong', value), node('span', label));
  return block;
}
function renderMetrics() {
  if (!state.day) return;
  const m = state.day.tradeoffs[state.threshold];
  $('daily-metrics').replaceChildren(
    metric('Flagged cells today', number(m.alerts)), metric('Recorded ignitions', number(m.observed)),
    metric('Correct alerts', number(m.true_positive)), metric('False alerts', number(m.false_positive)),
    metric('Missed ignitions', number(m.false_negative)), metric('Recall today', pct(m.recall, 1)));
  const rows = [];
  for (const year of ['2018', '2019']) {
    const full = state.meta.results[year];
    const value = full.thresholds[state.threshold];
    const tr = node('tr');
    for (const cell of [year === '2018' ? '2018 validation · reconstructed' : '2019 test · reconstructed',
      pct(value.precision), pct(value.recall), number(value.alerts / 184), number(value.false_positive / 184)]) tr.append(node('td', cell));
    rows.push(tr);
  }
  const published = state.meta.published_2019.threshold_tradeoffs[state.threshold];
  const tr = node('tr');
  for (const cell of ['2019 test · original published', pct(published.precision), pct(published.recall),
    number(published.alerts_per_day), number(published.false_alerts_per_day)]) tr.append(node('td', cell));
  rows.push(tr);
  $('year-comparison').replaceChildren(...rows);
}

function renderRanking() {
  if (!state.day) return;
  const filter = $('ranking-filter').value;
  let indices = state.grid.cells.map((_, index) => index);
  if (filter === 'alerts') indices = indices.filter(i => state.day.scores[i] >= cutoff());
  if (filter === 'observed') indices = indices.filter(i => state.day.observed[i]);
  indices.sort((a, b) => state.day.scores[b] - state.day.scores[a] || a - b);
  const limit = filter === 'all' ? 30 : 200;
  text('ranking-caption', `${Math.min(indices.length, limit)} of ${number(indices.length)} ${filter === 'all' ? 'cells, highest score first' : filter === 'alerts' ? 'flagged cells' : 'recorded ignition cells'}. Select a row to inspect. Download includes every cell.`);
  const rows = indices.slice(0, limit).map((i, rank) => {
    const tr = node('tr', null, i === state.selected ? 'selected' : '');
    tr.append(node('td', rank + 1));
    const idCell = node('td');
    const button = node('button', state.grid.cells[i].id);
    button.type = 'button'; button.addEventListener('click', () => selectCell(i));
    idCell.append(button); tr.append(idCell, node('td', pct(state.day.scores[i], 4)),
      node('td', state.day.scores[i] >= cutoff() ? 'Flagged' : '—', state.day.scores[i] >= cutoff() ? 'flag' : ''),
      node('td', state.day.weather_missing[i] ? 'Missing' : `${state.day.station_counts[i]} stations`, state.day.weather_missing[i] ? 'weather-missing' : ''),
      node('td', state.day.observed[i] ? 'Yes' : 'No'));
    return tr;
  });
  if (!rows.length) {
    const td = node('td', 'No cells match this filter on the selected day.', 'empty'); td.colSpan = 6;
    const tr = node('tr'); tr.append(td); rows.push(tr);
  }
  $('ranking-body').replaceChildren(...rows);
}

function pair(label, value) {
  const div = node('div'); div.append(node('dt', label), node('dd', value)); return div;
}
async function selectCell(index, focus = true) {
  if (state.loading && !state.day) return;
  const request = ++state.cellRequest;
  const day = state.day.date;
  state.selected = index;
  text('cell-title', state.grid.cells[index].id);
  text('cell-prompt', 'Loading the selected cell’s inputs…');
  $('cell-prompt').hidden = false; $('cell-detail').hidden = true;
  renderRanking(); draw();
  try {
    const result = await api(`/api/cell?date=${day}&grid_id=${encodeURIComponent(state.grid.cells[index].id)}`);
    if (request !== state.cellRequest || day !== state.day.date) return;
    state.cell = result;
    renderCell();
    if (focus && window.innerWidth < 751) $('cell-title').scrollIntoView({behavior: 'smooth', block: 'center'});
  } catch (cause) {
    if (request === state.cellRequest) text('cell-prompt', cause.message);
  }
}
function renderCell() {
  if (!state.cell || state.selected == null || state.cell.date !== state.day.date) return;
  const cell = state.cell, features = cell.features, i = state.selected;
  $('cell-prompt').hidden = true; $('cell-detail').hidden = false;
  const small = node('small', 'Estimated daily ignition probability');
  $('cell-score').replaceChildren(document.createTextNode(pct(cell.score, 4)), small);
  text('cell-state', `${cell.score >= cutoff() ? 'Flagged at this cutoff' : 'Below this cutoff'} · ${cell.observed ? 'Recorded ignition' : 'No recorded ignition'}`);
  $('cell-context').replaceChildren(
    pair('Location', `${state.grid.cells[i].latitude.toFixed(3)}°, ${state.grid.cells[i].longitude.toFixed(3)}°`),
    pair('Prior-day weather', features.cwfis_missing ? 'Missing' : `${number(features.cwfis_station_count)} stations`),
    pair('Temperature', features.cwfis_temp_c == null ? 'Missing' : `${number(features.cwfis_temp_c)} °C`),
    pair('Relative humidity', features.cwfis_rh_pct == null ? 'Missing' : `${number(features.cwfis_rh_pct)}%`),
    pair('Wind speed', features.cwfis_wind_speed_kmh == null ? 'Missing' : `${number(features.cwfis_wind_speed_kmh)} km/h`),
    pair('Fire Weather Index', features.cwfis_fwi == null ? 'Missing' : number(features.cwfis_fwi)),
    pair('Prior fire in same cell', features.fire_history_days_since_same_cell == null ? 'No earlier observed event' : `${number(features.fire_history_days_since_same_cell)} days earlier`));
  $('all-features').replaceChildren(...Object.entries(features).map(([key, value]) => pair(key,
    value == null ? (key === 'fire_history_days_since_same_cell' ? 'Censored: no earlier observed event' : 'Missing') : number(value))));
}

function resize() {
  const bounds = canvas.getBoundingClientRect();
  const oldWidth = width, oldHeight = height;
  width = Math.max(1, bounds.width); height = Math.max(1, bounds.height); dpr = window.devicePixelRatio || 1;
  canvas.width = Math.round(width * dpr); canvas.height = Math.round(height * dpr);
  if (state.grid && (oldWidth !== width || oldHeight !== height)) resetView(); else draw();
}
function resetView() {
  if (!state.grid) return;
  const cells = state.grid.cells;
  const minX = Math.min(...cells.map(c => c.x)), maxX = Math.max(...cells.map(c => c.x)) + 10000;
  const minY = Math.min(...cells.map(c => c.y)), maxY = Math.max(...cells.map(c => c.y)) + 10000;
  state.scale = Math.min((width - 60) / (maxX - minX), (height - 55) / (maxY - minY));
  state.tx = width / 2 - state.scale * (minX + maxX) / 2;
  state.ty = height / 2 + state.scale * (minY + maxY) / 2;
  state.zoom = 1; draw();
}
function zoomAt(factor, x = width / 2, y = height / 2) {
  const next = Math.max(.65, Math.min(15, state.zoom * factor));
  factor = next / state.zoom; state.zoom = next;
  state.tx = x + (state.tx - x) * factor; state.ty = y + (state.ty - y) * factor;
  state.scale *= factor; draw();
}
function drawBoundary() {
  const geometry = state.grid.boundary;
  const polygons = geometry.type === 'Polygon' ? [geometry.coordinates] : geometry.coordinates;
  ctx.beginPath();
  for (const polygon of polygons) for (const ring of polygon) {
    ring.forEach(([x, y], i) => i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)); ctx.closePath();
  }
  ctx.fillStyle = '#cbdcbd'; ctx.fill('evenodd');
  ctx.strokeStyle = '#7c997d'; ctx.lineWidth = .8 / state.scale; ctx.stroke();
}
function draw() {
  ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!state.grid) return;
  ctx.setTransform(dpr * state.scale, 0, 0, -dpr * state.scale, dpr * state.tx, dpr * state.ty);
  drawBoundary();
  if (!state.day) return;
  const threshold = cutoff(), breaks = state.meta.colour_breaks;
  const onlyAlerts = $('alerts-only').checked;
  state.grid.cells.forEach((cell, i) => {
    const screenX = cell.x * state.scale + state.tx, screenY = -cell.y * state.scale + state.ty;
    const size = 10000 * state.scale;
    if (screenX + size < 0 || screenX > width || screenY < 0 || screenY - size > height) return;
    const score = state.day.scores[i];
    if (onlyAlerts && score < threshold) return;
    let band = 0; while (band < breaks.length && score >= breaks[band]) band++;
    ctx.fillStyle = colours[band]; ctx.fillRect(cell.x, cell.y, 10000, 10000);
    if (size > 4) { ctx.strokeStyle = '#ffffff25'; ctx.lineWidth = .35 / state.scale; ctx.strokeRect(cell.x, cell.y, 10000, 10000); }
    if (score >= threshold) { ctx.strokeStyle = '#ffffff'; ctx.lineWidth = 1 / state.scale; ctx.strokeRect(cell.x, cell.y, 10000, 10000); }
    if (state.day.weather_missing[i] && size > 8) {
      ctx.strokeStyle = '#34433e88'; ctx.lineWidth = .7 / state.scale;
      ctx.beginPath(); ctx.moveTo(cell.x + 2500, cell.y + 2500); ctx.lineTo(cell.x + 7500, cell.y + 7500); ctx.stroke();
    }
  });
  if ($('observations').checked) state.grid.cells.forEach((cell, i) => {
    if (!state.day.observed[i]) return;
    ctx.beginPath(); ctx.arc(cell.x + 5000, cell.y + 5000, 5 / state.scale, 0, 2 * Math.PI);
    ctx.fillStyle = '#181d19'; ctx.fill(); ctx.strokeStyle = '#fff'; ctx.lineWidth = 1.8 / state.scale; ctx.stroke();
  });
  if (state.selected != null) {
    const cell = state.grid.cells[state.selected];
    ctx.strokeStyle = '#182f43'; ctx.lineWidth = 3 / state.scale;
    ctx.strokeRect(cell.x - 1000, cell.y - 1000, 12000, 12000);
  }
}
function hit(x, y) {
  const worldX = Math.floor(((x - state.tx) / state.scale) / 10000) * 10000;
  const worldY = Math.floor(((state.ty - y) / state.scale) / 10000) * 10000;
  return state.positions.get(`${worldX},${worldY}`);
}
canvas.addEventListener('pointerdown', event => {
  if (!state.day) return;
  drag = {x: event.offsetX, y: event.offsetY, startX: event.offsetX, startY: event.offsetY, moved: false};
  canvas.setPointerCapture(event.pointerId); $('map-tip').hidden = true;
});
canvas.addEventListener('pointermove', event => {
  if (!state.day) return;
  if (drag) {
    state.tx += event.offsetX - drag.x; state.ty += event.offsetY - drag.y;
    if (Math.hypot(event.offsetX - drag.startX, event.offsetY - drag.startY) > 5) drag.moved = true;
    drag.x = event.offsetX; drag.y = event.offsetY; draw(); return;
  }
  const i = hit(event.offsetX, event.offsetY);
  $('map-tip').hidden = i == null;
  if (i != null) {
    text('map-tip', `${pct(state.day.scores[i], 4)}${state.day.weather_missing[i] ? ' · Weather missing' : ''}`);
    $('map-tip').style.left = `${Math.max(5, Math.min(width - 190, event.offsetX + 12))}px`;
    $('map-tip').style.top = `${Math.max(5, Math.min(height - 45, event.offsetY + 12))}px`;
  }
});
canvas.addEventListener('pointerup', event => {
  if (!drag) return;
  if (!drag.moved) { const i = hit(event.offsetX, event.offsetY); if (i != null) selectCell(i); }
  drag = null; canvas.releasePointerCapture(event.pointerId);
});
canvas.addEventListener('pointercancel', () => { drag = null; });
canvas.addEventListener('pointerleave', () => { $('map-tip').hidden = true; });
canvas.addEventListener('wheel', event => { event.preventDefault(); zoomAt(Math.exp(-event.deltaY * .0015), event.offsetX, event.offsetY); }, {passive: false});
canvas.addEventListener('keydown', event => {
  const moves = {ArrowLeft: [35, 0], ArrowRight: [-35, 0], ArrowUp: [0, 35], ArrowDown: [0, -35]};
  if (event.key in moves) { event.preventDefault(); const [x, y] = moves[event.key]; state.tx += x; state.ty += y; draw(); }
  if (event.key === '+' || event.key === '=') zoomAt(1.3);
  if (event.key === '-') zoomAt(1 / 1.3);
});
$('zoom-in').addEventListener('click', () => zoomAt(1.4));
$('zoom-out').addEventListener('click', () => zoomAt(1 / 1.4));
$('reset').addEventListener('click', resetView);
$('date').addEventListener('change', event => loadDay(event.target.value));
for (const [id, offset] of [['previous', -1], ['next', 1]]) $(id).addEventListener('click', () => {
  const day = new Date(`${$('date').value}T12:00:00Z`); day.setUTCDate(day.getUTCDate() + offset); loadDay(day.toISOString().slice(0, 10));
});
$('threshold').addEventListener('change', event => { state.threshold = Number(event.target.value); renderMetrics(); renderRanking(); renderCell(); draw(); });
for (const id of ['observations', 'alerts-only']) $(id).addEventListener('change', draw);
$('ranking-filter').addEventListener('change', renderRanking);
$('download').addEventListener('click', event => { if (state.loading || !state.day) event.preventDefault(); });
new ResizeObserver(resize).observe(canvas.parentElement);

async function boot() {
  try {
    const [meta, grid] = await Promise.all([api('/api/metadata'), api('/api/grid')]);
    state.meta = meta; state.grid = grid; state.threshold = meta.policy.default_index;
    state.positions = new Map(grid.cells.map((cell, index) => [`${cell.x},${cell.y}`, index]));
    $('threshold').replaceChildren(...meta.policy.choices.map(choice => {
      const option = node('option', `${pct(choice.threshold, 4)}${choice.index === meta.policy.default_index ? ' · Default F2' : ''}`);
      option.value = choice.index; return option;
    }));
    $('threshold').value = state.threshold;
    $('limitations').replaceChildren(...meta.limitations.map(item => node('li', item)));
    text('verification', meta.verification.status === 'PASS' ? 'Reconstruction verified: published 2019 metrics and all eight confusion tables match.' : 'Reconstruction discrepancy: results differ from the published experiment. Compare the separately labelled rows above.');
    if (meta.verification.status !== 'PASS') error('The reconstructed model differs from the original report. Its results are shown separately.');
    text('attribution', grid.attribution);
    const ranges = ['< ' + pct(meta.colour_breaks[0], 3), ...meta.colour_breaks.map(value => '≥ ' + pct(value, 3))];
    $('legend').replaceChildren(...colours.map((colour, i) => {
      const item = node('span'); const swatch = node('span', null, 'swatch'); swatch.style.background = colour;
      item.append(swatch, document.createTextNode(ranges[i])); return item;
    }));
    resetView(); await loadDay(meta.default_date);
  } catch (cause) { error(cause.message); text('status', 'The demo could not start. Check the local server window.'); }
}
boot();
