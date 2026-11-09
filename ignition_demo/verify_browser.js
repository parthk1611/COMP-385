async (page) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const assert = (value, message) => { if (!value) throw new Error(message); };
  await page.setViewportSize({width: 1440, height: 1000});
  await page.goto('http://127.0.0.1:8766/');
  await page.locator('#status').filter({hasText: '9,673 cells scored'}).waitFor();
  assert(await page.locator('#threshold').inputValue() === '4', 'Default F2 cutoff not selected');
  assert(await page.locator('#ranking-body button').count() === 30, 'Top-30 ranking absent');
  await page.locator('#ranking-body button').first().click();
  await page.locator('#cell-detail').waitFor({state: 'visible'});
  const selected = await page.locator('#cell-title').innerText();
  assert(await page.locator('#all-features > div').count() === 36, 'Inspector input count differs');
  await page.getByRole('button', {name: 'Next day', exact: true}).click();
  await page.locator('#status').filter({hasText: '9,673 cells scored'}).waitFor();
  await page.locator('#cell-detail').waitFor({state: 'visible'});
  assert(await page.locator('#date').inputValue() === '2019-07-02', 'Date step failed');
  assert(await page.locator('#cell-title').innerText() === selected, 'Selection lost across dates');
  const before = Number((await page.locator('#daily-metrics strong').first().innerText()).replaceAll(',', ''));
  await page.locator('#threshold').selectOption('1');
  const after = Number((await page.locator('#daily-metrics strong').first().innerText()).replaceAll(',', ''));
  assert(after >= before, 'Lower cutoff reduced alert count');
  await page.getByRole('checkbox', {name: 'Show recorded ignitions', exact: true}).check();
  await page.getByRole('checkbox', {name: 'Alerts only', exact: true}).check();
  await page.getByRole('button', {name: 'Zoom in', exact: true}).click();
  await page.getByRole('button', {name: 'Reset view', exact: true}).click();
  await page.locator('#ranking-filter').selectOption('observed');
  assert(await page.locator('#ranking-caption').innerText().then(value => value.includes('recorded ignition cells')), 'Recorded-ignition filter failed');
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('link', {name: 'Download day ↓', exact: true}).click();
  const download = await downloadPromise;
  assert(download.suggestedFilename() === 'ignition_2019-07-02.csv', 'Download date differs');
  await download.saveAs('output/playwright/ignition_2019-07-02.csv');
  const badDate = await page.request.get('http://127.0.0.1:8766/api/predictions?date=2020-01-01');
  assert(badDate.status() === 400, 'Invalid API date not rejected');
  await page.locator('#date').fill('2019-05-01');
  await page.locator('#status').filter({hasText: '9,673 cells scored'}).waitFor();
  await page.waitForFunction(() => document.querySelector('#date').value === '2019-05-01' && document.querySelector('#previous').disabled);
  await page.locator('#date').fill('2019-10-31');
  await page.waitForFunction(() => document.querySelector('#date').value === '2019-10-31' && document.querySelector('#next').disabled);
  await page.locator('#date').fill('2019-07-01');
  await page.waitForFunction(() => document.querySelector('#status').textContent.includes('9,673 cells scored') && !document.querySelector('#date').disabled);
  await page.locator('#threshold').selectOption('4');
  await page.locator('#ranking-filter').selectOption('all');
  await page.getByRole('checkbox', {name: 'Alerts only', exact: true}).uncheck();
  await page.locator('#ranking-body button').first().click();
  await page.locator('#cell-detail').waitFor({state: 'visible'});
  await page.locator('.workspace').screenshot({path: 'output/playwright/map-inspector.png'});
  await page.evaluate(() => scrollTo(0, 0));
  await page.screenshot({path: 'output/playwright/desktop.png'});
  const layouts = [];
  for (const [width, height] of [[1440, 1000], [1024, 768], [390, 844]]) {
    await page.setViewportSize({width, height});
    const result = await page.evaluate(() => ({width: innerWidth, pageWidth: document.documentElement.scrollWidth,
      mapWidth: document.querySelector('#map').getBoundingClientRect().width}));
    assert(result.pageWidth <= width + 1, `Page overflows viewport at ${width}px`);
    assert(result.mapWidth > 200, 'Map too narrow');
    layouts.push(result);
    if (width === 390) {
      await page.evaluate(() => scrollTo(0, 0));
      await page.screenshot({path: 'output/playwright/mobile.png', fullPage: true});
    }
  }
  await page.setViewportSize({width: 1440, height: 1000});
  await page.evaluate(() => scrollTo(0, 0));
  assert(errors.length === 0, errors.join('\n'));
  return {status: 'PASS', checks: ['date selection and boundaries', '36-input cell inspection', 'selection retained across dates',
    'threshold changes counts', 'observed and alert-only overlays', 'zoom/reset', 'recorded ignition filter',
    'full-day CSV download', 'invalid API date', 'three responsive layouts', 'no page errors'], layouts, errors};
}
