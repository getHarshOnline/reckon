import { describe, expect, it } from "vitest";
import { computeParetoFrontier, extractPoints } from "./analysis";
import { prepareFrontier } from "./axes";
import type { FrontierSource } from "./types";
import type { DebuggerEvent, ParetoPoint } from "../types";

const point = (label: string, x: number, y: number): ParetoPoint => ({
  label,
  x,
  y,
  xMetric: "cost",
  yMetric: "outcome",
  isPareto: false,
});
const event = (overrides: Partial<DebuggerEvent> = {}): DebuggerEvent => ({
  eventId: "0",
  eventType: 2,
  wallTimeMs: 0,
  episodeId: "episode",
  step: 0,
  memoryEvents: [],
  exceededDimension: "",
  snapshot: [],
  initialBudget: { maxBytes: 100, maxSlots: 10, windowSize: 1 },
  finalUsage: { byteCount: 150, slotCount: 3, tokenCount: 0, opsInWindow: 0 },
  totalWrites: 4,
  totalPrunes: 1,
  ...overrides,
});

describe("cost and outcome frontier", () => {
  it("keeps measurement names separate from units and operation proxies", () => {
    const supplied = prepareFrontier([], {
      points: [point("zero", 0, 0), point("reward", 2, 7.5)],
      axes: {
        x: { metric: "cost" },
        y: { metric: "outcome", label: "Mean return" },
      },
    });
    expect(supplied.axes.y).toEqual({
      metric: "outcome",
      label: "Mean return",
      format: "number",
    });
    expect(supplied.analysis.frontierPoints.map((p) => p.y)).toEqual([0, 7.5]);
    const operations = prepareFrontier([event()], {});
    expect(operations.axes.y.metric).toBe("writeShare");
    expect(operations.axes.y.label).toMatch(/operation proxy/);
    expect(operations.analysis.points[0]).toMatchObject({
      xMetric: "byteBudgetFraction",
      yMetric: "writeShare",
      y: 0.8,
    });
  });

  it("requires consistent axes even for empty supplied comparisons", () => {
    expect(() =>
      prepareFrontier([], { points: [] } as unknown as FrontierSource),
    ).toThrow(/named axes/);
    expect(() =>
      prepareFrontier([], {
        xMetric: "probeEpisodes",
      } as unknown as FrontierSource),
    ).toThrow(/named axes/);
    expect(() =>
      computeParetoFrontier([
        point("a", 1, 2),
        { ...point("b", 2, 3), yMetric: "accuracy" },
      ]),
    ).toThrow(/matching named axes/);
    expect(() =>
      prepareFrontier([], {
        points: [point("a", 1, 2)],
        axes: {
          x: { metric: "cost" },
          y: { metric: "accuracy", format: "percent" },
        },
      }),
    ).toThrow(/matching named axes/);
  });

  it("matches strict dominance in either input order, keeping tied candidates", () => {
    const points = [
      point("weak", 1, 2),
      point("best", 1, 3),
      point("same", 1, 3),
      point("costlier", 2, 3),
      point("higher", 3, 4),
      point("cheap", 0, 1),
    ];
    for (const order of [points, [...points].reverse()]) {
      const expected = order
        .filter(
          (p) =>
            !order.some(
              (q) =>
                q.x! <= p.x! && q.y! >= p.y! && (q.x! < p.x! || q.y! > p.y!),
            ),
        )
        .map((p) => p.label)
        .sort();
      expect(
        computeParetoFrontier(order)
          .frontierPoints.map((p) => p.label)
          .sort(),
      ).toEqual(expected);
    }
    expect(points.every((p) => p.isPareto === false)).toBe(true);
  });

  it("rejects unavailable or non-finite supplied coordinates", () => {
    expect(() =>
      computeParetoFrontier([
        { ...point("missing", 0, 0), y: undefined } as unknown as ParetoPoint,
      ]),
    ).toThrow(/finite/);
    expect(() => computeParetoFrontier([point("invalid", NaN, 1)])).toThrow(
      /finite/,
    );
    expect(computeParetoFrontier([]).points).toEqual([]);
    expect(
      computeParetoFrontier([point("zero", 0, 0)]).frontierPoints,
    ).toHaveLength(1);
    expect(() =>
      computeParetoFrontier([
        {
          budget: 0,
          performance: 0,
          xMetric: "cost",
          yMetric: "outcome",
        } as unknown as ParetoPoint,
      ]),
    ).toThrow(/finite/);
  });

  it("keeps budget overruns and actual zero counts", () => {
    expect(extractPoints([event()])[0]).toMatchObject({ x: 1.5, y: 0.8 });
    expect(
      extractPoints([event({ totalWrites: 0 })], "tokenCount", "writeCount")[0],
    ).toMatchObject({ x: 0, y: 0 });
    expect(
      extractPoints(
        [event({ initialBudget: undefined })],
        "byteCount",
        "writeCount",
      )[0]?.x,
    ).toBe(150);
    expect(
      extractPoints(
        [event({ totalPrunes: 6 })],
        "byteCount",
        "netWritesPerWrite",
      )[0]?.y,
    ).toBe(-0.5);
  });

  it("does not invent zeros for missing task outcomes, counts, costs or denominators", () => {
    expect(extractPoints([event({ totalWrites: undefined })])).toEqual([]);
    expect(extractPoints([event({ totalWrites: 0, totalPrunes: 0 })])).toEqual(
      [],
    );
    expect(extractPoints([event({ initialBudget: undefined })])).toEqual([]);
    expect(
      extractPoints([
        event({ initialBudget: { maxBytes: 0, maxSlots: 10, windowSize: 1 } }),
      ]),
    ).toEqual([]);
  });
  it("refuses non-finite ratio inputs and an overflowed denominator", () => {
    expect(
      extractPoints([
        event({
          initialBudget: { maxBytes: Infinity, maxSlots: 10, windowSize: 1 },
        }),
      ]),
    ).toEqual([]);
    for (const totalPrunes of [Infinity, -Infinity, NaN]) {
      expect(extractPoints([event({ totalPrunes })])).toEqual([]);
      expect(
        extractPoints(
          [event({ totalPrunes })],
          "byteCount",
          "netWritesPerWrite",
        ),
      ).toEqual([]);
    }
    expect(extractPoints([event({ totalWrites: Infinity })])).toEqual([]);
    expect(
      extractPoints([
        event({ totalWrites: Number.MAX_VALUE, totalPrunes: Number.MAX_VALUE }),
      ]),
    ).toEqual([]);
  });
});
