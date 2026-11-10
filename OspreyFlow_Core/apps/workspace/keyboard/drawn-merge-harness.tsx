// The Ingest Studio's *Merge into a dataset…* keyboard harness (ADR-143 Amendment 2 decision 6;
// Amendment 3; L3.9): the drawing *Night visits* (three drawn items, one of a type the target lacks),
// which Dana may merge into *Prison intel*, offered one match. The Conduit is a stand-in kept here,
// answering as the merge routes do for an Author of the target holding `merge_datasets`
// (`?policy=second_person_reviews` for a target that asks a second person; once merged it answers
// 404 for the drawing, as the Studio's gate does). `?choose=src` chooses the target once drawn, and `?press=<button text>`
// presses buttons in turn ("|" between), for the axe scan of each step; `?map=Organisation` maps the
// drawn Vessel onto the target's Organisation once the merge is open (Amendment 7), so its property
// places are drawn. What was sent is on
// `window.__DRAWN_MERGE__`.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import "../src/boards/boards.css";
import { DrawnMerge } from "../src/ingest/runs/drawnMerge";
import { applyHarnessBrand } from "./brandHarness";

interface Sent {
  method: string;
  path: string;
  body: unknown;
}

declare global {
  interface Window {
    __DRAWN_MERGE__?: { sent: Sent[] };
  }
}

type Json = Record<string, unknown>;
const params = new URLSearchParams(window.location.search);
const policy = params.get("policy") ?? "author_promotes";
let merged = false;

const item = (id: string, type: string, label: string, problems: string[] = []): Json => ({
  item_id: id, element_id: `e-${id}`, kind: "node", type, label, marking: "OFFICIAL", follows: false,
  source: null, target: null, problems,
});  // prettier-ignore
const LACKS = "Vessel is not a type of Prison intel's model.";
const CHOICES = ["Organisation", "Person"];
const sheet = {
  drawn_dataset_id: "d-night", drawn_name: "Night visits", target_dataset_id: "src", target_name: "Prison intel",
  highest_marking: "OFFICIAL-SENSITIVE", policy,
  mapping: [
    { kind: "node", drawn_type: "Person", target_type: "Person", items: 2, why_not: null, choices: CHOICES,
      drawn_properties: ["family_name"] },
    { kind: "node", drawn_type: "Vessel", target_type: null, items: 1, choices: CHOICES, drawn_properties: ["flag", "name"],
      why_not: `${LACKS} Map it onto one of its types, or its items are left out and stay on the drawing; propose the type on Prison intel's Model tab to merge them later.` },
  ],
  target_types: [
    { kind: "node", name: "Organisation", properties: ["org_ref", "name", "country"], required: [] },
    { kind: "node", name: "Person", properties: ["family_name", "given_names"], required: ["family_name"] },
  ],
  matches: [{ drawn: "e-i-1", drawn_label: "Mercer", loaded: "p-loaded", loaded_label: "Mercer", loaded_type: "Person", score: 1, why: "a name alike" }],
  more_matches: false,
  // A type mapped onto none is said at Map and left out by the merge, never a problem of its items.
  items: [item("i-1", "Person", "Mercer"), item("i-2", "Person", "Unknown male “Tall”"), item("i-3", "Vessel", "Night boat")],
  checks: [
    { name: "marking", passed: true, words: "Every marking within Prison intel's highest allowed, OFFICIAL-SENSITIVE" },
    { name: "types", passed: true, words: "Every type in Prison intel's model" },
  ],
  recorded_as: "One load into Prison intel (trigger drawn_merge), committed at once (the Author promotes).",
};  // prettier-ignore

window.__DRAWN_MERGE__ = { sent: [] };
const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

window.fetch = async (input: RequestInfo | URL, init: RequestInit = {}) => {
  const url = new URL(String(input));
  const path = url.pathname;
  const method = init.method ?? "GET";
  const body = typeof init.body === "string" ? (JSON.parse(init.body) as Json) : null;
  window.__DRAWN_MERGE__!.sent.push({ method, path: `${path}${url.search}`, body });
  const base = "/v1/datasets/d-night/";
  if (!path.startsWith(base)) return json(404, { error: "not_found" });
  const rest = path.slice(base.length);
  if (merged) return json(404, { error: "not_found" });
  if (rest === "merge-targets") {
    return json(200, {
      drawn_dataset_id: "d-night", drawn_name: "Night visits",
      targets: [{ dataset_id: "src", name: "Prison intel", highest_marking: "OFFICIAL-SENSITIVE", policy }],
    });  // prettier-ignore
  }
  if (rest === "merge-sheet" && url.searchParams.get("target") === "src") return json(200, sheet);
  // As the Conduit: the Vessel goes as the type it is mapped onto, a new item; mapped onto none, it is
  // left out with Map's reason.
  const vessel = ((body?.mapping as Json[]) ?? []).find((m) => m.drawn_type === "Vessel")?.target_type ?? null;
  const ticked = ((body?.item_ids as string[]) ?? []).filter((i) => i !== "i-3" || vessel !== null);
  const retyped = vessel !== null && ticked.includes("i-3") ? 1 : 0;
  const leftOut = vessel === null ? [{ item_id: "i-3", label: "Night boat", why: "Its type, Vessel, goes into no type of Prison intel (Map): it stays on the drawing, read-only." }] : [];
  const matches = ((body?.matches as unknown[]) ?? []).length;
  if (rest === "merges/dry-run" && method === "POST") {
    return json(200, { target_dataset_id: "src", nodes: ticked.length, links: 0, matches, retyped, left_out: leftOut, recorded_as: "" });
  }
  if (rest === "merges" && method === "POST") {
    merged = policy === "author_promotes";
    return json(201, {
      id: "m-1", load_id: "promotion-night-1", trigger: "drawn_merge", dataset_id: "src", dataset_name: "Prison intel", case_id: "h-night",
      case_name: "Night visits", board_id: null, proposed_by: "dana", proposed_by_name: "D. Engineer", proposed_at: "2026-11-09T09:00:00Z",
      status: policy === "author_promotes" ? "committed" : "awaiting_review", nodes: ticked.length, links: 0,
      left_out: leftOut, may_review: false, why_not: null, revert_command: null,
    });  // prettier-ignore
  }
  return json(404, {});
};

await applyHarnessBrand();

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

const choose = params.get("choose");
let map = params.get("map");
const presses = (params.get("press") ?? "").split("|").filter(Boolean);
const step = () => {
  const select = document.querySelector<HTMLSelectElement>("#drawn-merge-target");
  if (choose && select && select.value !== choose) {
    const set = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value")!.set!;
    set.call(select, choose);
    select.dispatchEvent(new Event("change", { bubbles: true }));
  }
  const rows = Array.from(document.querySelectorAll<HTMLSelectElement>("select[id^=drawn-merge-type-]"));
  const vesselRow = rows.find((r) => r.labels?.[0]?.textContent?.startsWith("Vessel"));
  if (map && vesselRow) {
    const set = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value")!.set!;
    set.call(vesselRow, map);
    vesselRow.dispatchEvent(new Event("change", { bubbles: true }));
    map = null;
  }
  const name = presses[0];
  if (name && (!choose || select?.value === choose)) {
    const button = Array.from(document.querySelectorAll<HTMLButtonElement>("button")).find((b) => b.textContent?.trim() === name && !b.disabled);
    if (button) {
      presses.shift();
      button.click();
    }
  }
  if (presses.length > 0 || map || (choose && select?.value !== choose)) requestAnimationFrame(step);
};
requestAnimationFrame(step);

createRoot(container).render(
  <div style={{ padding: "var(--sp-16)", background: "var(--surface-app)", color: "var(--text-primary)", minHeight: "720px" }}>
    <DrawnMerge apiBaseUrl="http://keyboard-test.invalid" bearerToken="unused" datasetId="d-night" />
  </div>,
);
