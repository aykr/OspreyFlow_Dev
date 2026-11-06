// The Ingest Studio's four places (ADR-140 decision 1, redesign phase 2), mounted whole and served by
// the page itself: for `ingest-studio.spec.ts` (rule 13) and the every-harness axe scan
// (`a11y/every-harness.spec.ts`), in both themes and under GOV.UK (`?brand=govuk`). Nothing here
// reaches a server; every request is recorded on `window.__asked` for the spec to prove an action
// reached its route. `?tab=model|sources|runs` opens a place; `&cell=1` opens a day's run report on
// Runs, `&held=1` its held rows. The data is synthetic (rule 9): invented names, `SYN-` ids.
import { createRoot } from "react-dom/client";
import { useState } from "react";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { applyHarnessBrand } from "./brandHarness";
import { IngestStudio } from "../src/ingest/IngestStudio";

await applyHarnessBrand();

const day = (back: number, hour = 9) => {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - back);
  d.setUTCHours(hour, 0, 0, 0);
  return d.toISOString();
};

const CASES = [
  { id: "inv-1", name: "Harbour wing review", level: "author", created_at: day(30), created_by: "engineer-1", domains: ["niem"],
    datasets: ["Harbour prison extract (synthetic)"], dataset_ids: ["harbour-extract"] },
  { id: "inv-2", name: "Carrier records intake", level: "editor", created_at: day(20), created_by: "engineer-1", domains: [],
    datasets: ["Carrier records (synthetic)"], dataset_ids: ["carrier-records"] },
];  // prettier-ignore

const CHAIN = {
  nodes: [
    { id: "domain", kind: "domain_model", label: "Domain model", config: { pack: "niem" } },
    { id: "source", kind: "source", label: "Call log", config: {} },
    { id: "profile", kind: "profile", label: "Profile", config: {} },
    { id: "map", kind: "map", label: "Map", config: {} },
    { id: "load", kind: "load", label: "Load", config: {} },
  ],
  edges: [
    { source: "domain", target: "source" },
    { source: "source", target: "profile" },
    { source: "profile", target: "map" },
    { source: "map", target: "load" },
  ],
};

const base = { connector_profile: "generic-csv", owning_unit: "unit-a", created_by: "engineer-1", created_at: day(10),
  unmapped_fields: [], ready_for_profile: true, dataset_id: "harbour-extract", legal_basis: "Synthetic demonstration" };  // prettier-ignore
const deployed: Record<string, unknown> = {
  ...base, recipe_id: "r-calls", version: 2, status: "published", label: "Wing phone calls", source_location: "harbour-extract/calls.csv",
  handling: { classification: "OFFICIAL" }, git_path: "recipes/r-calls.yaml", schedule_watch: "calls-*.csv", pipeline: CHAIN,
};  // prettier-ignore
let draft: Record<string, unknown> = {
  ...base, recipe_id: "r-visits", version: 3, status: "draft", label: "Visit bookings", source_location: "harbour-extract/visits.csv",
  handling: { classification: "OFFICIAL" }, verified_at: day(0, 8), pipeline: CHAIN,
};  // prettier-ignore

const RUNS = [
  { run_id: "run-3", trigger: "watch", file: "calls-0603.csv", started_at: day(1), outcome: "succeeded", run_as: "engineer-1",
    rows_read: 120, nodes_created: 14, nodes_referenced: 220, edges_created: 96, rows_rejected: 1, rows_held: 2, load_id: "SYN-LOAD-3" },
  { run_id: "run-2", trigger: "manual", started_at: day(3), outcome: "succeeded", run_as: "engineer-1",
    rows_read: 200, nodes_created: 40, nodes_referenced: 310, edges_created: 160, rows_rejected: 0, rows_held: 0, load_id: "SYN-LOAD-2" },
  { run_id: "run-1", trigger: "manual", started_at: day(5), outcome: "refused", run_as: "engineer-1",
    failure: "Visit bookings is marked above the clearance of the person it runs as." },
];  // prettier-ignore

const HELD = [
  { id: "h1", investigation_id: "inv-1", load_id: "SYN-LOAD-3", recipe_id: "r-calls", recipe_version: 2, rule_id: "r-cash",
    reason: "The rule could not judge the row: its amount is missing.", source: "harbour-extract/calls-0603.csv",
    row_index: 41, held_at: day(1), handling: { classification: "OFFICIAL" }, row: { caller: "SYN-0441", called: "SYN-0912" },
    status: "pending" },
];  // prettier-ignore

const asked: { method: string; path: string }[] = [];
(window as unknown as { __asked: typeof asked }).__asked = asked;

window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
  const path = new URL(String(input)).pathname;
  const method = init?.method ?? "GET";
  asked.push({ method, path });
  const reply = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
  if (path === "/v1/investigations") return reply(CASES);
  if (path.endsWith("/ingest/recipe-registry")) return reply([deployed, draft]);
  if (path.endsWith("/ingest/recipes/r-calls/runs")) return reply(RUNS);
  if (path.endsWith("/ingest/recipes/r-calls/run") && method === "POST")
    return reply({ load_id: "SYN-LOAD-4", recipe_id: "r-calls", recipe_version: 2, rows_read: 120, rows_deduplicated: 0,
      rows_already_loaded: 120, nodes_created: 0, nodes_referenced: 0, edges_created: 0, rejections: [], rows_held: 0, rule_notes: [] });  // prettier-ignore
  if (path.endsWith("/ingest/recipes/r-visits/publish") && method === "POST") {
    draft = { ...draft, status: "published", git_path: "recipes/r-visits.yaml" };
    return reply(draft);
  }
  if (path.endsWith("/ingest/recipes/r-visits/run") && method === "POST")
    return reply({ load_id: "SYN-LOAD-5", recipe_id: "r-visits", recipe_version: 3, rows_read: 30, rows_deduplicated: 0,
      nodes_created: 12, nodes_referenced: 18, edges_created: 30, rejections: [], rows_held: 0, rule_notes: [] });  // prettier-ignore
  if (path.endsWith("/ingest/recipes/r-calls")) return reply(deployed);
  if (path.endsWith("/ingest/recipes/r-visits")) return reply(draft);
  if (path.endsWith("/held-rows")) return reply(HELD);
  if (path.endsWith("/v1/ingest/packs")) return reply([{ name: "niem", label: "Crime case analysis (NIEM)", entity_types: [], edge_types: [] }]);
  if (path.endsWith("/v1/ingest/schedule-preview")) return reply({ words: "", next_runs: [] });
  if (path.endsWith("/ingest/source-files")) return reply({ root: "/ingest", files: [] });
  return reply({}, 404);
};

function Host() {
  const [caseId, setCaseId] = useState("inv-1");
  return (
    <>
      <IngestStudio
        apiBaseUrl="http://ingest-studio-harness.invalid"
        bearerToken="unused"
        investigationId={caseId}
        onOpenCase={setCaseId}
        rights={new Set(["revert_loads"])}
        username="engineer-1"
      />
      <p role="status" aria-label="Case the Studio works through">{caseId}</p>
    </>
  );
}

createRoot(document.getElementById("root")!).render(<Host />);

// Optional states for the axe scan: a place, a day's report, its held rows.
const settle = () => new Promise((resolve) => setTimeout(resolve, 50));
const press = (match: (b: HTMLButtonElement) => boolean) => {
  const button = [...document.querySelectorAll<HTMLButtonElement>("button")].find(match);
  button?.click();
  return Boolean(button);
};
const params = new URLSearchParams(window.location.search);
const tab = params.get("tab");
const labels: Record<string, string> = { model: "1 Model", sources: "2 Sources", runs: "4 Runs" };
if (tab && labels[tab]) for (let i = 0; i < 40 && !press((b) => b.textContent === labels[tab]); i++) await settle();
if (tab === "runs" && params.get("cell"))
  for (let i = 0; i < 40; i++) {
    const held = [...document.querySelectorAll<HTMLButtonElement>("button")].filter((b) =>
      (b.getAttribute("aria-label") ?? "").includes("needs a person"),
    );
    if (held.length > 0) {
      held[held.length - 1]!.click();
      break;
    }
    await settle();
  }
if (params.get("held")) for (let i = 0; i < 40 && !press((b) => b.textContent === "Open held rows"); i++) await settle();
