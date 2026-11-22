import type { DebuggerEvent } from "../types";
import type { FrontierAxis, FrontierSource, XMetric, YMetric } from "./types";
import {
  computeParetoFrontier,
  extractPoints,
  requirePointAxes,
} from "./analysis";

const X_AXES: Record<XMetric, FrontierAxis> = {
  byteBudgetFraction: {
    metric: "byteBudgetFraction",
    label: "Bytes / byte allowance (%)",
    format: "percent",
  },
  byteCount: { metric: "byteCount", label: "Memory (bytes)" },
  tokenCount: { metric: "tokenCount", label: "Tokens used" },
  slotCount: { metric: "slotCount", label: "Slots used" },
};
const Y_AXES: Record<YMetric, FrontierAxis> = {
  writeShare: {
    metric: "writeShare",
    label: "Writes / (writes + prunes) (%) — operation proxy",
    format: "percent",
  },
  netWritesPerWrite: {
    metric: "netWritesPerWrite",
    label: "(writes − prunes) / writes (%) — operation proxy",
    format: "percent",
  },
  writeCount: { metric: "writeCount", label: "Total writes" },
};

/** Resolve measurement identities independently from labels and percentage display. */
export function prepareFrontier(
  events: DebuggerEvent[],
  source: FrontierSource,
) {
  const supplied = source.points !== undefined;
  const axes = supplied
    ? source.axes
    : {
        x: X_AXES[source.xMetric ?? "byteBudgetFraction"],
        y: Y_AXES[source.yMetric ?? "writeShare"],
      };
  if (!axes?.x?.metric?.trim() || !axes?.y?.metric?.trim()) {
    throw new Error("Frontier inputs require two named axes");
  }
  const points = supplied
    ? source.points
    : extractPoints(events, source.xMetric, source.yMetric);
  for (const point of points)
    requirePointAxes(point, axes.x.metric, axes.y.metric);
  return {
    analysis: computeParetoFrontier(points),
    axes: {
      x: {
        ...axes.x,
        label: axes.x.label ?? axes.x.metric,
        format: axes.x.format ?? "number",
      },
      y: {
        ...axes.y,
        label: axes.y.label ?? axes.y.metric,
        format: axes.y.format ?? "number",
      },
    },
  };
}
