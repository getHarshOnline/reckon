import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import * as wire from "../../../../generated/reckon/core/v1/types";

// The same pre-rename v1 bytes are read independently by Python and TypeScript.
const cases = JSON.parse(
  readFileSync(
    new URL(
      "../../../../../src/tests/fixtures/historical_run_metrics_v1.json",
      import.meta.url,
    ),
    "utf8",
  ),
);

describe("historical v1 metrics", () => {
  for (const [index, sample] of cases.entries()) {
    it(`round trips old fields and presence, case ${index}`, () => {
      const bytes = Buffer.from(sample.metrics_hex, "hex");
      const metrics = wire.HistoricalRunMetricsV1.fromBinary(bytes);
      expect(
        Buffer.from(wire.HistoricalRunMetricsV1.toBinary(metrics)),
      ).toEqual(bytes);
      expect(wire.HistoricalRunMetricsV1.toJson(metrics)).toEqual(sample.json);
      expect(
        Buffer.from(
          wire.HistoricalRunMetricsV1.toBinary(
            wire.HistoricalRunMetricsV1.fromJson(sample.json),
          ),
        ),
      ).toEqual(bytes);
      const summaryBytes = Buffer.from(sample.summary_hex, "hex");
      const summary = wire.RunSummary.fromBinary(summaryBytes);
      expect(summary.metrics).toEqual(metrics);
      expect(Buffer.from(wire.RunSummary.toBinary(summary))).toEqual(
        summaryBytes,
      );
      expect(
        Buffer.from(
          wire.RunSummary.toBinary(
            wire.RunSummary.fromJson(wire.RunSummary.toJson(summary)),
          ),
        ),
      ).toEqual(summaryBytes);
      expect(metrics.causalPrecision).toBe(sample.json.causalPrecision);
      expect(metrics.usefulMemoryRate).toBe(sample.json.usefulMemoryRate);
    });
  }
  it("exposes the historical name without a current alias", () => {
    expect(wire.HistoricalRunMetricsV1.typeName).toBe(
      "reckon.core.v1.HistoricalRunMetricsV1",
    );
    expect(wire).not.toHaveProperty("RunMetrics");
  });
});
