import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const workspace = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const application = resolve(workspace, 'packages/debugger');
const cases = JSON.parse(readFileSync(resolve(workspace, '../src/tests/fixtures/record_score_presence.json'), 'utf8'));
const { createServer, loadConfigFromFile } = await import(
  pathToFileURL(resolve(application, 'node_modules/vite/dist/node/index.js')).href
);
const { config } = await loadConfigFromFile(
  { command: 'serve', mode: 'test' }, resolve(application, 'vite.config.ts'),
);
const server = await createServer({
  ...config, configFile: false, root: application,
  resolve: { ...config.resolve, alias: {
    ...config.resolve?.alias,
    '@rtepl/reckon-components': resolve(workspace, 'packages/components/src/index.ts'),
  } },
  server: { host: '127.0.0.1', port: 0, strictPort: true, open: false },
});
let browser;
try {
  await server.listen();
  const origin = `http://127.0.0.1:${server.httpServer.address().port}`;
  browser = await chromium.launch({
    channel: process.env.PLAYWRIGHT_CHANNEL,
    args: ['--disable-background-networking'],
  });
  const context = await browser.newContext({ viewport: { width: 1000, height: 1000 }, serviceWorkers: 'block' });
  await context.route('**/*', route => new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
  const page = await context.newPage();
  page.setDefaultTimeout(7000);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(`${origin}/tests/record-scores.html`);
  await page.waitForFunction(() => typeof window.showScoreCases === 'function');
  const row = label => page.getByText(label, { exact: true }).locator('..');
  await page.waitForFunction(() => document.body.textContent.includes('Not recorded'));
  assert.match(await row('Proxy-only records in snapshot').innerText(), /Not recorded/);
  for (const sample of cases) {
    await page.evaluate(({ samples, selected }) => window.showScoreCases(samples, selected), { samples: cases, selected: sample.id });
    await page.waitForFunction(id => document.body.textContent.includes(id), sample.id);
    assert.match(await row('Proxy-only records in snapshot').innerText(), /\b2$/);
    assert.ok((await row('Attribution source').innerText()).includes(sample.source), sample.id);
    for (const [key, label] of [['ablationDelta', 'Ablation Delta'], ['counterfactualDelta', 'Counterfactual Delta'], ['influenceProxy', 'Influence (proxy)']]) {
      if (sample.score[key] != null) {
        assert.ok((await row(label).innerText()).includes(sample.score[key].toFixed(4)), sample.id);
      } else {
        assert.equal(await page.getByText(label, { exact: true }).count(), 0, sample.id);
      }
    }
  }
  await page.evaluate(samples => window.showScoreCases(samples.filter(sample => sample.source !== 'Proxy only'), 'ablation_zero'), cases);
  await page.waitForFunction(() => document.body.textContent.includes('ablation_zero'));
  assert.match(await row('Proxy-only records in snapshot').innerText(), /\b0$/);
  await page.evaluate(samples => window.showScoreCases([...samples, { id: 'missing_scores' }], 'missing_scores'), cases);
  await page.waitForFunction(() => document.body.textContent.includes('missing_scores'));
  assert.match(await row('Attribution source').innerText(), /Not recorded/);
  assert.match(await row('Proxy-only records in snapshot').innerText(), /Not fully recorded \(2 proxy-only identified\)/);
  assert.deepEqual(errors, []);
  console.log(`Inspector passed ${cases.length} shared cases, missing score data and absent snapshots.`);
} finally {
  await browser?.close();
  await server.close();
}
