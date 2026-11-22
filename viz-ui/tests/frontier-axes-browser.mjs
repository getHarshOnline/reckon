import assert from "node:assert/strict";
import { dirname, resolve } from "node:path";
import { pathToFileURL, fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const workspace = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const application = resolve(workspace, "packages/debugger");
const { createServer, loadConfigFromFile } = await import(
  pathToFileURL(resolve(application, "node_modules/vite/dist/node/index.js"))
    .href
);
const { config } = await loadConfigFromFile(
  { command: "serve", mode: "test" },
  resolve(application, "vite.config.ts"),
);
const server = await createServer({
  ...config,
  configFile: false,
  root: application,
  resolve: {
    ...config.resolve,
    alias: {
      ...config.resolve?.alias,
      "@rtepl/reckon-components": resolve(
        workspace,
        "packages/components/src/index.ts",
      ),
    },
  },
  server: { host: "127.0.0.1", port: 0, strictPort: true, open: false },
});
let browser;
try {
  await server.listen();
  const address = server.httpServer.address();
  const url = new URL(
    "/tests/frontier-axes.html",
    `http://127.0.0.1:${address.port}`,
  );
  browser = await chromium.launch({
    executablePath: process.env.RECKON_CHROMIUM,
    args: ["--disable-background-networking"],
  });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    serviceWorkers: "block",
  });
  await context.route("**/*", (route) =>
    new URL(route.request().url()).origin === url.origin
      ? route.continue()
      : route.abort(),
  );
  const page = await context.newPage();
  page.setDefaultTimeout(7000);
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(url.href);
  async function chart() {
    await page.waitForFunction(
      () => document.querySelector(".js-plotly-plot")?.data?.length > 0,
    );
    return page.locator(".js-plotly-plot").evaluate((el) => ({
      xLabel: el.layout.xaxis.title.text,
      yLabel: el.layout.yaxis.title.text,
      traces: el.data.map(({ name, x, y, error_y }) => ({
        name,
        x,
        y,
        errors: error_y?.array,
      })),
    }));
  }
  const result = await chart();
  assert.equal(result.yLabel, "Mean return");
  assert.deepEqual(result.traces[0].x, [0, 2]);
  assert.deepEqual(result.traces[0].y, [0, 7.5]);
  assert.deepEqual(result.traces[0].errors, [0, 0.5]);
  assert.deepEqual(
    result.traces.find((t) => t.name === "You Are Here (A)").y,
    [7.5],
  );
  await page.getByRole("button", { name: "Accuracy", exact: true }).click();
  const accuracy = await chart();
  assert.equal(accuracy.yLabel, "Final accuracy (%)");
  assert.deepEqual(accuracy.traces[0].y, [0, 75]);
  assert.deepEqual(accuracy.traces[0].errors, [0, 5]);
  assert.deepEqual(
    accuracy.traces.find((t) => t.name === "You Are Here (A)").y,
    [75],
  );
  await page.getByRole("button", { name: "Operations", exact: true }).click();
  const operations = await chart();
  assert.match(operations.yLabel, /operation proxy/);
  assert.deepEqual(operations.traces[0].x, [150]);
  assert.deepEqual(operations.traces[0].y, [80]);
  assert.deepEqual(errors, []);
  console.log(
    JSON.stringify(
      {
        chromium: browser.version(),
        mean_return: result,
        accuracy,
        operations,
      },
      null,
      2,
    ),
  );
} finally {
  try {
    await browser?.close();
  } finally {
    await server.close();
  }
}
