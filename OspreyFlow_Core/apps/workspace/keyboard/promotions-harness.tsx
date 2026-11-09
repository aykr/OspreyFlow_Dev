// The Ingest Studio's *Analyst promotions* keyboard harness (ADR-143 decision 10; Amendment 2
// decision 1; L3.4): dataset *Prison intel* with one promotion waiting for review (from case Wing B,
// two items and a link), one committed, and one removed case's layer. The Conduit is a stand-in kept
// here, so the axe scan of every harness sees the list filled: it answers as the promotion routes do
// for one of the dataset's Authors holding `review_promotions` (`?as=fred` reads as a data engineer
// who is not one of its Authors; `?as=alice` as the proposer). `?press=<button text>` presses a
// button once drawn, for the axe scan of a sheet or a question. What was sent is on
// `window.__PROMOTIONS__`.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import "../src/boards/boards.css";
import { AnalystPromotions } from "../src/ingest/runs/promotions";
import { applyHarnessBrand } from "./brandHarness";

interface Sent {
  method: string;
  path: string;
  body: unknown;
}

declare global {
  interface Window {
    __PROMOTIONS__?: { sent: Sent[] };
  }
}

type Json = Record<string, unknown>;
const params = new URLSearchParams(window.location.search);
const reader = params.get("as") ?? "dana";
const author = reader !== "fred";
const at = "2026-11-08T09:00:00Z";

const promotion = (over: Json): Json => ({
  id: "p-1", load_id: "promotion-wing-1", trigger: "analyst_promotion", dataset_id: "src", dataset_name: "Prison intel",
  case_id: "c-wing", case_name: "Wing B", board_id: null, proposed_by: "alice", proposed_by_name: "A. Field",
  proposed_at: at, status: "awaiting_review", nodes: 2, links: 1, left_out: [{ item_id: "i-x", label: "Spare", why: "Not ticked." }],
  may_review: author && reader !== "alice",
  why_not: reader === "alice" ? "You sent this promotion: a second person must review it."
    : author ? null : "Only one of the dataset's Authors who may review promotions can decide this: you are not one of its Authors.",
  revert_command: null, ...over,
});  // prettier-ignore

const promotions: Json[] = [
  promotion({}),
  // L3.9: a drawn dataset's merge waiting for review, with a match in its details.
  promotion({ id: "p-3", load_id: "promotion-drawn-1", trigger: "drawn_merge", case_name: "Night visits", left_out: [] }),
  promotion({ id: "p-0", load_id: "promotion-night-1", case_name: "Night shift", status: "committed", reviewed_by: "dana",
    reviewed_by_name: "D. Engineer", nodes: 1, links: 0, may_review: false, why_not: null, revert_command: "x" }),
];  // prettier-ignore
const cases: Json[] = [{ investigation_id: "c-old", name: "Old wing", items: 3, mergeable: true }];
const sheetItems = [
  { item_id: "i-a", element_id: "n-a", kind: "node", type: "Person", label: "Unknown male “Tall”", marking: "OFFICIAL", follows: false, problems: [] },
  { item_id: "i-b", element_id: "n-b", kind: "node", type: "Vehicle", label: "Blue van", marking: "OFFICIAL", follows: false, problems: [] },
  { item_id: "i-c", element_id: "e-c", kind: "link", type: "ASSOCIATE_OF", label: "seen together", marking: "SECRET", follows: true, source: "n-a", target: "n-b",
    problems: ["Marked SECRET, above Prison intel's highest allowed marking, OFFICIAL-SENSITIVE."] },
];  // prettier-ignore
let grantOpen = false;

window.__PROMOTIONS__ = { sent: [] };
const json = (status: number, body: unknown) =>
  new Response(status === 204 ? null : JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

window.fetch = async (input: RequestInfo | URL, init: RequestInit = {}) => {
  const url = new URL(String(input));
  const path = url.pathname;
  const method = init.method ?? "GET";
  const body = typeof init.body === "string" ? (JSON.parse(init.body) as Json) : null;
  window.__PROMOTIONS__!.sent.push({ method, path, body });
  const base = "/v1/datasets/src/";
  if (!path.startsWith(base)) return json(404, { error: "not_found" });
  const rest = path.slice(base.length);
  if (rest === "promotions") return json(200, { promotions });
  const one = /^promotions\/([^/]+)(\/decision)?$/.exec(rest);
  if (one) {
    const p = promotions.find((x) => x.id === one[1]);
    if (!p) return json(404, { error: "promotion_not_found" });
    if (!author) return json(403, { error: "not_an_author", detail: "Only one of the dataset's Authors who may review promotions can read or decide this." });
    if (one[2]) {
      const decision = body as Json;
      Object.assign(p, decision.approve ? { status: "committed", reviewed_by: reader, reviewed_by_name: "D. Engineer" }
        : { status: "rejected", reviewed_by: reader, reviewed_by_name: "D. Engineer", reason: decision.reason });  // prettier-ignore
      p.may_review = false;
      return json(200, p);
    }
    return json(200, {
      promotion: p, withheld: false,
      matches: p.trigger === "drawn_merge"
        ? [{ drawn: "n-a", drawn_label: "Unknown male “Tall”", loaded: "p-loaded", loaded_label: "Tall, J.", loaded_type: "Person", score: 0.82, why: "chosen at the merge" }]
        : [],
      items: [
        { element_id: "n-a", kind: "node", type: "Person", label: "Unknown male “Tall”", marking: "OFFICIAL", grading: "B21", source_note: "Wing officer report, 4 Nov" },
        { element_id: "n-b", kind: "node", type: "Vehicle", label: "Blue van", marking: "OFFICIAL", grading: "C32", source_note: "Gate log" },
        { element_id: "e-c", kind: "link", type: "ASSOCIATE_OF", label: "seen together", marking: "OFFICIAL", grading: "B21", source_note: "Visits log" },
      ],
    });  // prettier-ignore
  }
  if (!author) return json(403, { error: "not_an_author", detail: "Only one of the dataset's Authors may merge or delete a removed case's layer." });
  if (rest === "removed-cases") return json(200, { dataset_id: "src", cases });
  if (rest === "removed-cases/c-old/merge-sheet" && method === "POST") {
    grantOpen = true;
    return json(200, {
      grant_id: "g-1", investigation_id: "c-old", case_name: "Old wing", dataset_id: "src", dataset_name: "Prison intel",
      highest_marking: "OFFICIAL-SENSITIVE", policy: "author_promotes", items: sheetItems,
      checks: [{ name: "marking", passed: false, words: "Every marking within Prison intel's highest allowed, OFFICIAL-SENSITIVE: 1 above it" }],
      warnings: [], recorded_as: "One load into Prison intel (trigger layer_merge), committed at once (the Author promotes).",
    });  // prettier-ignore
  }
  if (rest === "layer-merges/g-1" && method === "DELETE") {
    grantOpen = false;
    return json(204, null);
  }
  if (rest === "layer-merges/g-1" && method === "POST") {
    if (!grantOpen) return json(403, { error: "no_open_grant", detail: "This merge is closed: open Merge into the dataset again to read the layer." });
    grantOpen = false;
    const ticked = ((body as Json).item_ids as string[]) ?? [];
    const merged = promotion({ id: "p-2", load_id: "promotion-old-1", trigger: "layer_merge", case_name: "Old wing", status: "committed",
      nodes: ticked.length, links: 0, may_review: false, left_out: [{ item_id: "i-c", label: "seen together", why: "Not ticked." }] });  // prettier-ignore
    promotions.unshift(merged);
    return json(201, merged);
  }
  if (rest === "removed-cases/c-old/delete/dry-run" && method === "POST") {
    return json(200, { investigation_id: "c-old", action: "delete", items: 3, links: 0, size_bytes: 512,
      would: "Would delete 3 items and 0 links (512 bytes) from Old wing's layer. Promoted items are never touched. Nothing has been written." });  // prettier-ignore
  }
  if (rest === "removed-cases/c-old/layer" && method === "DELETE") {
    cases.splice(0, cases.length);
    return json(200, { investigation_id: "c-old", words: "The layer was deleted: its items are withdrawn and kept in the audit. Promoted items were not touched." });
  }
  return json(404, {});
};

await applyHarnessBrand();

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

// `press` names buttons to press in turn, separated by "|", each once it is drawn.
const presses = (params.get("press") ?? "").split("|").filter(Boolean);
const pressNext = () => {
  const name = presses[0];
  if (!name) return;
  const button = Array.from(document.querySelectorAll<HTMLElement>("button")).find((b) => b.textContent?.trim() === name);
  if (button) {
    presses.shift();
    button.click();
  }
  requestAnimationFrame(pressNext);
};
requestAnimationFrame(pressNext);

createRoot(container).render(
  <div style={{ padding: "var(--sp-16)", background: "var(--surface-app)", color: "var(--text-primary)", minHeight: "720px" }}>
    <AnalystPromotions apiBaseUrl="http://keyboard-test.invalid" bearerToken="unused" datasetId="src" canRevert={params.get("revert") === "1"} username={reader} />
  </div>,
);
