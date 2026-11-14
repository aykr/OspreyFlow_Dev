// Batch expansion harness (ADR-151): `workingset/BatchExpansion.tsx` alone, following one job to its
// end against a stand-in of rules-b's route kept here. `a11y/every-harness.spec.ts` scans it with no
// query (one state: the job starting); `batch-expansion.spec.ts` scans each `?job=` state in the three
// looks. `?job=` picks the job's end: `done` (the default; the view opens), `refused`, `failed` (then
// done on a second try), `deleted` (done, its view since deleted), `forbidden` (a reader below
// Editor, the Conduit's sentence), `noright` (an account without the right), `overlimit` (done, its
// view past the canvas's limit), `trouble` (its progress unread, still trying), `running` (it never
// ends), `following` (a job of the reader's already running here, the 409). Each stage's
// words are the route's own sentences. `?step=1`: the job moves on only when the spec sets
// `window.__BATCH__.stage` (0 queued, 1-3 the stages, 4 its end), so each stage stands until it has
// been read rather than for one poll's length. What was sent and opened are on `window.__BATCH__`.
import { useState } from "react";
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import type { CaseViewOpened } from "../src/views/viewsApi";
import { BatchExpansion } from "../src/workingset/BatchExpansion";
import type { BatchExpansionRequest } from "../src/workingset/batchExpansionApi";
import { applyHarnessBrand } from "./brandHarness";

declare global {
  interface Window {
    __BATCH__?: { sent: { method: string; path: string }[]; opened: string | null; closed: boolean; stage: number };
  }
}

const params = new URLSearchParams(window.location.search);
const end = params.get("job") ?? "done";
const VIEW = { id: "v-batch", case_id: "c1", name: "Expansion of Ledger Holdings Ltd", created_by: "alice", created_at: "2026-11-14T10:00:00Z", shared: false, chosen: null };
const OPENED = { view: VIEW, nodes: [{ id: "n1", type: "Organisation" }], edges: [], layout: {}, missing: 0 };
const QUEUED = "Waiting for the batch expansion to start.";
const STAGES = ["Expanding from 12 nodes.", "Counting the links among 41,203 nodes.", "Saving the view."];
const job = (state: string, words: string, more: Record<string, unknown> = {}) =>
  ({ id: end === "following" ? "j-running" : "j1", state, words, view: null, nodes: null, links: null, refusal: null, ...more });
const ENDS: Record<string, ReturnType<typeof job>> = {
  overlimit: job("done", "Saved 58,000 nodes and 131,940 links as your private view “Expansion of Ledger Holdings Ltd”.", { view: VIEW, nodes: 58_000, links: 131_940 }),
  done: job("done", "Saved 41,203 nodes and 96,114 links as your private view “Expansion of Ledger Holdings Ltd”.", { view: VIEW, nodes: 41_203, links: 96_114 }),
  refused: job("refused", "Too many for a batch expansion: 812,000 nodes against a limit of 500,000, so nothing was saved. Narrow it by link type, depth or dates and try again.",
    { refusal: { code: "too_many_nodes", cap_kind: "nodes", cap: 500_000, would_be: 812_000 } }),
  failed: job("failed", "The batch expansion could not finish, and nothing was saved. Try again, or narrow the expansion."),
  deleted: job("done", "The batch expansion finished, but the view it saved has since been deleted."),
};

window.__BATCH__ = { sent: [], opened: null, closed: false, stage: 0 };
const stepped = params.get("step") === "1";
const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
let starts = 0;
let reads = 0;

window.fetch = async (input: RequestInfo | URL, init: RequestInit = {}) => {
  const path = new URL(String(input)).pathname;
  const method = init.method ?? "GET";
  window.__BATCH__!.sent.push({ method, path });
  if (path === "/v1/investigations/c1/batch-expansions" && method === "POST") {
    starts += 1;
    reads = 0;
    if (end === "forbidden") return json(403, { detail: "You hold Reader in this case; this needs Editor." });
    if (end === "noright") return json(403, { detail: { error: "right_required", right: "investigate" } });
    if (end === "following") {
      return json(409, { error: "batch_expansion_running", id: "j-running",
        detail: "A batch expansion of yours is already running in this case, so another was not started. Follow that one, or wait for it to finish." });
    }
    return json(202, job("queued", QUEUED));
  }
  if (/^\/v1\/investigations\/c1\/batch-expansions\/[^/]+$/.test(path)) {
    reads += 1;
    if (end === "trouble" && reads > 1) return json(503, {});
    const at = stepped ? window.__BATCH__!.stage : reads;
    if (stepped && at === 0) return json(200, job("queued", QUEUED));
    if (at <= STAGES.length || end === "running" || end === "following") {
      return json(200, job("running", STAGES[Math.min(at, STAGES.length) - 1]!));
    }
    // A failed job's second try runs to done.
    return json(200, end === "failed" && starts > 1 ? ENDS.done : (ENDS[end] ?? ENDS.done));
  }
  if (path === "/v1/investigations/c1/views/v-batch") {
    return end === "overlimit"
      ? json(409, { error: "limit_exceeded", cap_kind: "nodes", cap: 50_000, would_be: 58_000, options: ["save_as_view", "filter", "promote_to_batch"] })
      : json(200, OPENED);
  }
  return json(404, {});
};

const REQUEST: BatchExpansionRequest = {
  nodeId: "n1",
  edgeType: "OWNS",
  depth: 2,
  refused: { error: "limit_exceeded", cap_kind: "nodes", cap: 50_000, would_be: 61_200, options: ["save_as_view", "filter", "promote_to_batch"] },
};

function Harness() {
  const [open, setOpen] = useState(true);
  const [opened, setOpened] = useState<string | null>(null);
  return (
    <>
      {opened && <p>The lens shows the view “{opened}”.</p>}
      {open && (
        <BatchExpansion
          request={REQUEST}
          apiBaseUrl={window.location.origin}
          bearerToken="harness"
          investigationId="c1"
          pollMs={Number(params.get("poll") ?? 150)}
          onViewOpened={(view: CaseViewOpened) => {
            window.__BATCH__!.opened = view.view.id;
            setOpened(view.view.name);
          }}
          onClose={() => {
            window.__BATCH__!.closed = true;
            setOpen(false);
          }}
        />
      )}
    </>
  );
}

void applyHarnessBrand().then(() => createRoot(document.getElementById("root")!).render(<Harness />));
