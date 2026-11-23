const $ = id => document.getElementById(id);
const pct = (value, digits = 2) => value == null ? '—' : `${(100 * value).toFixed(digits)}%`;
const number = value => value == null ? '—' : Number(value).toLocaleString('en-CA', {maximumFractionDigits: 2});
const colours = ['#dce8ba', '#b4d38e', '#7fa66b', '#497957', '#b78043', '#913f32'];
const state = {meta: null, grid: null, day: null, selected: null, spread: null, threshold: 4, zoom: 1, tx: 0, ty: 0, scale: 1, dateRequest: 0, cellRequest: 0, loading: true};
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
    clearSpread(); spreadReady();
    $('date').value = day;
    $('download').href = `/api/download?date=${day}`;
    text('map-date', new Intl.DateTimeFormat('en-CA', {dateStyle: 'long', timeZone: 'UTC'}).format(new Date(`${day}T12:00:00Z`)) + ' · America/Toronto · Frozen 10 km grid footprint');
    text('status', `${number(data.summary.cells)} cells scored · ${number(data.summary.weather_missing)} with missing prior-day weather · ${state.meta.model}`);
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
  const tr = node('tr');
  const unavailable = node('td', state.meta.performance_note);
  unavailable.colSpan = 5;
  tr.append(unavailable);
  $('year-comparison').replaceChildren(tr);
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
  if (!state.spreadRunning) spreadReady();
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
const MAX_ZOOM = 4000;  // deep enough to see single 90 m spread cells
function zoomAt(factor, x = width / 2, y = height / 2) {
  const next = Math.max(.65, Math.min(MAX_ZOOM, state.zoom * factor));
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
  if (state.spread && state.spreadRaster) {
    // Fade the ignition colours so the fire stands out, then draw everything burned by the playback time.
    const view = ctx.getTransform(); ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.fillStyle = '#ffffffa6'; ctx.fillRect(0, 0, canvas.width, canvas.height); ctx.setTransform(view);
    const raster = state.spreadRaster;
    renderSpreadRaster(state.spreadTime ?? state.spread.start.hours * 60);
    // The raster's rows run north to south, so place it in screen space; smoothing softens its edges as it scales up.
    ctx.save(); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = 'high';
    const x = raster.west * state.scale + state.tx, y = -raster.north * state.scale + state.ty;
    const w = raster.widthM * state.scale, h = raster.heightM * state.scale;
    const cellPx = 90 * state.scale, blur = Math.max(1.5, Math.min(12, cellPx * .55));
    ctx.filter = `blur(${(blur * 2.6).toFixed(1)}px)`; ctx.globalAlpha = .85; ctx.drawImage(raster.canvas, x, y, w, h);  // haze
    ctx.filter = `blur(${(blur * .6).toFixed(1)}px)`; ctx.globalAlpha = .95; ctx.drawImage(raster.canvas, x, y, w, h);   // body
    ctx.restore();
    const start = state.spread.start;
    ctx.beginPath(); ctx.arc(start.x_3978, start.y_3978, 6 / state.scale, 0, 2 * Math.PI);
    ctx.fillStyle = '#c0392b'; ctx.fill(); ctx.strokeStyle = '#fff'; ctx.lineWidth = 2 / state.scale; ctx.stroke();
  }
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
  if (state.spread && state.spreadTime != null) drawWindArrow();
}
function spreadWeather() {
  const hourly = state.spread?.hourly_weather || [];
  return hourly.length ? hourly[Math.min(hourly.length - 1, Math.floor((state.spreadTime || 0) / 60))] : null;
}
function drawWindArrow() {
  // Screen space, top right: points where the wind blows to. The map is EPSG:3978, so grid north differs from
  // true north by the grid convergence at the start point.
  const weather = spreadWeather();
  if (!weather) return;
  const downwind = (weather.wind_from_deg + 180 - (state.spread.start.grid_convergence_deg || 0)) * Math.PI / 180;
  const cx = width - 46, cy = 92, length = 14 + Math.min(weather.wind_kmh, 40) * .5;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.fillStyle = '#ffffffe6'; ctx.beginPath(); ctx.arc(cx, cy, 34, 0, 2 * Math.PI); ctx.fill();
  ctx.strokeStyle = '#1d3557'; ctx.fillStyle = '#1d3557'; ctx.lineWidth = 2.5;
  const dx = Math.sin(downwind), dy = -Math.cos(downwind);
  ctx.beginPath(); ctx.moveTo(cx - dx * length / 2, cy - dy * length / 2); ctx.lineTo(cx + dx * length / 2, cy + dy * length / 2); ctx.stroke();
  const tipX = cx + dx * length / 2, tipY = cy + dy * length / 2;
  ctx.beginPath(); ctx.moveTo(tipX, tipY);
  ctx.lineTo(tipX - dx * 8 - dy * 5, tipY - dy * 8 + dx * 5); ctx.lineTo(tipX - dx * 8 + dy * 5, tipY - dy * 8 - dx * 5); ctx.closePath(); ctx.fill();
  ctx.font = '600 10px Segoe UI, Arial, sans-serif'; ctx.textAlign = 'center';
  ctx.fillText(`${Math.round(weather.wind_kmh)} km/h`, cx, cy + 27);
}
// Playback length grows gently with run length: 24 h plays in 12 s, 72 h in 20 s.
const playbackMs = hours => 8000 + hours * 170;
// Minutes since the fire reached a spot -> colour and opacity. The front is a bright, nearly opaque glow; behind
// it the fire cools to a translucent ember-red haze, so the burned ground reads as smoke rather than paint.
const FIRE_RAMP = [[0, '#fff3b0', 255], [12, '#ffd166', 250], [45, '#ff9f1c', 240], [120, '#f3722c', 225],
                   [240, '#d62828', 190], [420, '#a4161a', 145], [600, '#6a040f', 105]];
const COOLED_BY = 600;
const FLICKER_UNTIL = 120;  // the burning edge shimmers
const rgb = colour => [1, 3, 5].map(i => parseInt(colour.slice(i, i + 2), 16));
const pack = ([r, g, b], a = 255) => ((a << 24) | (b << 16) | (g << 8) | r) >>> 0;  // ImageData is RGBA, little-endian
const mix = (a, b, t) => a.map((value, i) => Math.round(value + (b[i] - value) * t));
const FIRE_LUT = Array.from({length: COOLED_BY + 1}, (_, age) => {
  for (let i = 1; i < FIRE_RAMP.length; i++) {
    const [t0, c0, a0] = FIRE_RAMP[i - 1], [t1, c1, a1] = FIRE_RAMP[i];
    if (age <= t1) { const t = (age - t0) / (t1 - t0); return pack(mix(rgb(c0), rgb(c1), t), Math.round(a0 + (a1 - a0) * t)); }
  }
  return pack(rgb(FIRE_RAMP.at(-1)[1]), FIRE_RAMP.at(-1)[2]);
});
function buildSpreadRaster(cells) {
  // Grid of the burned cells with a one-cell unburned border, upsampled k times. Each sub-pixel gets an arrival
  // time interpolated from the burned cells around it, so the front sweeps across cells instead of popping them in,
  // and it is drawn where at least half its neighbourhood burned, which rounds the outline without growing it.
  const size = cells.size;
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (let i = 0; i < cells.count; i++) {
    minX = Math.min(minX, cells.x[i]); maxX = Math.max(maxX, cells.x[i]); minY = Math.min(minY, cells.y[i]); maxY = Math.max(maxY, cells.y[i]);
  }
  const west = minX - size, north = maxY + 2 * size;
  const columns = Math.round((maxX - minX) / size) + 3, rows = Math.round((maxY - minY) / size) + 3;
  const arrival = new Float32Array(rows * columns).fill(Infinity);
  for (let i = 0; i < cells.count; i++) {
    arrival[Math.round((north - cells.y[i] - size) / size) * columns + Math.round((cells.x[i] - west) / size)] = cells.minutes[i];
  }
  const k = Math.max(1, Math.min(4, Math.floor(Math.sqrt(1.5e6 / (rows * columns)))));  // at most ~1.5 M sub-pixels
  const w = columns * k, h = rows * k, time = new Float32Array(w * h).fill(Infinity);
  for (let r = 0; r < h; r++) {
    const v = (r + .5) / k - .5, r0 = Math.floor(v), fr = v - r0;
    for (let c = 0; c < w; c++) {
      const u = (c + .5) / k - .5, c0 = Math.floor(u), fc = u - c0;
      let cover = 0, sum = 0;
      const take = (rr, cc, weight) => {
        if (weight <= 0 || rr < 0 || cc < 0 || rr >= rows || cc >= columns) return;
        const a = arrival[rr * columns + cc];
        if (a !== Infinity) { cover += weight; sum += a * weight; }
      };
      take(r0, c0, (1 - fr) * (1 - fc)); take(r0, c0 + 1, (1 - fr) * fc); take(r0 + 1, c0, fr * (1 - fc)); take(r0 + 1, c0 + 1, fr * fc);
      if (cover >= .5) {
        time[r * w + c] = sum / cover;
      }
    }
  }
  const raster = document.createElement('canvas'); raster.width = w; raster.height = h;
  const context = raster.getContext('2d'), image = context.createImageData(w, h);
  return {canvas: raster, context, image, pixels: new Uint32Array(image.data.buffer), time,
          west, north, widthM: columns * size, heightM: rows * size, drawnAt: null};
}
function renderSpreadRaster(now) {
  const raster = state.spreadRaster;
  if (raster.drawnAt === now) return;
  const {time, pixels} = raster, phase = now * .35;
  for (let i = 0; i < time.length; i++) {
    const t = time[i];
    if (t > now) { pixels[i] = 0; continue; }
    const age = now - t;
    if (age >= COOLED_BY) { pixels[i] = FIRE_LUT[COOLED_BY]; continue; }
    if (age >= FLICKER_UNTIL) { pixels[i] = FIRE_LUT[age | 0]; continue; }
    // Shimmer: look up a slightly younger or older colour, varying smoothly in space and time.
    const wobble = Math.sin(i * 0.731 + phase) * Math.sin(i * 0.177 - phase * .6) * 18 * (1 - age / FLICKER_UNTIL);
    pixels[i] = FIRE_LUT[Math.max(0, Math.min(COOLED_BY, age + wobble)) | 0];
  }
  raster.context.putImageData(raster.image, 0, 0);
  raster.drawnAt = now;
}
const SEED_AREA_HA = 0.81;       // the 90 m start cell
const compass = degrees => ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'][Math.round(((degrees % 360) + 360) % 360 / 45) % 8];
function spreadAreaAt(minutes) {
  // Area burned by the end of each hour comes from the 90 m grid; interpolate within the hour.
  const byHour = state.spread.area_by_hour_ha || [];
  if (!byHour.length) return null;
  const hour = Math.floor(minutes / 60), before = hour === 0 ? SEED_AREA_HA : byHour[Math.min(hour, byHour.length) - 1];
  const after = byHour[Math.min(hour, byHour.length - 1)];
  return before + (after - before) * (minutes / 60 - hour);
}
function updateSpreadClock() {
  const spread = state.spread, minutes = state.spreadTime;
  const [day, clock] = spread.start.local_standard_time.split(' ');
  const [y, mo, d] = day.split('-').map(Number), [h, mi] = clock.split(':').map(Number);
  const local = new Date(Date.UTC(y, mo - 1, d, h, mi) + minutes * 60000).toISOString().slice(0, 16).replace('T', ' ');
  const weather = spreadWeather(), area = spreadAreaAt(minutes);
  text('spread-clock', `+${Math.floor(minutes / 60)} h ${String(Math.floor(minutes % 60)).padStart(2, '0')} min · ${local} local` +
    (area == null ? '' : ` · ${number(Math.round(area * 10) / 10)} ha`) +
    (weather ? ` · wind ${Math.round(weather.wind_kmh)} km/h from ${compass(weather.wind_from_deg)}` : ''));
  $('spread-time').value = String(Math.round(minutes));
}
function setSpreadTime(minutes, ease = 1) {
  state.spreadTime = Math.max(0, Math.min(minutes, state.spread.start.hours * 60));
  if (state.followSpread && state.spreadCells) moveCamera(spreadView(state.spreadTime), ease);
  updateSpreadClock(); draw();
}
function pauseSpread() {
  if (state.spreadFrame) cancelAnimationFrame(state.spreadFrame);
  state.spreadFrame = null; $('spread-play').textContent = '▶'; $('spread-play').setAttribute('aria-label', 'Play the spread');
}
function playSpread() {
  if (!state.spread) return;
  const total = state.spread.start.hours * 60;
  if (state.spreadTime >= total) state.spreadTime = 0;  // replay from the start once finished
  pauseSpread();
  $('spread-play').textContent = '❚❚'; $('spread-play').setAttribute('aria-label', 'Pause the spread');
  let last = performance.now(), settling = 0;
  const duration = playbackMs(state.spread.start.hours);
  const step = now => {
    const elapsed = Math.min(now - last, 100); last = now;
    const ease = 1 - Math.exp(-elapsed / 280);  // the camera closes ~30% of the gap every 100 ms
    if (state.spreadTime < total) setSpreadTime(state.spreadTime + elapsed * total / duration, ease);
    else if (state.followSpread && settling++ < 60) { moveCamera(spreadView(total), ease); draw(); }
    else { pauseSpread(); return; }
    state.spreadFrame = requestAnimationFrame(step);
  };
  state.spreadFrame = requestAnimationFrame(step);
}
function showSpreadPlayer() {
  const total = state.spread.start.hours * 60;
  $('spread-time').max = String(total); $('spread-time').step = '10';
  $('spread-player').hidden = !state.spread.spread;
  state.spreadTime = 0; state.followSpread = true; moveCamera(spreadView(0), 1); updateSpreadClock(); draw();
  if (state.spread.spread && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) playSpread();
  else setSpreadTime(total);  // no animation for reduced motion: show the final state, scrubbable
}
function prepareSpread(result) {
  // Use the simulator's own 90 m cells when sent (close-ups look like a fire, not blocks); otherwise 375 m.
  const fine = result.fine_cells, n = fine ? fine.minutes.length : result.reached_cells.length;
  const arrival = i => fine ? fine.minutes[i] : result.reached_cells[i].minutes;
  const order = Array.from({length: n}, (_, i) => i).sort((a, b) => arrival(a) - arrival(b));
  const cells = {count: n, size: fine ? fine.pixel_m : 375, x: new Float64Array(n), y: new Float64Array(n), minutes: new Float64Array(n),
                 minX: new Float64Array(n), maxX: new Float64Array(n), minY: new Float64Array(n), maxY: new Float64Array(n)};
  order.forEach((source, i) => {
    if (fine) { cells.x[i] = fine.west + fine.cols[source] * fine.pixel_m; cells.y[i] = fine.north - (fine.rows[source] + 1) * fine.pixel_m; }
    else { cells.x[i] = result.reached_cells[source].x; cells.y[i] = result.reached_cells[source].y; }
    cells.minutes[i] = arrival(source);
    // Running extent of everything burned so far, for the camera.
    cells.minX[i] = Math.min(cells.x[i], i ? cells.minX[i - 1] : Infinity); cells.maxX[i] = Math.max(cells.x[i] + cells.size, i ? cells.maxX[i - 1] : -Infinity);
    cells.minY[i] = Math.min(cells.y[i], i ? cells.minY[i - 1] : Infinity); cells.maxY[i] = Math.max(cells.y[i] + cells.size, i ? cells.maxY[i - 1] : -Infinity);
  });
  return cells;
}
const CAMERA_MIN_HALF_M = 1000;  // never closer than a 2 km wide view
const PLAYER_BAR_PX = 70;        // the playback bar covers the bottom of the map
function spreadView(minutes) {
  // Frame everything burned by `minutes` (and the start point) with a margin, in the part of the map above the bar.
  const cells = state.spreadCells, start = state.spread.start;
  let low = 0, high = cells.count;
  while (low < high) { const mid = (low + high) >> 1; if (cells.minutes[mid] <= minutes) low = mid + 1; else high = mid; }
  let minX = start.x_3978, maxX = start.x_3978, minY = start.y_3978, maxY = start.y_3978;
  if (low > 0) {
    minX = Math.min(minX, cells.minX[low - 1]); maxX = Math.max(maxX, cells.maxX[low - 1]);
    minY = Math.min(minY, cells.minY[low - 1]); maxY = Math.max(maxY, cells.maxY[low - 1]);
  }
  const half = Math.max(CAMERA_MIN_HALF_M, Math.max(maxX - minX, maxY - minY) / 2 * 1.3 + cells.size);
  const base = state.scale / state.zoom;
  const scale = Math.max(base * .65, Math.min(base * MAX_ZOOM, Math.min(width, height - PLAYER_BAR_PX) / (2 * half)));
  return {scale, cx: (minX + maxX) / 2, cy: (minY + maxY) / 2};
}
function moveCamera(target, ease) {
  // ease 1 jumps; below 1 moves that fraction of the way (zoom in log space, so it feels even).
  const base = state.scale / state.zoom, viewHeight = height - PLAYER_BAR_PX;
  const cx = (width / 2 - state.tx) / state.scale, cy = (state.ty - viewHeight / 2) / state.scale;
  const scale = state.scale * Math.pow(target.scale / state.scale, ease);
  const x = cx + (target.cx - cx) * ease, y = cy + (target.cy - cy) * ease;
  state.scale = scale; state.zoom = scale / base;
  state.tx = width / 2 - scale * x; state.ty = viewHeight / 2 + scale * y;
}
function stopFollowing() { state.followSpread = false; }
function spreadReady() {
  const ready = state.selected != null && !!state.day && !state.spreadRunning;
  for (const id of ['spread-hour', 'spread-hours', 'run-spread']) $(id).disabled = !ready;
  if (!state.spreadRunning && !state.spread) text('spread-status', state.selected == null ? 'Select a cell on the map or in the ranking first.'
    : `Ready to start a fire at the centre of ${state.grid.cells[state.selected].id} on ${state.day.date}.`);
}
function clearSpread() {
  pauseSpread();
  state.spread = null; state.spreadCells = null; state.spreadRaster = null; state.spreadTime = null; state.followSpread = false; state.spreadRequest = (state.spreadRequest || 0) + 1; state.spreadRunning = false;
  $('spread-summary').hidden = true; $('spread-legend').hidden = true; $('spread-detail').hidden = true; $('spread-player').hidden = true;
}
async function runSpread() {
  if (state.selected == null || !state.day) return;
  const index = state.selected, day = state.day.date, request = (state.spreadRequest || 0) + 1;
  clearSpread(); state.spreadRequest = request; state.spreadRunning = true; spreadReady();
  const params = new URLSearchParams({date: day, grid_id: state.grid.cells[index].id,
    start_hour: $('spread-hour').value, hours: $('spread-hours').value});
  text('spread-status', 'Running the FBP simulation… The first run at a new place downloads fuel, terrain and weather and can take a minute.');
  try {
    const result = await api(`/api/spread?${params}`);
    if (request !== state.spreadRequest || day !== state.day.date) return;
    state.spread = result; state.spreadCells = prepareSpread(result); state.spreadRaster = buildSpreadRaster(state.spreadCells);
    const s = result.summary, w = result.weather_at_start;
    $('spread-summary').replaceChildren(
      metric('Area burned', s.area_ha == null ? '—' : `${number(s.area_ha)} ha`),
      metric('Head run', `${number(s.head_distance_km)} km`),
      metric('Head direction', s.head_bearing_deg == null ? '—' : `${s.head_bearing_deg}°`),
      metric('Wind at start', `${number(w.wind_kmh)} km/h from ${w.wind_from_deg}°`),
      metric('ISI · BUI', `${w.isi ?? '—'} · ${w.bui ?? '—'}`));
    $('spread-summary').hidden = false;
    const swatchItem = (colour, label) => {
      const item = node('span'); const swatch = node('span', null, 'swatch'); swatch.style.background = colour;
      item.append(swatch, document.createTextNode(label)); return item;
    };
    $('spread-legend').replaceChildren(node('strong', 'Fire'),
      swatchItem('#ffd166', 'burning now'), swatchItem('#f3722c', 'cooling (1–3 h)'), swatchItem('#d62828', 'smouldering'),
      swatchItem('#6a040f70', 'burned (10 h+)'));
    $('spread-legend').hidden = !result.spread;
    const settings = result.settings;
    text('spread-detail', `Start ${result.start.local_standard_time} local standard time (${result.start.start_utc} UTC)` +
      (result.start.seed_shift_m ? `, moved ${number(result.start.seed_shift_m)} m to the nearest burnable cell` : '') +
      `. FBP rate × ${settings.ros_scale}, flank × ${settings.flank_scale}, tuned on ${settings.tune_years.join('–')} fires only. ` +
      `${result.inputs.fuel}. Weather: ${result.inputs.weather}. ${result.message || ''}`);
    $('spread-detail').hidden = false;
    const barely = result.spread && s.area_ha <= 1;
    text('spread-status', !result.spread ? result.message
      : barely ? `Little or no spread from ${state.grid.cells[index].id}: only the 90 m start cell burned. At the start, FFMC was ${w.ffmc ?? '—'} and ISI ${w.isi ?? '—'}. ` +
          (w.ffmc != null && w.ffmc < 75 ? 'Surface fuels were too damp to carry fire; fires rarely spread below FFMC 75.' : 'Wind and fuel gave a very slow spread rate.') +
          ' The spread uses the weather of the day itself; the inspector above shows the previous day\'s weather, which the ignition model uses, so a dry previous day can still be followed by a wet one.'
      : `Fire spread from ${state.grid.cells[index].id} for ${result.start.hours} h, playing on the map above. The view follows the fire; drag the time slider to scrub, or pan/zoom to take over. Reset view returns to the province.`);
    showSpreadPlayer();
  } catch (cause) {
    if (request === state.spreadRequest) text('spread-status', cause.message);
  } finally {
    if (request === state.spreadRequest) { state.spreadRunning = false; spreadReady(); }
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
    if (Math.hypot(event.offsetX - drag.startX, event.offsetY - drag.startY) > 5) { drag.moved = true; stopFollowing(); }
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
canvas.addEventListener('wheel', event => { event.preventDefault(); stopFollowing(); zoomAt(Math.exp(-event.deltaY * .0015), event.offsetX, event.offsetY); }, {passive: false});
canvas.addEventListener('keydown', event => {
  const moves = {ArrowLeft: [35, 0], ArrowRight: [-35, 0], ArrowUp: [0, 35], ArrowDown: [0, -35]};
  if (event.key in moves) { event.preventDefault(); const [x, y] = moves[event.key]; state.tx += x; state.ty += y; draw(); }
  if (event.key === '+' || event.key === '=') zoomAt(1.3);
  if (event.key === '-') zoomAt(1 / 1.3);
});
$('zoom-in').addEventListener('click', () => { stopFollowing(); zoomAt(1.4); });
$('zoom-out').addEventListener('click', () => { stopFollowing(); zoomAt(1 / 1.4); });
$('reset').addEventListener('click', () => { stopFollowing(); resetView(); });
$('date').addEventListener('change', event => loadDay(event.target.value));
for (const [id, offset] of [['previous', -1], ['next', 1]]) $(id).addEventListener('click', () => {
  const day = new Date(`${$('date').value}T12:00:00Z`); day.setUTCDate(day.getUTCDate() + offset); loadDay(day.toISOString().slice(0, 10));
});
$('threshold').addEventListener('change', event => { state.threshold = Number(event.target.value); renderMetrics(); renderRanking(); renderCell(); draw(); });
for (const id of ['observations', 'alerts-only']) $(id).addEventListener('change', draw);
$('ranking-filter').addEventListener('change', renderRanking);
$('run-spread').addEventListener('click', runSpread);
$('spread-play').addEventListener('click', () => state.spreadFrame ? pauseSpread() : playSpread());
$('spread-time').addEventListener('input', event => { pauseSpread(); setSpreadTime(Number(event.target.value)); });
$('download').addEventListener('click', event => { if (state.loading || !state.day) event.preventDefault(); });
new ResizeObserver(resize).observe(canvas.parentElement);

async function boot() {
  try {
    const [meta, grid] = await Promise.all([api('/api/metadata'), api('/api/grid')]);
    state.meta = meta; state.grid = grid; state.threshold = meta.policy.default_index;
    state.positions = new Map(grid.cells.map((cell, index) => [`${cell.x},${cell.y}`, index]));
    $('threshold').replaceChildren(...meta.policy.choices.map(choice => {
      const option = node('option', `${pct(choice.threshold, 4)}${choice.index === meta.policy.default_index ? ' · Illustrative default' : ''}`);
      option.value = choice.index; return option;
    }));
    $('threshold').value = state.threshold;
    $('limitations').replaceChildren(...meta.limitations.map(item => node('li', item)));
    text('verification', `${meta.model} · ${meta.feature_count} inputs · main export integrity verified. This is not a claim of validated replay-year performance.`);
    text('attribution', grid.attribution);
    const ranges = ['< ' + pct(meta.colour_breaks[0], 3), ...meta.colour_breaks.map(value => '≥ ' + pct(value, 3))];
    $('legend').replaceChildren(...colours.map((colour, i) => {
      const item = node('span'); const swatch = node('span', null, 'swatch'); swatch.style.background = colour;
      item.append(swatch, document.createTextNode(ranges[i])); return item;
    }));
    $('spread-hour').replaceChildren(...Array.from({length: 24}, (_, hour) => {
      const option = node('option', `${String(hour).padStart(2, '0')}:00${hour === 14 ? ' · afternoon peak' : ''}`);
      option.value = hour; return option;
    }));
    $('spread-hour').value = 14;
    resetView(); await loadDay(meta.default_date);
  } catch (cause) { error(cause.message); text('status', 'The demo could not start. Check the local server window.'); }
}
boot();
