import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const workspace = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const application = resolve(workspace, 'packages/debugger');
const python = process.env.RECKON_PYTHON ?? resolve(workspace, '../.venv/bin/python');
const samples = JSON.parse(execFileSync(python,
  [resolve(workspace, '../src/tests/test_native_record_wire.py')], { encoding: 'utf8' }));
const publicSamples = JSON.parse(execFileSync(python,
  [resolve(workspace, '../src/tests/test_native_public_record.py')], { encoding: 'utf8' }));
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
    executablePath: process.env.RECKON_CHROMIUM,
    channel: process.env.PLAYWRIGHT_CHANNEL,
    args: ['--disable-background-networking'],
  });
  const context = await browser.newContext({ viewport: { width: 900, height: 900 }, serviceWorkers: 'block' });
  await context.route('**/*', route => new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
  const page = await context.newPage();
  page.setDefaultTimeout(7000);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(`${origin}/tests/record-wire.html`);
  await page.waitForFunction(() => typeof window.inspectNativeRecord === 'function');
  const row = label => page.getByText(label, { exact: true }).locator('..');
  for (const [index, sample] of samples.entries()) {
    const result = await page.evaluate(bytes => window.inspectNativeRecord(bytes), sample);
    assert.deepEqual(result.encoded, sample, 'Generated TS must retain the native wire values');
    if (index > 1) {
      assert.match(result.error, /timestamp exceeds the viewer's exact integer range/);
      continue;
    }
    assert.equal(result.error, undefined);
    const record = result.record;
    assert.deepEqual(Object.values(record.payload), [0, 255, 128, ...Buffer.from('opaque')]);
    assert.deepEqual(Object.values(record.metadata), [255, 0, ...Buffer.from('metadata')]);
    assert.equal(record.compressed, true);
    assert.equal(record.encoding, 'producer-codec');
    assert.deepEqual(record.tags, ['second', 'first', 'second']);
    assert.equal(record.causalScore.ablationDelta, 0);
    assert.equal(record.causalScore.counterfactualDelta, -0.5);
    assert.equal(record.causalScore.influenceProxy, undefined);
    assert.equal(record.causalScore.lastEvaluated, 7);
    if (index === 0) {
      assert.deepEqual(record.provenance, { sourceOp: 'observe', inputIds: ['b', 'a'], hash: 'supplied' });
      assert.equal(record.createdAtStep, 0);
      assert.equal(record.createdAtSequence, undefined);
    } else {
      assert.equal(record.provenance, undefined);
      assert.equal(record.createdAtStep, undefined);
      assert.equal(record.createdAtSequence, 0);
    }
    await page.waitForFunction(id => document.body.textContent.includes(id), record.id);
    assert.match(await row('Timestamp').innerText(), new RegExp(`\\b${record.timestamp}$`));
    assert.match(await row('Ablation Delta').innerText(), /0\.0000$/);
    assert.match(await row('Counterfactual Delta').innerText(), /-0\.5000$/);
    assert.equal(await page.getByText('Influence (proxy)', { exact: true }).count(), 0);
    assert.equal(await page.getByText('second', { exact: true }).count(), 2);
  }
  for (const result of await page.evaluate(bytes => window.checkNativeIntegerLimits(bytes), samples[0])) {
    assert.ok(result.error.includes(`${result.field} exceeds the viewer's exact integer range`));
  }
  for (const [index, sample] of publicSamples.entries()) {
    if (index === 2) {
      await assert.rejects(page.evaluate(value => window.inspectPublicRecord(value), sample),
        /cost.tokens exceeds the viewer's exact integer range/);
      assert.equal(sample.cost.tokens, '9223372036854775807');
      continue;
    }
    const record = await page.evaluate(value => window.inspectPublicRecord(value), sample);
    await page.waitForFunction(id => document.body.textContent.includes(id), record.id);
    assert.equal(record.cost.tokens, index === 0 ? null : 0);
    assert.match(await row('Tokens').innerText(), index === 0 ? /Not recorded$/ : /\b0$/);
    assert.equal(record.createdAtStep, 0);
    assert.equal(record.createdAtSequence, undefined);
    assert.deepEqual(Object.values(record.payload), [0, 255, ...Buffer.from('opaque')]);
    assert.deepEqual(Object.values(record.metadata), [255, 0, ...Buffer.from('metadata')]);
    assert.deepEqual(record.tags, ['second', 'first', 'second']);
    assert.equal(record.causalScore.ablationDelta, 0);
    assert.equal(record.causalScore.influenceProxy, null);
    assert.match(await row('Ablation Delta').innerText(), /0\.0000$/);
  }
  assert.deepEqual(errors, []);
  console.log('Native manager → Rust JSON/TypeScript → inspector and historical wire passed; unknown, zero and unsafe counts remain distinct.');
} finally {
  await browser?.close();
  await server.close();
}
