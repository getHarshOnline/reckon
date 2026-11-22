import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdir, mkdtemp, readFile, rm } from "node:fs/promises";
import { createServer } from "node:net";
import { dirname, resolve, delimiter } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const workspace = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repository = resolve(workspace, "..");
await mkdir(resolve(repository, "experiments/runs"), { recursive: true });
const temporary = await mkdtemp(
  resolve(repository, "experiments/runs/viewer-browser-"),
);
const children = [];
let browser;

async function freePort() {
  const server = createServer();
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const port = server.address().port;
  await new Promise((resolve) => server.close(resolve));
  return port;
}

function start(command, args, options) {
  const child = spawn(command, args, {
    stdio: ["ignore", "pipe", "pipe"],
    ...options,
  });
  let output = "";
  child.stdout.on("data", (chunk) => {
    output = (output + chunk).slice(-8000);
  });
  child.stderr.on("data", (chunk) => {
    output = (output + chunk).slice(-8000);
  });
  child.on("error", (error) => {
    output += error.message;
  });
  children.push(child);
  return () => output;
}

async function ready(url, output) {
  for (let attempt = 0; attempt < 180; attempt++) {
    try {
      if ((await fetch(url)).ok) return;
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`Server did not become ready: ${url}\n${output()}`);
}

try {
  const apiPort = await freePort();
  const uiPort = await freePort();
  const api = `http://127.0.0.1:${apiPort}`;
  const python =
    process.env.RECKON_PYTHON ?? resolve(repository, ".venv/bin/python");
  const backendOutput = start(
    python,
    [
      "-m",
      "uvicorn",
      "kernel_fixture:app",
      "--host",
      "127.0.0.1",
      "--port",
      String(apiPort),
    ],
    {
      cwd: repository,
      env: {
        ...process.env,
        RECKON_VIZ_DATA_DIR: temporary,
        RECKON_VIZ_LOAD_FIXTURES: "0",
        PYTHONPATH: [
          resolve(repository, "src"),
          resolve(workspace, "tests"),
        ].join(delimiter),
      },
    },
  );
  const uiOutput = start(
    process.execPath,
    [
      resolve(workspace, "packages/debugger/node_modules/vite/bin/vite.js"),
      "preview",
      "--host",
      "127.0.0.1",
      "--port",
      String(uiPort),
      "--strictPort",
    ],
    {
      cwd: resolve(workspace, "packages/debugger"),
      env: process.env,
    },
  );
  await Promise.all([
    ready(`${api}/health`, backendOutput),
    ready(`http://127.0.0.1:${uiPort}`, uiOutput),
  ]);
  const { events: original } = await (
    await fetch(`${api}/fixture/produce`, { method: "POST" })
  ).json();
  assert.equal(original.length, 24);
  const imported = await fetch(`${api}/v1/runs/import`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      run_id: "imported",
      events_jsonl_bytes: original.map((e) => JSON.stringify(e)).join("\n"),
    }),
  });
  assert.equal(imported.status, 200);
  let live;
  for (let attempt = 0; attempt < 100 && !live; attempt++) {
    const { runs } = await (await fetch(`${api}/v1/runs`)).json();
    live = runs.find((run) => run.run_id.startsWith("live-"));
    if (!live) await new Promise((resolve) => setTimeout(resolve, 20));
  }
  assert.ok(live, "Live manager did not reach storage");
  const legacy = JSON.parse(
    await readFile(
      resolve(repository, "runs/_fixtures/golden_run_export.json"),
      "utf8",
    ),
  );
  assert.equal(
    (
      await fetch(`${api}/v1/runs/import`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(legacy),
      })
    ).status,
    200,
  );
  for (const [runId, success] of [
    ["measured-zero", 0],
    ["measured-positive", 0.625],
  ]) {
    const response = await fetch(`${api}/v1/runs/import`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        run_id: runId,
        summary: {
          task_name: runId,
          num_episodes: 8,
          metrics: { success_rate: success },
        },
        events_jsonl_bytes: original
          .map((event) => JSON.stringify(event))
          .join("\n"),
      }),
    });
    assert.equal(response.status, 200);
    assert.equal(
      (await (await fetch(`${api}/v1/runs/${runId}`)).json()).success_rate,
      success,
    );
  }
  assert.equal(live.success_rate, null);
  assert.equal(
    (await (await fetch(`${api}/v1/runs/imported`)).json()).success_rate,
    null,
  );
  browser = await chromium.launch({
    headless: true,
    ...(process.env.RECKON_CHROMIUM
      ? { executablePath: process.env.RECKON_CHROMIUM }
      : {}),
  });
  {
    const page = await browser.newPage({
      viewport: { width: 1440, height: 1000 },
    });
    page.setDefaultTimeout(10000);
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.route("**:8000/**", async (route) => {
      const response = await route.fetch({
        url: route
          .request()
          .url()
          .replace(/:\d+\//, `:${apiPort}/`),
      });
      await route.fulfill({
        response,
        headers: { ...response.headers(), "access-control-allow-origin": "*" },
      });
    });
    await page.addInitScript(
      ({ port }) => {
        // Inspect the labels actually drawn on the canvas across run changes.
        window.timelineAxisLabels = [];
        const context = CanvasRenderingContext2D.prototype;
        const fillRect = context.fillRect;
        context.fillRect = function (x, y, width, height) {
          if (x === 0 && y === 0 && width > 100 && height > 100)
            window.timelineAxisLabels = [];
          return fillRect.call(this, x, y, width, height);
        };
        const fillText = context.fillText;
        context.fillText = function (text, ...args) {
          if (this.font === "10px system-ui, monospace")
            window.timelineAxisLabels.push(text);
          return fillText.call(this, text, ...args);
        };
        const NativeWebSocket = window.WebSocket;
        window.WebSocket = class extends NativeWebSocket {
          constructor(url, protocols) {
            super(
              String(url).replace("localhost:8000", `127.0.0.1:${port}`),
              protocols,
            );
          }
        };
      },
      { port: apiPort },
    );
    await page.goto(`http://127.0.0.1:${uiPort}`, { waitUntil: "networkidle" });
    assert.ok(
      await page
        .locator("header")
        .evaluate(
          (element) => parseFloat(getComputedStyle(element).paddingLeft) > 0,
        ),
      "Global reset must not erase header spacing",
    );
    assert.ok(
      await page
        .locator("main")
        .evaluate(
          (element) => parseFloat(getComputedStyle(element).paddingTop) > 0,
        ),
      "Global reset must not erase panel spacing",
    );
    for (const runId of ["imported", live.run_id]) {
      await page.locator("select").selectOption(runId);
      await page.getByText("No event selected", { exact: true }).waitFor();
      await page.getByText("24 events", { exact: true }).first().waitFor();
      await page.waitForFunction(
        () =>
          window.timelineAxisLabels.length > 0 &&
          window.timelineAxisLabels.every((label) => label.startsWith("step ")),
      );
      for (let index = 0; index < original.length; index++) {
        await page
          .getByRole("button", { name: "Next event", exact: true })
          .click();
        await page
          .getByText(`Event ${index + 1} of 24`, { exact: true })
          .waitFor();
        const source = await page.locator("details pre").textContent();
        assert.deepEqual(JSON.parse(source), original[index]);
        await page
          .getByText("Not recorded (logical steps)", { exact: true })
          .waitFor();
        const timeValue = page.getByText("Not recorded (logical steps)", {
          exact: true,
        });
        assert.ok(
          await timeValue.evaluate(
            (element) => element.scrollWidth <= element.clientWidth,
          ),
          "The inspector must show the complete missing-time explanation",
        );
      }
      assert.equal(
        await page
          .getByRole("button", { name: "Next event", exact: true })
          .isDisabled(),
        true,
      );
      // Selection redraws on the next animation frame, after resetting the canvas.
      await page.waitForFunction(() => {
        const canvas = document.querySelector("canvas");
        const pixel = canvas?.getContext("2d")?.getImageData(1, 100, 1, 1).data;
        return pixel && [...pixel].join(",") === "26,26,46,255";
      });
      if (runId === live.run_id) {
        const { events } = await (
          await fetch(`${api}/fixture/read`, { method: "POST" })
        ).json();
        assert.equal(events.length, 1);
        await page.getByText("25 events", { exact: true }).first().waitFor();
        await page
          .getByRole("button", { name: "Next event", exact: true })
          .click();
        await page.getByText("Event 25 of 25", { exact: true }).waitFor();
        assert.deepEqual(
          JSON.parse(await page.locator("details pre").textContent()),
          events[0],
        );
      }
    }
    for (const [runId, label] of [
      ["measured-zero", "8 episodes | 0% success"],
      ["measured-positive", "8 episodes | 63% success"],
      ["imported", "0 episodes | Success unavailable"],
      [live.run_id, "0 episodes | Success unavailable"],
    ]) {
      await page.locator("select").selectOption(runId);
      await page.getByText(label, { exact: true }).waitFor();
      if (process.env.RECKON_BROWSER_SCREENSHOT && runId !== live.run_id)
        await page.screenshot({
          path: process.env.RECKON_BROWSER_SCREENSHOT.replace(
            /\.png$/,
            `-${runId}.png`,
          ),
          fullPage: true,
        });
    }
    await page.locator("select").selectOption(legacy.run_id);
    await page.getByText("10 events", { exact: true }).first().waitFor();
    await page.getByText("No event selected", { exact: true }).waitFor();
    for (let index = 0; index < 10; index++) {
      await page
        .getByRole("button", { name: "Next event", exact: true })
        .click();
      await page
        .getByText(`Event ${index + 1} of 10`, { exact: true })
        .waitFor();
    }
    await page.waitForFunction(
      () =>
        window.timelineAxisLabels.length > 0 &&
        window.timelineAxisLabels.every((label) => !label.startsWith("step ")),
    );
    await page.locator("select").selectOption("imported");
    await page.getByText("24 events", { exact: true }).first().waitFor();
    await page.waitForFunction(
      () =>
        window.timelineAxisLabels.length > 0 &&
        window.timelineAxisLabels.every((label) => label.startsWith("step ")),
    );
    await page.getByRole("button", { name: "Disconnect", exact: true }).click();
    await page.getByText("Disconnected", { exact: true }).waitFor();
    assert.deepEqual(errors, []);
    if (process.env.RECKON_BROWSER_SCREENSHOT)
      await page.screenshot({
        path: process.env.RECKON_BROWSER_SCREENSHOT,
        fullPage: true,
      });
    await page.close();
  }
  console.log(
    "Imported and live runs: all 24 actual kernel events visible and inspectable in order, including ID zero and tied steps; a subsequent live operation arrives, the bundled legacy export displays, disconnect works, and measured zero/positive success remains distinct from unavailable imported/live success.",
  );
} finally {
  if (browser) await browser.close();
  for (const child of children)
    if (child.exitCode === null) child.kill("SIGTERM");
  await Promise.all(
    children.map((child) =>
      child.exitCode === null
        ? new Promise((resolve) => child.once("exit", resolve))
        : Promise.resolve(),
    ),
  );
  await rm(temporary, { recursive: true, force: true });
}
