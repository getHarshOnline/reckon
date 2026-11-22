import { useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ParetoFrontier,
  type DebuggerEvent,
  type ParetoPointWithUncertainty,
} from "@rtepl/reckon-components";

const event: DebuggerEvent = {
  eventId: "operation",
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
};

function Fixture() {
  const [mode, setMode] = useState("Return");
  const accuracy = mode === "Accuracy";
  const yMetric = accuracy ? "final_accuracy" : "mean_return";
  const point: ParetoPointWithUncertainty = {
    x: 2,
    y: accuracy ? 0.75 : 7.5,
    xMetric: "budget_slots",
    yMetric,
    isPareto: false,
    label: "candidate",
    xStd: 0,
    yStd: accuracy ? 0.05 : 0.5,
    trialCount: 3,
  };
  return (
    <>
      {["Return", "Accuracy", "Operations"].map((name) => (
        <button key={name} onClick={() => setMode(name)}>
          {name}
        </button>
      ))}
      <div style={{ width: 900, height: 600 }}>
        {mode === "Operations" ? (
          <ParetoFrontier key={mode} events={[event]} />
        ) : (
          <ParetoFrontier
            key={mode}
            events={[]}
            points={[{ ...point, x: 0, y: 0, label: "zero", yStd: 0 }, point]}
            axes={{
              x: { metric: "budget_slots", label: "Memory allowance (slots)" },
              y: {
                metric: yMetric,
                label: accuracy ? "Final accuracy (%)" : "Mean return",
                format: accuracy ? "percent" : "number",
              },
            }}
            youAreHereMarkers={{ measured: point, selected: point }}
          />
        )}
      </div>
    </>
  );
}
createRoot(document.getElementById("root")!).render(<Fixture />);
