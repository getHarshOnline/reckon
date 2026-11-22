import type { DebuggerEvent, ParetoPoint } from "../types";
import type { ParetoAnalysis, XMetric, YMetric } from "./types";

export const getX = (point: ParetoPoint): number => point.x;
export const getY = (point: ParetoPoint): number => point.y;

/** Extract only coordinates supplied by events; operation ratios are proxies. */
export function extractPoints(
  events: DebuggerEvent[],
  xMetric: XMetric = "byteBudgetFraction",
  yMetric: YMetric = "writeShare",
): ParetoPoint[] {
  const points: ParetoPoint[] = [];
  for (const event of events) {
    const usage = event.finalUsage;
    let x: number | undefined;
    let y: number | undefined;
    switch (xMetric) {
      case "byteBudgetFraction": {
        const allowance = event.initialBudget?.maxBytes;
        if (
          usage &&
          allowance !== undefined &&
          Number.isFinite(usage.byteCount) &&
          Number.isFinite(allowance) &&
          allowance > 0
        )
          x = usage.byteCount / allowance;
        break;
      }
      case "byteCount":
        x = usage?.byteCount;
        break;
      case "tokenCount":
        x = usage?.tokenCount;
        break;
      case "slotCount":
        x = usage?.slotCount;
        break;
    }
    const writes = event.totalWrites;
    const prunes = event.totalPrunes;
    switch (yMetric) {
      case "writeCount":
        y = writes;
        break;
      case "writeShare":
        if (
          writes !== undefined &&
          prunes !== undefined &&
          Number.isFinite(writes) &&
          Number.isFinite(prunes) &&
          Number.isFinite(writes + prunes) &&
          writes + prunes > 0
        )
          y = writes / (writes + prunes);
        break;
      case "netWritesPerWrite":
        if (
          writes !== undefined &&
          prunes !== undefined &&
          Number.isFinite(writes) &&
          Number.isFinite(prunes) &&
          writes > 0
        )
          y = (writes - prunes) / writes;
        break;
    }
    if (
      x === undefined ||
      y === undefined ||
      !Number.isFinite(x) ||
      !Number.isFinite(y)
    )
      continue;
    points.push({
      x,
      y,
      xMetric,
      yMetric,
      label: event.episodeId || event.eventId,
      episodeId: event.episodeId,
      isPareto: false,
    });
  }
  return points;
}

/** Refuse missing or mixed measurement identities before comparing coordinates. */
export function requirePointAxes(
  point: ParetoPoint,
  xMetric: string,
  yMetric: string,
): void {
  if (
    !xMetric?.trim() ||
    !yMetric?.trim() ||
    point.xMetric !== xMetric ||
    point.yMetric !== yMetric
  ) {
    throw new Error("Frontier points require matching named axes");
  }
  if (!Number.isFinite(point.x) || !Number.isFinite(point.y)) {
    throw new Error(
      "Frontier points require finite cost and outcome coordinates",
    );
  }
}

/** Minimise cost, maximise outcome; dominance needs at least one strict gain. */
export function computeParetoFrontier(points: ParetoPoint[]): ParetoAnalysis {
  const axes = points[0];
  const sorted = points
    .map((point) => {
      requirePointAxes(point, axes!.xMetric, axes!.yMetric);
      return { ...point, isPareto: false };
    })
    .sort((a, b) => getX(a) - getX(b) || getY(b) - getY(a));
  let bestAtLowerCost = -Infinity;
  for (let first = 0; first < sorted.length;) {
    const bestHere = getY(sorted[first]!);
    let end = first;
    while (end < sorted.length && getX(sorted[end]!) === getX(sorted[first]!)) {
      sorted[end]!.isPareto =
        getY(sorted[end]!) === bestHere && bestHere > bestAtLowerCost;
      end++;
    }
    bestAtLowerCost = Math.max(bestAtLowerCost, bestHere);
    first = end;
  }
  return {
    points: sorted,
    frontierPoints: sorted.filter((p) => p.isPareto),
    dominatedPoints: sorted.filter((p) => !p.isPareto),
  };
}
