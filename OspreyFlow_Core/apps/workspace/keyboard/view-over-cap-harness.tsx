// The view-over-the-cap dialog's keyboard harness (ADR-124 decision 2, `CLAUDE.md` rule 13): the real
// delta client, the real working-set store and `ViewOverCapGate`, the one component `App.tsx` renders
// too; the socket is a stand-in that `view-over-cap.spec.ts` speaks for the server, and the view
// routes are answered by the spec. What the client sent and which view was opened are on
// `window.__OVERCAP__`. The view opened is held as `App.tsx` holds it, with the Glass's own banner
// over it; the only other line that is not the Glass's is the ready marker.
import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { useStore } from "zustand/react";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { connectDeltaClient, type SocketLike } from "../src/workingset/deltaClient";
import { createWorkingSet } from "../src/workingset/store";
import { ViewOverCapGate } from "../src/workingset/ViewOverCapGate";
import { ViewLensBanner } from "../src/views/ViewLensBanner";
import { applyHarnessBrand } from "./brandHarness";

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

await applyHarnessBrand();

// `?state=form`: the dialog drawn with its *Save as a view* form open, for the axe scan of every
// harness (`a11y/every-harness.spec.ts`); the spec never uses it.
const drawForm = new URLSearchParams(window.location.search).get("state") === "form";

function Harness() {
  const within = useStore(workingSet.store, (s) => s.viewOverCap === null);
  // As `App.tsx` holds it: a view opened over the case, until *Back to the case*.
  const [lens, setLens] = useState<string | null>(null);
  useEffect(() => {
    if (!drawForm) return;
    workingSet.store.getState().setViewOverCap({
      error: "limit_exceeded",
      cap_kind: "nodes",
      cap: 50_000,
      would_be: 50_001,
      options: ["save_as_view", "filter", "promote_to_batch"],
    });
    requestAnimationFrame(() =>
      Array.from(document.querySelectorAll<HTMLButtonElement>("button"))
        .find((b) => b.textContent === "Save as a view")
        ?.click(),
    );
  }, []);
  return (
    <>
      {within && <p>The view is within the limit.</p>}
      {lens && <ViewLensBanner name={lens} shared={false} missing={0} onBack={() => setLens(null)} />}
      <ViewOverCapGate
        store={workingSet.store}
        requestResync={(last) => client.requestResync(last)}
        entityTypes={["Person", "Vehicle", "Organisation"]}
        apiBaseUrl="http://keyboard-test.invalid"
        bearerToken="unused"
        investigationId="c1"
        onViewOpened={(opened) => {
          window.__OVERCAP__!.opened.push(opened.view.id);
          setLens(opened.view.id);
        }}
        lensOpen={lens !== null}
      />
    </>
  );
}

createRoot(document.getElementById("root")!).render(<Harness />);
