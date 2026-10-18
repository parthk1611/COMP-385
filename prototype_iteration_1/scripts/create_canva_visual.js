const pptxgen = require('pptxgenjs');

const pptx = new pptxgen();
pptx.layout = 'LAYOUT_WIDE';
pptx.author = 'Ontario Wildfire Prediction Capstone';
pptx.subject = 'Dataset inventory, measured EDA findings, feature decisions, and proposed architecture';
pptx.title = 'Ontario Wildfire Data: Findings and System Architecture';
pptx.lang = 'en-CA';

const W = 13.333;
const H = 7.5;
const C = {
  forest: '163D30',
  dark: '172D24',
  moss: '5C8A5E',
  mint: 'DDEDDC',
  cream: 'F7F6F0',
  white: 'FFFFFF',
  muted: '52665A',
  line: 'D3DED2',
  gold: 'D99B3A',
  paleGold: 'F8EDD8',
  red: '9F5146',
  paleRed: 'F5E8E4',
};

function box(slide, x, y, w, h, fill, radius = 0.16, border = fill) {
  slide.addShape(pptx.ShapeType.roundRect, {
    x, y, w, h, radius,
    rectRadius: radius,
    fill: { color: fill },
    line: { color: border, width: 0.8 },
  });
}

function text(slide, value, x, y, w, h, size = 16, color = C.dark, bold = false, opts = {}) {
  slide.addText(value, {
    x, y, w, h, fontFace: opts.face || 'Aptos', fontSize: size,
    color, bold, margin: 0, breakLine: false,
    valign: opts.valign || 'mid', align: opts.align || 'left',
    fit: 'shrink',
    ...opts,
  });
}

function top(slide, section, title, sub) {
  slide.background = { color: C.cream };
  box(slide, 0, 0, W, 0.16, C.forest, 0);
  text(slide, section.toUpperCase(), 0.64, 0.43, 7, 0.22, 10, C.moss, true, { charSpacing: 2.5 });
  text(slide, title, 0.64, 0.78, 12, 0.65, 30, C.forest, true, { face: 'Aptos Display' });
  text(slide, sub, 0.66, 1.44, 12, 0.33, 13.3, C.muted);
}

function footer(slide, n, note) {
  slide.addShape(pptx.ShapeType.line, { x: 0.64, y: 7.08, w: 12.05, h: 0, line: { color: C.line, width: 1 } });
  text(slide, note, 0.66, 7.12, 11.6, 0.2, 8.4, C.muted);
  text(slide, String(n).padStart(2, '0'), 12.31, 7.12, 0.4, 0.2, 9, C.muted, true, { align: 'right' });
}

function circleLabel(slide, x, y, label, color) {
  slide.addShape(pptx.ShapeType.ellipse, { x, y, w: 0.45, h: 0.45, fill: { color }, line: { color } });
  text(slide, label, x, y + 0.005, 0.45, 0.44, 13, C.white, true, { align: 'center' });
}

function arrow(slide, x1, y1, x2, y2, color = C.moss, width = 2) {
  slide.addShape(pptx.ShapeType.line, {
    x: x1, y: y1, w: x2 - x1, h: y2 - y1,
    line: { color, width, endArrowType: 'triangle' },
  });
}

// Slide 1: source inventory
{
  const s = pptx.addSlide();
  top(s, 'The data', 'Four assigned datasets. One study area.',
    'Static context for an Ontario wildfire prediction project, profiled across the historical zone mask.');
  const items = [
    { n: '01', title: 'FBP fuel types', year: '2024 + 2026', body: '30 m categorical fuel maps\nSpruce · pine · mixedwood · grass · water', foot: 'Official 2025 raster not found', fill: C.mint, badge: C.forest },
    { n: '02', title: 'SCANFI v2', year: '2025', body: 'Canopy closure and height\nSeven tree-group closure layers', foot: 'Nine 30 m layers downloaded', fill: C.white, badge: C.moss },
    { n: '03', title: 'MRDEM DTM', year: 'Current product', body: '30 m terrain elevation\nDerive slope and aspect later', foot: '145 Ontario tiles downloaded', fill: C.white, badge: C.moss },
    { n: '04', title: 'Ontario zones', year: 'Historical boundary', body: '95 management-zone polygons\nUsed as the analysis mask', foot: '2005 effective dates', fill: C.paleGold, badge: C.gold },
  ];
  items.forEach((d, i) => {
    const x = 0.64 + i * 3.14;
    box(s, x, 2.05, 2.85, 3.43, d.fill, 0.17, C.line);
    circleLabel(s, x + 0.22, 2.30, d.n, d.badge);
    text(s, d.title, x + 0.23, 2.94, 2.4, 0.42, 20, C.forest, true);
    text(s, d.year, x + 0.23, 3.41, 2.4, 0.32, 12.5, C.moss, true);
    text(s, d.body, x + 0.23, 3.86, 2.39, 0.78, 12.5, C.dark, false, { breakLine: false });
    text(s, d.foot, x + 0.23, 4.91, 2.40, 0.31, 11, i === 0 ? C.red : C.muted, true);
  });
  box(s, 0.64, 5.79, 12.05, 0.85, C.forest);
  text(s, 'Scope', 0.94, 6.03, 1.0, 0.32, 15, C.white, true);
  text(s, '145 tiles per tiled layer  •  about 1.075 million km² mask  •  no fire-start or weather labels joined yet',
    2.08, 6.02, 10.0, 0.35, 15, C.white);
  footer(s, 1, 'Sources: official NRCan and Ontario open-data layers; local acquisition manifest, 2026-10-02.');
}

// Slide 2: measured findings
{
  const s = pptx.addSlide();
  top(s, 'Exploratory findings', 'What the Ontario-wide rasters show',
    '2024 fuel counts use every valid 30 m pixel; other values use a systematic ~300 m sample.');

  box(s, 0.64, 2.02, 6.12, 4.64, C.white, 0.17, C.line);
  text(s, 'FBP 2024: largest fuel classes', 0.95, 2.31, 5.5, 0.38, 18.5, C.forest, true);
  const bars = [
    ['Boreal spruce', 26.7, C.forest],
    ['Water', 16.4, '4E8FA9'],
    ['Matted grass', 10.1, C.gold],
    ['Aspen (2024 legend)', 9.8, C.moss],
    ['Leafless aspen', 8.6, '88A889'],
  ];
  bars.forEach((d, i) => {
    const y = 3.01 + i * 0.62;
    text(s, d[0], 0.96, y, 1.77, 0.26, 12.3, C.dark);
    box(s, 2.75, y + 0.01, 3.15, 0.24, 'E9EEE6', 0.06);
    box(s, 2.75, y + 0.01, 3.15 * d[1] / 30, 0.24, d[2], 0.06);
    text(s, `${d[1].toFixed(1)}%`, 6.04, y, 0.53, 0.27, 12.3, C.dark, true, { align: 'right' });
  });
  text(s, 'Denominator: 1.193 billion valid 2024 pixels within the mask.', 0.96, 6.25, 5.5, 0.20, 10.2, C.muted);

  const cards = [
    { x: 7.04, y: 2.02, num: '35.0%', label: 'mean canopy closure', detail: 'SCANFI 2025', fill: C.mint },
    { x: 9.95, y: 2.02, num: '13.65%', label: 'mean black spruce closure', detail: 'largest tree group', fill: C.white },
    { x: 7.04, y: 4.11, num: '0.882', label: 'closure–height correlation', detail: 'r across 11.9M locations', fill: C.white },
    { x: 9.95, y: 4.11, num: '250.5 m', label: 'mean elevation', detail: 'MRDEM sample', fill: C.paleGold },
  ];
  cards.forEach((d) => {
    box(s, d.x, d.y, 2.72, 1.89, d.fill, 0.17, C.line);
    text(s, d.num, d.x + 0.19, d.y + 0.25, 2.32, 0.61, 29, C.forest, true);
    text(s, d.label, d.x + 0.19, d.y + 1.00, 2.32, 0.39, 13, C.dark, true);
    text(s, d.detail, d.x + 0.19, d.y + 1.48, 2.32, 0.22, 10.8, C.muted);
  });
  footer(s, 2, 'Seven SCANFI species closure values sum exactly to total closure in the sample. 2026 fuel codes need their own legend.');
}

// Slide 3: feature decisions
{
  const s = pptx.addSlide();
  top(s, 'Feature decisions', 'What goes into the first feature table?',
    'These are data-informed candidates. Predictive importance needs dated fire-start labels.');
  const cols = [
    { x: 0.64, color: C.forest, pale: C.mint, head: 'PRIORITIZE', lead: 'Fuel + forest + terrain', rows: [
      'FBP class and neighborhood class shares',
      'Seven SCANFI species closure groups',
      'Elevation; derive slope and aspect',
    ] },
    { x: 4.86, color: C.gold, pale: C.paleGold, head: 'COMPARE LATER', lead: 'Correlated structure', rows: [
      'Total canopy closure = sum of species layers',
      'Tree height correlates with closure (r = 0.882)',
      'Keep only if it improves held-out prediction',
    ] },
    { x: 9.08, color: C.red, pale: C.paleRed, head: 'LIMIT / EXCLUDE', lead: 'Avoid misleading signals', rows: [
      'Do not use raw numeric FBP code as a quantity',
      'Historical zone ID is a reporting stratum',
      'No future-vintage rasters in past predictions',
    ] },
  ];
  cols.forEach((d) => {
    box(s, d.x, 2.10, 3.62, 3.76, d.pale, 0.17, C.line);
    box(s, d.x + 0.20, 2.34, 1.95, 0.42, d.color, 0.10);
    text(s, d.head, d.x + 0.33, 2.41, 1.68, 0.28, 11, C.white, true);
    text(s, d.lead, d.x + 0.22, 2.93, 3.15, 0.46, 18.5, C.forest, true);
    d.rows.forEach((r, i) => {
      circleLabel(s, d.x + 0.24, 3.65 + i * 0.65, String(i + 1), d.color);
      text(s, r, d.x + 0.83, 3.61 + i * 0.65, 2.51, 0.55, 11.8, C.dark);
    });
  });
  box(s, 0.64, 6.20, 12.05, 0.49, C.forest);
  text(s, 'Next data needed: dated ignitions, weather/FWI, lightning and access — all known before the prediction cutoff.',
    0.92, 6.31, 11.4, 0.25, 13, C.white, true);
  footer(s, 3, 'Special case: Fire Response Plan Area covers only northwestern Ontario; use only where date and coverage match.');
}

// Slide 4: proposed system and hierarchy
{
  const s = pptx.addSlide();
  top(s, 'Recommended architecture', 'From static maps to a dated risk map',
    'Build the data contract first, then add outcomes and time-varying predictors.');
  const stages = [
    { x: 0.64, title: '01  Versioned raw', body: 'FBP 2024 / 2026\nSCANFI v2 2025\nMRDEM + Ontario mask', status: 'AVAILABLE', fill: C.mint },
    { x: 3.74, title: '02  Spatial grid', body: 'Reproject + align\nCategorical / continuous rules\n2.5 km cell features', status: 'NEXT BUILD', fill: C.white },
    { x: 6.84, title: '03  Cell-day join', body: 'Ignition labels + cutoff\nWeather / FWI / lightning\nAccess and dated features', status: 'NEEDS DATA', fill: C.paleGold },
    { x: 9.94, title: '04  Risk product', body: 'EDA + leakage gate\nBaseline → LightGBM\nAPI → daily risk map', status: 'LATER', fill: C.white },
  ];
  stages.forEach((d, i) => {
    box(s, d.x, 2.12, 2.74, 2.66, d.fill, 0.17, C.line);
    text(s, d.title, d.x + 0.22, 2.43, 2.34, 0.40, 17.2, C.forest, true);
    text(s, d.body, d.x + 0.22, 3.05, 2.32, 0.93, 11.6, C.dark);
    box(s, d.x + 0.21, 4.19, 1.39, 0.32, i === 0 ? C.forest : (i === 2 ? C.gold : C.moss), 0.07);
    text(s, d.status, d.x + 0.31, 4.22, 1.18, 0.22, 9.2, C.white, true);
    if (i < 3) arrow(s, d.x + 2.78, 3.42, d.x + 3.07, 3.42, C.moss, 2.3);
  });

  text(s, 'Decision and handoff hierarchy', 0.65, 5.25, 6, 0.33, 17, C.forest, true);
  const roles = [
    ['IT Director', 0.64, C.forest],
    ['Research + Steward', 3.05, C.moss],
    ['Geo + Data Engineers', 6.17, C.moss],
    ['Analyst → ML Engineer', 9.29, C.moss],
  ];
  roles.forEach((r, i) => {
    box(s, r[1], 5.75, i === 0 ? 2.15 : 2.80, 0.67, i === 0 ? C.forest : C.mint, 0.12, C.line);
    text(s, r[0], r[1] + 0.17, 5.95, i === 0 ? 1.80 : 2.48, 0.25, 12.1, i === 0 ? C.white : C.dark, true);
    if (i < 3) arrow(s, r[1] + (i === 0 ? 2.19 : 2.84), 6.08, roles[i + 1][1] - 0.07, 6.08, C.moss, 1.5);
  });
  footer(s, 4, 'Solid availability applies to downloaded static inputs only. No live agents, cell-day table, labels, trained model or API yet.');
}

// Slide 5: model choice and prediction target
{
  const s = pptx.addSlide();
  top(s, 'Model design', 'Predict new fire starts in the next 24 hours',
    'One row = one 2.5 km Ontario cell at a fixed daily cutoff; output = calibrated start probability.');
  box(s, 0.64, 2.06, 12.05, 0.76, C.forest);
  text(s, 'Target', 0.93, 2.27, 1.06, 0.30, 16, C.white, true);
  text(s, 'At least one new ignition in that cell after the cutoff and before the next cutoff',
    2.08, 2.26, 9.95, 0.33, 16, C.white);
  const modelCards = [
    { x: 0.64, title: '01  Reference', model: 'Historical-rate baseline', note: 'Season + region only', fill: C.white, badge: C.moss },
    { x: 4.86, title: '02  Transparent', model: 'Logistic regression', note: 'Same dated features', fill: C.mint, badge: C.forest },
    { x: 9.08, title: '03  Candidate', model: 'LightGBM classifier', note: 'Nonlinear interactions + fuel class', fill: C.paleGold, badge: C.gold },
  ];
  modelCards.forEach((d) => {
    box(s, d.x, 3.16, 3.62, 2.18, d.fill, 0.17, C.line);
    text(s, d.title, d.x + 0.21, 3.43, 3.14, 0.30, 13, d.badge, true);
    text(s, d.model, d.x + 0.21, 3.95, 3.14, 0.44, 19, C.forest, true);
    text(s, d.note, d.x + 0.21, 4.73, 3.15, 0.30, 12, C.muted);
  });
  box(s, 0.64, 5.69, 12.05, 0.91, C.white, 0.14, C.line);
  text(s, 'Choose by evidence', 0.93, 5.91, 2.18, 0.33, 16.8, C.forest, true);
  text(s, 'Future-year + held-out-region performance  •  PR-AUC  •  recall at alert budget  •  probability calibration',
    3.17, 5.92, 8.98, 0.32, 13.1, C.dark);
  footer(s, 5, 'FBP and terrain describe fuel and landscape. Ignition labels and pre-cutoff weather/lightning are required to train this target.');
}

// Slide 6: training and daily scoring architecture
{
  const s = pptx.addSlide();
  top(s, 'System architecture', 'One feature builder, two execution paths',
    'The same source-version and cutoff rules must drive historical training and daily scoring.');
  box(s, 0.64, 2.03, 12.05, 0.81, C.forest);
  text(s, 'Shared foundation', 0.93, 2.24, 2.06, 0.31, 16, C.white, true);
  text(s, 'Immutable raw data + manifest → version-aware spatial alignment → 2.5 km static grid',
    3.01, 2.24, 9.09, 0.32, 14.6, C.white);

  const rows = [
    { y: 3.31, label: 'TRAIN', badge: C.gold, pale: C.paleGold,
      steps: ['Historical fire starts\n+ dated weather', 'Cell-day feature +\nfuture-start label', 'Year + geographic\nholdouts', 'Baseline / LightGBM\n+ calibration'] },
    { y: 4.82, label: 'DAILY', badge: C.moss, pale: C.mint,
      steps: ['Today’s pre-cutoff\nweather + lightning', 'Same feature builder\n+ approved model', 'Calibrated risk score\nper Ontario cell', 'Risk API + map\n+ drift monitoring'] },
  ];
  rows.forEach((r) => {
    box(s, 0.64, r.y, 1.12, 1.08, r.badge, 0.12);
    text(s, r.label, 0.84, r.y + 0.40, 0.77, 0.25, 12.8, C.white, true);
    r.steps.forEach((step, i) => {
      const x = 1.96 + i * 2.67;
      box(s, x, r.y, 2.39, 1.08, r.pale, 0.12, C.line);
      text(s, step, x + 0.17, r.y + 0.20, 2.03, 0.68, 11.8, C.dark, i === 3);
      if (i < 3) arrow(s, x + 2.42, r.y + 0.53, x + 2.65, r.y + 0.53, r.badge, 1.9);
    });
  });
  footer(s, 6, 'Training and serving are proposed, not implemented. Block future-dated rasters and any observations after each cutoff.');
}

pptx.writeFile({ fileName: 'reports/ontario_wildfire_findings_architecture.pptx' });
