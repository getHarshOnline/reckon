import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import {
  DebuggerEventType,
  EdgeDisplayControl,
  EdgeDisplayMode,
  EdgeType,
  MultipleTestingMethod,
  PayloadType,
  TruthMode,
  type CausalEdge,
  type DebuggerEvent,
  type EdgeStatus,
  type MemoryRecord,
} from "@rtepl/reckon-components";
import { CausalGraphPanel } from "../src/features/causal-graph/CausalGraphPanel";
import { useDebuggerStore } from "../src/store";
import "../src/styles/globals.css";
import "@xyflow/react/dist/style.css";

const record = (id: string, order: number) =>
  ({
    id,
    timestamp: order,
    episodeId: "fixture",
    createdAtSequence: order,
    payloadType: PayloadType.OBSERVATION,
    provenance: { inputIds: [] },
    causalScore: {},
  }) as MemoryRecord;
const target: MemoryRecord = {
  ...record("target", 3),
  provenance: { ...record("target", 3).provenance, inputIds: ["a", "b"] },
  causalScore: { ...record("target", 3).causalScore, ablationDelta: -0.6 },
};
const snapshot = [record("a", 1), record("b", 2), target];
const event = (eventId: string): DebuggerEvent => ({
  eventId,
  snapshot,
  eventType: DebuggerEventType.STEP,
  wallTimeMs: 0,
  episodeId: "fixture",
  step: 1,
  memoryEvents: [],
  exceededDimension: "",
});
const inferred: CausalEdge = {
  id: "a->b",
  source: "a",
  target: "b",
  edgeType: EdgeType.INFERRED,
};
const probe: EdgeStatus = {
  edgeType: EdgeType.MEASURED,
  source: "a",
  target: "target",
  probeEvidence: {
    pValue: 0.003,
    qValue: 0.012,
    effectSize: -0.4,
    n: 50,
    correctionMethod: MultipleTestingMethod.BH_FDR,
    testType: "fixture",
    timestamp: 0,
    episodesUsed: 50,
    wallTimeSeconds: 1,
  },
};

useDebuggerStore.setState({ truthMode: TruthMode.RESEARCH });
function loadFixture() {
  useDebuggerStore.setState({
    events: [event("one"), event("two")],
    inferredEdges: [
      inferred,
      { ...inferred },
      { id: "b->a", source: "b", target: "a", edgeType: EdgeType.MEASURED },
      {
        id: "a->missing",
        source: "a",
        target: "missing",
        edgeType: EdgeType.INFERRED,
      },
    ],
    edgeStatuses: new Map([
      ["a->target", probe],
      ["b->target", { ...probe }],
      ["a->b", { ...inferred, inferredPath: ["a", "target", "b"] }],
    ]),
  });
}

function Fixture() {
  const [showControl, setShowControl] = useState(false);
  const [mode, setMode] = useState(EdgeDisplayMode.INCLUDE_UNMEASURED);
  const [requests, setRequests] = useState(0);
  return showControl ? (
    <div data-testid="probe-control" style={{ width: 500, padding: 20 }}>
      <EdgeDisplayControl
        mode={mode}
        onModeChange={setMode}
        inferredEdgeCount={2}
        unverifiedEdgeCount={2}
        onVerifyAll={() => setRequests((count) => count + 1)}
        verifyAllCostEpisodes={10}
        verifyAllCostSeconds={5}
        verificationQueue={{
          pendingProbes: 2,
          estimatedCostEpisodes: 20,
          estimatedCostSeconds: 9,
        }}
      />
      <output>Probe requests: {requests}</output>
    </div>
  ) : (
    <>
      <button onClick={loadFixture}>Load fixture</button>
      <button onClick={() => setShowControl(true)}>
        Show embedding probe controls
      </button>
      <div style={{ height: "95%" }}>
        <CausalGraphPanel />
      </div>
    </>
  );
}

createRoot(document.getElementById("root")!).render(<Fixture />);
