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
    "/tests/pair-evidence.html",
    `http://127.0.0.1:${address.port}`,
  );
  browser = await chromium.launch({
    ...(process.env.RECKON_CHROMIUM
      ? { executablePath: process.env.RECKON_CHROMIUM }
      : {}),
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
  await page.getByText("No records to display.", { exact: false }).waitFor();
  await page.getByRole("button", { name: "Load fixture" }).click();

  const graphEdges = page.locator(".react-flow__edge");
  const legend = page.locator(".edge-legend");
  const display = page.locator(".edge-display-control");
  const results = [];
  const measured = ["a->target", "solid"];

  async function observe(mode, edges, impliedCount, proxyCount) {
    await page.waitForFunction(
      (count) =>
        document.querySelectorAll(".react-flow__edge").length === count,
      edges.length,
    );
    const graph = await graphEdges.evaluateAll((elements) =>
      elements
        .map((edge) => {
          const dash = edge.querySelector(".react-flow__edge-path").style
            .strokeDasharray;
          return [
            edge.dataset.id,
            dash.startsWith("8") ? "dashed" : dash ? "dotted" : "solid",
          ];
        })
        .sort((a, b) => a[0].localeCompare(b[0])),
    );
    const labels = (await legend.innerText()).trim().replace(/\s+/g, " ");
    assert.deepEqual(graph, edges, mode);
    assert.match(labels, /Measured\s*\(1\)/);
    if (impliedCount) assert.match(labels, /Implied \(unverified\)\s*\(1\)/);
    else assert.doesNotMatch(labels, /Implied/);
    if (proxyCount) assert.match(labels, /Proxy\s*\(1\)/);
    else assert.doesNotMatch(labels, /Proxy/);
    results.push({ mode, graph, legend: labels });
  }

  await observe("Research Measured", [measured], 0, 0);
  await page
    .locator('.react-flow__edge[data-id="a->target"]')
    .dispatchEvent("click");
  await page.getByText("Probe Evidence", { exact: true }).waitFor();
  await page
    .getByRole("status")
    .filter({ hasText: "Probe execution is unavailable" })
    .waitFor();
  assert.equal(
    await page.getByRole("button", { name: "Rerun Probe" }).count(),
    0,
  );

  await display
    .getByRole("button", { name: "All supplied", exact: true })
    .click();
  await observe(
    "Research All supplied",
    [["a->b", "dashed"], measured, ["b->target", "dotted"]],
    1,
    1,
  );
  await page
    .locator('.react-flow__edge[data-id="a->b"]')
    .dispatchEvent("click");
  await page.getByText("IMPLIED (UNVERIFIED)", { exact: true }).waitFor();
  await page
    .getByRole("status")
    .filter({ hasText: "Probe execution is unavailable" })
    .waitFor();
  assert.equal(
    await page.getByRole("button", { name: /^Verify Edge/ }).count(),
    0,
  );

  await display
    .getByRole("button", { name: "Probe status", exact: true })
    .click();
  await observe("Research Probe status", [measured], 0, 0);
  assert.equal(
    await page.getByText("IMPLIED (UNVERIFIED)", { exact: true }).count(),
    0,
  );

  await display
    .getByRole("button", { name: "All supplied", exact: true })
    .click();
  assert.equal(
    await page.getByText("IMPLIED (UNVERIFIED)", { exact: true }).count(),
    0,
  );
  await page.locator(".truth-mode-switch button").click();
  await page.getByRole("button", { name: "Show Legend" }).click();
  await observe("Product with All supplied selected", [measured], 0, 0);
  await page
    .getByText("Showing 0 implied (unverified) edges.", { exact: false })
    .waitFor();

  if (process.env.RECKON_BROWSER_SCREENSHOT)
    await page.screenshot({
      path: process.env.RECKON_BROWSER_SCREENSHOT,
      fullPage: true,
    });

  await page
    .getByRole("button", { name: "Show embedding probe controls" })
    .click();
  const embedding = page.getByTestId("probe-control");
  for (const [index, label] of ["All supplied", "Probe status"].entries()) {
    await embedding.getByRole("button", { name: label, exact: true }).click();
    await embedding.getByRole("button", { name: /^Run 2 probes/ }).click();
    await embedding
      .getByText("Confirm Verification", { exact: true })
      .waitFor();
    await embedding
      .getByRole("list")
      .getByText(index === 0 ? "~10 episodes" : "~20 episodes", { exact: true })
      .waitFor();
    await embedding
      .getByRole("list")
      .getByText(
        index === 0 ? "~5s estimated wall time" : "~9s estimated wall time",
        { exact: true },
      )
      .waitFor();
    if (process.env.RECKON_BROWSER_SCREENSHOT)
      await page.screenshot({
        path: process.env.RECKON_BROWSER_SCREENSHOT.replace(
          /\.png$/,
          `-confirmation-${index}.png`,
        ),
        fullPage: true,
      });
    await embedding
      .getByRole("button", { name: "Cancel", exact: true })
      .click();
    assert.equal(
      await embedding.locator("output").textContent(),
      `Probe requests: ${index}`,
    );
    await embedding.getByRole("button", { name: /^Run 2 probes/ }).click();
    await embedding
      .getByRole("button", { name: "Run Probes", exact: true })
      .click();
    await embedding
      .getByText(`Probe requests: ${index + 1}`, { exact: true })
      .waitFor();
    assert.equal(
      await embedding
        .getByText("Confirm Verification", { exact: true })
        .count(),
      0,
    );
  }
  assert.deepEqual(errors, []);
  console.log(
    JSON.stringify(
      {
        chromium: browser.version(),
        results,
        loaded_after_empty_graph: true,
        mismatched_probe_remained_proxy: true,
        label_only_measurement_hidden: true,
        absent_endpoint_hidden: true,
        probe_actions_explicitly_unavailable: true,
        hidden_edge_closed_drawer: true,
        optional_probe_callbacks_confirmed_in_both_views: true,
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
