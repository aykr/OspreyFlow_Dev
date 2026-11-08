// The Studio's *1 Model* tab's proposals block (ADR-143 decision 9; L3.5) on its own. The Conduit is a
// stand-in kept here, so the axe scan of every harness (`a11y/every-harness.spec.ts`) sees the block
// filled; it refuses as the Conduit does: a decision with no reason, and a proposal its proposer
// decides (`?as=alice`). `?open=accept` and `?open=decline-error` draw the decision form, the second
// with the GOV.UK error summary, for the axe scan; no spec uses them. What was sent is on
// `window.__PROPOSALS__`.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { ModelProposals } from "../src/linktypes/ModelProposals";
import { applyHarnessBrand } from "./brandHarness";

declare global {
  interface Window {
    __PROPOSALS__?: { sent: { path: string; body: unknown }[] };
  }
}

const params = new URLSearchParams(window.location.search);
const reader = params.get("as") ?? "dan";
const rows = [
  {
    id: "p1", name: "BRIBED", label: "Bribed", from_types: ["Person"], to_types: ["Person"], directed: true,
    proposed_by: "alice", proposed_at: "2026-11-08T10:00:00Z", reason: "Paid a prison officer to carry items in",
    status: "pending", decided_by: null as string | null, decision_reason: null as string | null,
    in_model: null as string | null, basis: null as string | null,
  },
  {
    id: "p2", name: "LOOKS_OUT_FOR", label: "Looks out for", from_types: ["Person"], to_types: ["Person"], directed: true,
    proposed_by: "bob", proposed_at: "2026-11-07T15:00:00Z", reason: "Keeps watch during a handover",
    status: "pending", decided_by: null as string | null, decision_reason: null as string | null,
    in_model: null as string | null, basis: null as string | null,
  },
  {
    id: "p3", name: "SEEN_NEAR", label: "Seen near", from_types: ["Person"], to_types: ["Location"], directed: true,
    proposed_by: "bob", proposed_at: "2026-11-06T09:00:00Z", reason: "Near the gate at visiting time",
    status: "rejected", decided_by: "dan", decision_reason: "Use PRESENT_AT",
    in_model: null as string | null, basis: null as string | null,
  },
];  // prettier-ignore

window.__PROPOSALS__ = { sent: [] };
const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

window.fetch = async (input: RequestInfo | URL, init: RequestInit = {}) => {
  const path = new URL(String(input)).pathname;
  if (path === "/v1/datasets/ds-1/model/proposals") return json(200, { proposals: rows });
  const decided = /^\/v1\/datasets\/ds-1\/model\/proposals\/([^/]+)\/(accept|decline)$/.exec(path);
  if (!decided) return json(404, { error: "proposal_not_found" });
  const body = JSON.parse(String(init.body ?? "{}")) as { reason?: string; basis?: string };
  window.__PROPOSALS__!.sent.push({ path, body });
  const row = rows.find((r) => r.id === decided[1]);
  if (!row || row.status !== "pending") return json(404, { error: "proposal_not_found" });
  const refuse = (detail: string) => json(422, { error: "proposal_refused", detail });
  if (!String(body.reason ?? "").trim()) return refuse("Say why: a reason of at most 2000 characters is required.");
  if (row.proposed_by === reader) return refuse("You proposed this type, so another data engineer of the dataset decides it.");
  if (decided[2] === "accept" && !body.basis) return json(422, { detail: [{ msg: "basis required" }] });
  row.status = decided[2] === "accept" ? "accepted" : "rejected";
  row.in_model = decided[2] === "accept" ? "draft" : null;
  row.basis = body.basis ?? null;
  row.decided_by = reader;
  row.decision_reason = String(body.reason);
  return json(200, row);
};

await applyHarnessBrand();

// `?open=…`: the decision form drawn, for the axe scan.
const open = params.get("open");
if (open) {
  const label = open === "accept" ? "Add Bribed to the draft model…" : "Decline Bribed…";
  const press = () => {
    const button = [...document.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent === label);
    if (!button) return void requestAnimationFrame(press);
    button.click();
    if (open === "decline-error") {
      const submit = () => {
        const decide = [...document.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent === "Decline");
        if (decide) decide.click();
        else requestAnimationFrame(submit);
      };
      requestAnimationFrame(submit);
    }
  };
  requestAnimationFrame(press);
}

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");
createRoot(container).render(
  <main style={{ padding: "var(--sp-12)", background: "var(--surface-panel)", maxWidth: 720 }}>
    <ModelProposals apiBaseUrl="http://keyboard-test.invalid" bearerToken="unused" datasetId="ds-1" datasetName="Prison intelligence (synthetic)" />
  </main>,
);
