// Run the copied build-directory version using the bundled artifact runtime.
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {Presentation, PresentationFile} from '@oai/artifact-tool';

const root = process.cwd();
const skill = process.env.IGNITION_PRESENTATION_SKILL_DIR;
const runtime = process.env.IGNITION_PRESENTATION_RUNTIME_DIR;
if (!skill || !runtime) {
  throw new Error('Set IGNITION_PRESENTATION_SKILL_DIR and IGNITION_PRESENTATION_RUNTIME_DIR to the bundled presentation tools before rebuilding the slides.');
}
process.env.RUNTIME_NODE_MODULES = path.join(runtime, 'node/node_modules');
const build = path.join(root, 'artifacts/ignition_demo/presentation-build');
const destination = path.join(root, 'docs/ignition_demo/presentation.pptx');
const evidence = JSON.parse(await fs.readFile(path.join(root, 'docs/ignition_demo/reconstruction_evidence.json'), 'utf8'));
const utils = await import(pathToFileURL(path.join(skill, 'container_tools/artifact_tool_utils.mjs')).href);
const deck = Presentation.create({slideSize: {width: 1280, height: 720}});
const font = 'Arial';
const ink = '#173d31', muted = '#52665c', paper = '#f7f8f3';

function textbox(slide, content, x, y, width, height, size = 26, colour = ink, bold = false) {
  const item = slide.shapes.add({geometry: 'textbox', name: content.slice(0, 40),
    position: {left: x, top: y, width, height}, fill: 'none', line: {fill: 'none', width: 0}});
  item.text = content;
  item.text.style = {fontFamily: font, fontSize: size, color: colour, bold};
  return item;
}
function slide(title, source, notes = '') {
  const s = deck.slides.add(); s.background.fill = paper;
  textbox(s, 'COMP 385   ONTARIO IGNITION ATLAS', 70, 30, 1100, 30, 16, muted);
  textbox(s, title, 70, 92, 1140, 110, 48, ink, true);
  textbox(s, String(deck.slides.items.length).padStart(2, '0'), 1150, 666, 60, 28, 16, muted);
  s.speakerNotes.text = `${notes}\n\nSources: ${source}`;
  return s;
}
function table(s, values, top, heights = 330, widths = [760, 380]) {
  const t = s.tables.add({rows: values.length, columns: values[0].length, left: 70, top,
    width: 1140, height: heights, columnWidths: widths, values});
  for (let r = 0; r < values.length; r++) for (let c = 0; c < values[0].length; c++) {
    const cell = t.getCell(r, c);
    cell.fill = r === 0 ? '#e0e9da' : paper;
    cell.text.style = {fontFamily: font, fontSize: 24, color: ink, bold: r === 0};
  }
  return t;
}

{
  const s = deck.slides.add(); s.background.fill = ink;
  textbox(s, 'COMP 385   HISTORICAL WILDFIRE MODELLING', 72, 64, 1136, 40, 18, '#c5d7c6');
  textbox(s, 'Ontario\nIgnition Atlas', 72, 175, 1136, 250, 88, '#ffffff', true);
  textbox(s, 'An interactive replay of daily ignition scores\nMay–October 2019', 76, 478, 1040, 105, 30, '#d8e4d2');
  textbox(s, 'Model reconstruction, risk mapping and alert decisions', 76, 635, 1100, 40, 20, '#c5d7c6');
  s.speakerNotes.text = 'Introduce the prediction as at least one recorded ignition per existing 10 km cell during a local calendar day. This is a historical demonstration. Sources: docs/ignition_demo/report.md; docs/modeling/final_report.md.';
}
{
  const s = slide('The prediction problem', 'docs/modeling/final_report.md; data/metadata/ignition_feature_selection_v1.json',
    'Explain that ignition and fire spread answer separate questions. Identifiers and outcome labels are excluded from model inputs.');
  table(s, [['Element', 'Definition'], ['Prediction unit', '10 km cell, one local day'], ['Demonstration grid', '9,673 cells in Ontario'],
    ['Historical full panel', '17,798,320 cell-days'], ['Approved model inputs', '36 source features']], 215, 350, [500, 640]);
  textbox(s, 'Calendar, terrain, prior-day weather and earlier fire history', 75, 605, 1120, 45, 26, muted);
}
{
  const s = slide('Rebuilding the selected model', 'artifacts/ignition_demo/reconstruction/freeze.json; docs/ignition_demo/reconstruction_evidence.json',
    'The exact audited CSV was recovered from gzip. Only the selected model was refitted. The original experiment records remain intact. The model was frozen before test scoring.');
  const steps = [
    ['Verified sources', 'Exact audited CSV and pinned CWFIS archive checksums'],
    ['Corrected inputs', 'Complete daily grids, past-only weather and explicit missingness'],
    ['Frozen model', '40 boosting iterations, seed 385, all 2010–2016 training rows'],
    ['Independent comparison', 'Published 2019 metrics and all eight confusion tables match']
  ];
  steps.forEach(([heading, detail], i) => {
    const y = 220 + i * 102;
    textbox(s, `${i + 1}. ${heading}`, 74, y, 1130, 43, 29, ink, true);
    textbox(s, detail, 111, y + 43, 1090, 45, 25, muted);
  });
}
{
  const s = slide('Exploring one cell and one day', 'output/playwright/map-inspector.png; scripts/ignition_demo/server.py',
    'Demonstrate date selection, map navigation and inspection. The screenshot uses the fixed July 1 default. Inputs are context rather than causal explanations. The photograph-like asset is an actual screenshot of the local application.');
  s.images.add({blob: new Uint8Array(await fs.readFile(path.join(root, 'output/playwright/map-inspector.png'))), contentType: 'image/png', alt: 'Actual Ontario ignition map with selected-cell score and weather inputs',
    fit: 'contain', position: {left: 70, top: 195, width: 1140, height: 430}});
  textbox(s, 'Fixed colours across dates. Recorded ignitions remain separate from inputs.', 75, 635, 1120, 35, 23, muted);
}
{
  const result = evidence.results['2019'];
  const s = slide('Ranking improves over prevalence', 'docs/modeling/final_test.json; docs/ignition_demo/reconstruction_evidence.json',
    'The plotted values are average precision and the natural-prevalence reference, expressed as fractions. The reconstructed and published metrics match exactly. ROC-AUC is not alert accuracy.');
  const chart = s.charts.add('bar', {position: {left: 75, top: 215, width: 720, height: 355},
    title: '2019 average precision', categories: ['Prevalence baseline', 'Reconstructed HGB'],
    series: [{name: 'Average precision', values: [Number(result.prevalence.toFixed(6)), Number(result.average_precision.toFixed(6))], fill: '#497957'}],
    hasLegend: false, barOptions: {direction: 'column', grouping: 'clustered'},
    xAxis: {title: '', textStyle: {fontFamily: font, fontSize: 20}},
    yAxis: {numberFormatCode: '0.000', textStyle: {fontFamily: font, fontSize: 18}, minimumScale: 0},
    dataLabels: {showValue: true, position: 'outEnd', numberFormatCode: '0.000000'},
    chartFill: paper, plotAreaFill: paper});
  utils.applyPresentationChartFont(chart, {fontFamily: font});
  textbox(s, result.average_precision.toFixed(6), 865, 250, 330, 80, 53, ink, true);
  textbox(s, 'Average precision', 870, 335, 320, 45, 24, muted);
  textbox(s, result.roc_auc.toFixed(4), 865, 420, 330, 80, 53, ink, true);
  textbox(s, 'ROC-AUC', 870, 505, 320, 45, 24, muted);
  textbox(s, 'Absolute alert precision remains low despite better ranking.', 75, 615, 1130, 60, 28, ink);
}
{
  const value = evidence.results['2019'].thresholds[evidence.policy.default_index];
  const s = slide('Default alert performance', 'docs/ignition_demo/reconstruction_evidence.json; docs/modeling/threshold_tradeoffs_2018.csv',
    'F2 chooses the best of eight frozen cutoffs using 2018 only. The full-precision cutoff is 0.01502367973189238. Inclusive comparisons flag scores equal to the cutoff. Operational costs and capacity are unspecified.');
  textbox(s, 'Cutoff 1.5024%, chosen using 2018 validation F2', 75, 200, 1130, 45, 27, muted);
  table(s, [['2019 outcome', 'Cell-days'], ['Correct alerts', value.true_positive.toLocaleString('en-CA')],
    ['False alerts', value.false_positive.toLocaleString('en-CA')], ['Missed ignitions', value.false_negative.toLocaleString('en-CA')],
    ['Correct non-alerts', value.true_negative.toLocaleString('en-CA')]], 265, 290, [760, 380]);
  textbox(s, `Precision ${(value.precision*100).toFixed(2)}%     Recall ${(value.recall*100).toFixed(2)}%     Alerts/day ${(value.alerts/184).toFixed(2)}`, 75, 600, 1130, 65, 29, ink, true);
}
{
  const s = slide('A historical demonstration with clear limits', 'docs/ignition_demo/report.md; docs/ignition_demo/demo_script.md',
    'Launch Start-IgnitionDemo.cmd, inspect one cell, compare cutoffs and export a date. Future live forecasting requires issue-time data, current validation, coverage/drift monitoring and an alert policy based on response costs and capacity.');
  textbox(s, 'Available now', 75, 215, 1100, 45, 31, ink, true);
  textbox(s, 'Verified reconstructed model, local prediction service, interactive risk map,\nalert comparisons, full-day exports and a learning walkthrough', 75, 270, 1120, 100, 28, muted);
  textbox(s, 'Claims remain bounded by the data', 75, 410, 1100, 45, 31, ink, true);
  textbox(s, 'Historical archive availability is unknown. The frozen grid uses event-informed\nedge selection. False alerts and missed ignitions remain substantial.\nLive forecasting needs a current pipeline and additional validation.', 75, 470, 1120, 135, 27, muted);
  textbox(s, 'Demo: choose a date, inspect a cell, compare cutoffs, download predictions', 75, 635, 1130, 35, 22, ink);
}

await fs.mkdir(build, {recursive: true});
for (let i = 0; i < deck.slides.items.length; i++) {
  const blob = await deck.export({slide: deck.slides.items[i], format: 'png', scale: 1});
  await fs.writeFile(path.join(build, `slide-${i+1}.png`), new Uint8Array(await blob.arrayBuffer()));
}
const candidate = path.join(build, 'candidate.pptx');
await (await PresentationFile.exportPptx(deck)).save(candidate);
const result = await utils.finalizePresentation({workspaceDir: root, candidatePath: candidate, finalPath: destination,
  pythonExecutable: path.join(runtime, 'python/python.exe'),
  integrityValidatorPath: path.join(skill, 'container_tools/inspect_presentation_package_integrity.py'),
  layoutValidatorPath: path.join(skill, 'container_tools/inspect_presentation_layout_geometry.py'),
  layoutArgs: ['--expected-slide-size-emu', '12192000,6858000', '--validate-bullet-geometry', '--validate-heading-fit',
    '--require-native-table-slide', '2', '--require-native-table-slide', '6'],
  explicitTotalSlideCount: 7, requiredNativeTableOwnerSlides: [2, 6], requiredNativeChartOwnerSlides: [5],
  fontPolicy: {basis: 'design', families: [font]}, verifyArtifactToolImport: true,
  materializeLiteralChartWorkbooks: true, receiptPath: path.join(build, 'validation.json')});
console.log(JSON.stringify({output: destination, slides: deck.slides.items.length, result}));
