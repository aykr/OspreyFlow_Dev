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
let deployed: Record<string, unknown> = {
  ...base, recipe_id: "r-calls", version: 2, status: "published", label: "Wing phone calls", source_location: "harbour-extract/calls.csv",
  handling: { classification: "OFFICIAL" }, git_path: "recipes/r-calls.yaml", schedule_watch: "calls-*.csv", pipeline: CHAIN,
  schedule_owner: "engineer-1", schedule_paused: true,
  schedule_paused_reason: "waiting for its chapter 9 step: resume it on the Studio's Runs tab",
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

const HANDLING = { classification: "OFFICIAL", handling_code: "P", originator: "unit-a", owning_unit: "unit-a" };
let SOURCES: Record<string, unknown>[] = [
  { id: "src-calls", dataset_id: "harbour-extract", connection_id: "files", name: "Wing phone calls file",
    location: "harbour-extract/calls.csv", connector_profile: "generic-csv", handling: HANDLING,
    legal_basis: "Synthetic demonstration", refresh: { trigger: "watch", pattern: "calls-*.csv", mode: "snapshot",
      dropped_rows: "keep", owner: "engineer-1", paused: false }, version: 1,
    created_by: "engineer-1", created_at: day(9) },
];  // prettier-ignore
const PROFILE = { rows_sampled: 3, sample_is_whole_source: true, values_masked: false, columns: [
  { name: "caller", sample_size: 3, null_count: 0, distinct_count: 3, inferred_type: "string", type_confidence: 1 },
  { name: "called", sample_size: 3, null_count: 0, distinct_count: 2, inferred_type: "string", type_confidence: 1 },
] };  // prettier-ignore
const SCHEME = { name: "uk-le", classification: ["OFFICIAL", "SECRET"],
  handling_codes: { P: { label: "Permitted", dissemination: "permitted" } } };  // prettier-ignore

const asked: { method: string; path: string; body?: string }[] = [];
// Phase 3's exit (ADR-140 Amendment 6): a pipeline named on the canvas, created here, then given a
// registered source. Absent until created, so every other case sees the registry it always saw.
let created: Record<string, unknown> | null = null;
(window as unknown as { __asked: typeof asked }).__asked = asked;

window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
  const path = new URL(String(input)).pathname;
  const method = init?.method ?? "GET";
  asked.push({ method, path, ...(typeof init?.body === "string" ? { body: init.body } : {}) });
  const reply = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
  if (path === "/v1/investigations") return reply(CASES);
  if (path === "/v1/handling-scheme") return reply(SCHEME);
  if (path === "/v1/ingest/connections") return reply([{ id: "files", kind: "files", name: "Files: the ingest root", created_by: "system", created_at: day(30) }]);
  if (path === "/v1/datasets/harbour-extract/source-files")
    return reply({ root: "/ingest", files: [
      { name: "calls.csv", source_location: "harbour-extract/calls.csv", size_bytes: 10, modified_at: 1 },
      { name: "cell_stays.csv", source_location: "harbour-extract/cell_stays.csv", size_bytes: 10, modified_at: 2 },
    ] });  // prettier-ignore
  if (path === "/v1/datasets/harbour-extract/sources" && method === "POST") {
    const body = JSON.parse(String(init?.body)) as Record<string, unknown>;
    const made = { ...body, id: "src-new", dataset_id: "harbour-extract", version: 1, created_by: "engineer-1", created_at: day(0) };
    SOURCES = [...SOURCES, made];
    return reply(made, 201);
  }
  if (path === "/v1/datasets/harbour-extract/sources") return reply(SOURCES);
  if (/\/v1\/datasets\/harbour-extract\/sources\/[^/]+\/profile$/.test(path)) return reply(PROFILE);
  if (/\/v1\/datasets\/harbour-extract\/sources\/[^/]+\/lineage$/.test(path))
    return reply([{ recipe_id: "r-calls", label: "Wing phone calls", version: 2, status: "published" }]);
  // ADR-110 Amendment 13: a refresh paused (with why) and resumed, neither an edit of the source.
  if (/\/v1\/datasets\/harbour-extract\/sources\/[^/]+\/refresh\/(pause|resume)$/.test(path) && method === "POST") {
    const pausing = path.endsWith("/pause");
    const reason = pausing ? ((JSON.parse(String(init?.body ?? "{}")) as { reason?: string | null }).reason ?? "paused by engineer-1") : null;
    const refresh = { ...(SOURCES[0].refresh as object), paused: pausing, paused_reason: reason };
    SOURCES = [{ ...SOURCES[0], refresh }, ...SOURCES.slice(1)];
    return reply(SOURCES[0]);
  }
  if (/\/v1\/datasets\/harbour-extract\/sources\/[^/]+\/governance$/.test(path)) {
    const body = JSON.parse(String(init?.body)) as Record<string, unknown>;
    const edited = { ...SOURCES[0], ...body, version: 2 };
    SOURCES = [edited, ...SOURCES.slice(1)];
    return reply({ source: edited, needs_attention: ["Wing phone calls"] });
  }
  if (path.endsWith("/ingest/recipes/r-visits/pipeline") && method === "PUT") {
    draft = { ...draft, pipeline: JSON.parse(String(init?.body)) };
    return reply(draft);
  }
  if (path.endsWith("/ingest/recipes/r-visits") && method === "PATCH") {
    draft = { ...draft, ...(JSON.parse(String(init?.body)) as object) };
    return reply(draft);
  }
  if (path.endsWith("/ingest/recipes") && method === "POST") {
    const body = JSON.parse(String(init?.body)) as Record<string, unknown>;
    created = { ...base, ...body, recipe_id: "r-new", version: 1, status: "draft", source_location: null, handling: {},
      legal_basis: null, ready_for_profile: false, created_at: day(0),
      pipeline: { ...CHAIN, nodes: CHAIN.nodes.map((n) => (n.id === "source" ? { ...n, label: "New source" } : n)) } };  // prettier-ignore
    return reply(created, 201);
  }
  if (created && path.endsWith("/ingest/recipes/r-new/pipeline") && method === "PUT") {
    created = { ...created, pipeline: JSON.parse(String(init?.body)) };
    return reply(created);
  }
  if (created && path.endsWith("/ingest/recipes/r-new") && method === "PATCH") {
    created = { ...created, ...(JSON.parse(String(init?.body)) as object), ready_for_profile: true };
    return reply(created);
  }
  if (created && path.endsWith("/ingest/recipes/r-new")) return reply(created);
  if (path.endsWith("/ingest/recipe-registry")) return reply(created ? [deployed, draft, created] : [deployed, draft]);
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
  if (path.endsWith("/ingest/recipes/r-calls/schedule/resume") && method === "POST") {
    deployed = { ...deployed, schedule_paused: false, schedule_paused_reason: null };
    return reply(deployed);
  }
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
// ADR-140 Amendment 4's states: the register wizard at its governance step, a source's page (with
// its governance being edited), and a pipeline's source chosen from the registered sources.
const pressNamed = async (name: string) => {
  for (let i = 0; i < 40 && !press((b) => b.textContent === name || b.getAttribute("aria-label") === name); i++) await settle();
};
/** Chooses `value` in the select labelled `label`, as React hears a person choose it. */
const choose = async (label: string, value: string) => {
  for (let i = 0; i < 40; i++) {
    const select = [...document.querySelectorAll("label")]
      .find((l) => l.textContent?.startsWith(label))
      ?.querySelector("select");
    if (select && [...select.options].some((o) => o.value === value)) {
      Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value")!.set!.call(select, value);
      select.dispatchEvent(new Event("change", { bubbles: true }));
      return;
    }
    await settle();
  }
};
if (tab === "sources" && params.get("register")) {
  await pressNamed("Register a source");
  await pressNamed("Next");
  await choose("File", "harbour-extract/cell_stays.csv");
  await settle();
  await pressNamed("Next");
}
if (tab === "sources" && params.get("source")) {
  await pressNamed("Open source Wing phone calls file");
  if (params.get("edit")) await pressNamed("Edit governance");
}
if (params.get("pipeline") === "source") {
  await pressNamed("Open Visit bookings");
  await pressNamed("Source: Call log");
}
