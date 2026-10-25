// The view-over-the-cap dialog's keyboard harness (ADR-124 decision 2, `CLAUDE.md` rule 13): the real
// delta client, the real working-set store and `ViewOverCapGate`, the one component `App.tsx` renders
// too; the socket is a stand-in that `view-over-cap.spec.ts` speaks for the server, and the branch
// route is answered by the spec. What the client sent and which case was opened are on
// `window.__OVERCAP__`. The only line here that is not the Glass's is the ready marker.
import { createRoot } from "react-dom/client";
import { useStore } from "zustand/react";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { connectDeltaClient, type SocketLike } from "../src/workingset/deltaClient";
import { createWorkingSet } from "../src/workingset/store";
import { ViewOverCapGate } from "../src/workingset/ViewOverCapGate";

declare global {
  interface Window {
    __OVERCAP__?: { sent: string[]; opened: string[]; deliver: (message: unknown) => void };
  }
}

const workingSet = createWorkingSet();
const socket = {
  onopen: null,
  onclose: null,
  onerror: null,
  onmessage: null,
  send(data: string) {
    window.__OVERCAP__!.sent.push(data);
  },
  close() {},
} as SocketLike;
window.__OVERCAP__ = {
  sent: [],
  opened: [],
  deliver: (message) => socket.onmessage?.({ data: JSON.stringify(message) }),
};
const client = connectDeltaClient(() => socket, {
  onDelta: (delta) => workingSet.store.getState().applyDelta(delta),
  onViewOverCap: (wouldBe) => workingSet.store.getState().setViewOverCap(wouldBe),
});
socket.onopen?.();

function Harness() {
  const within = useStore(workingSet.store, (s) => s.viewOverCap === null);
  return (
    <>
      {within && <p>The view is within the limit.</p>}
      <ViewOverCapGate
        store={workingSet.store}
        requestResync={(last) => client.requestResync(last)}
        entityTypes={["Person", "Vehicle", "Organisation"]}
        apiBaseUrl="http://keyboard-test.invalid"
        bearerToken="unused"
        investigationId="c1"
        onBranchOpened={(id) => window.__OVERCAP__!.opened.push(id)}
      />
    </>
  );
}

createRoot(document.getElementById("root")!).render(<Harness />);
