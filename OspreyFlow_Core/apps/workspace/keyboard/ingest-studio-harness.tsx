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

const startParams = new URLSearchParams(window.location.search);

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
// Phase 6 (ADR-140 decision 3): `?expert=1` gives the draft an expert step, which guided mode reads
// read-only. The step's kind is phase 8's; the harness only needs guided mode to meet one.
const WITH_EXPERT_STEP = {
  nodes: [...CHAIN.nodes, { id: "sql", kind: "sql_transform", label: "Visits per week",
    config: { sql: "SELECT visitor, count(*) AS visits FROM source GROUP BY visitor", summary: "Visits per visitor" } }],
  edges: [...CHAIN.edges, { source: "profile", target: "sql" }],
};  // prettier-ignore
// The draft's map, for the keyboard bind: a Person whose name the caller column fills.
const VISITS_TEMPLATE = { entities: [{ ref: "visitor", pole_class: "person", type: "Person", on_match: "create",
  properties: { name: { field: "caller" } } }], edges: [] };  // prettier-ignore
let draft: Record<string, unknown> = {
  ...base, recipe_id: "r-visits", version: 3, status: "draft", label: "Visit bookings", source_location: "harbour-extract/visits.csv",
  handling: { classification: "OFFICIAL" }, verified_at: day(0, 8), row_template: VISITS_TEMPLATE,
  pipeline: startParams.get("expert") ? WITH_EXPERT_STEP : CHAIN,
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
// Chapter 4's reports file declares a column for each of the six parts of a marking, as the committed
// recipe's `handling_columns` does, so every element of its map binds all six (ADR-127 Amendment 2).
const HANDLING_PARTS = ["classification", "handling_code", "action_code", "sanitisation_code", "originator", "owning_unit"];
const REPORTS_HANDLING = { ...HANDLING, units: ["unit-a", "unit-b"],
  handling_columns: Object.fromEntries(HANDLING_PARTS.map((part) => [part, part])) };  // prettier-ignore
let SOURCES: Record<string, unknown>[] = [
  { id: "src-calls", dataset_id: "harbour-extract", connection_id: "files", name: "Wing phone calls file",
    location: "harbour-extract/calls.csv", connector_profile: "generic-csv", handling: HANDLING,
    legal_basis: "Synthetic demonstration", refresh: { trigger: "watch", pattern: "calls-*.csv", mode: "snapshot",
      dropped_rows: "keep", owner: "engineer-1", paused: false }, version: 1,
    created_by: "engineer-1", created_at: day(9) },
  { id: "src-reports", dataset_id: "harbour-extract", connection_id: "files", name: "Intelligence reports file",
    location: "harbour-extract/intel_reports.csv", connector_profile: "generic-csv", handling: REPORTS_HANDLING,
    legal_basis: "Synthetic demonstration", refresh: { trigger: "manual", mode: "snapshot", dropped_rows: "keep",
      owner: "engineer-1", paused: false }, version: 1, created_by: "engineer-1", created_at: day(8) },
];  // prettier-ignore
const PROFILE = { rows_sampled: 3, sample_is_whole_source: true, values_masked: false, columns: [
  { name: "caller", sample_size: 3, null_count: 0, distinct_count: 3, inferred_type: "string", type_confidence: 1 },
  { name: "called", sample_size: 3, null_count: 0, distinct_count: 2, inferred_type: "string", type_confidence: 1 },
] };  // prettier-ignore
// Chapter 4's reports, synthetic (rule 9): the source the from-scratch walk registers nothing for,
// since it is already registered, and maps.
// Its columns are the real file's header, in its order (`pid_files.header_for`); its rows are invented.
const REPORTS_COLUMNS = ["subject_1", "report_ref", "subject_1_role", "subject_2", "subject_2_role", "subject_3",
  "subject_3_role", "subject_1_nino", "subject_2_nino", "subject_3_nino", "phone_mentioned", "area_ref", "area_ref_2",
  "area_ref_3", "subject_1_family_name", "subject_1_given_names", "subject_1_date_of_birth", "subject_2_family_name",
  "subject_2_given_names", "subject_2_date_of_birth", "subject_3_family_name", "subject_3_given_names",
  "subject_3_date_of_birth", "category", "submitted_at", "title", "report_text", "reviewer_initials", "classification",
  "handling_code", "action_code", "sanitisation_code", "originator", "owning_unit"];  // prettier-ignore
const REPORTS_PROFILE = { rows_sampled: 2, sample_is_whole_source: true, values_masked: false,
  columns: REPORTS_COLUMNS.map((name) => ({ name, sample_size: 2, null_count: 0, distinct_count: 2, inferred_type: "string", type_confidence: 1 })) };  // prettier-ignore
const reportRow = (n: number, title: string): Record<string, string> => ({
  ...Object.fromEntries(REPORTS_COLUMNS.map((name) => [name, ""])),
  subject_1: `SYN-P${n}`, report_ref: `SYN-IR ${n}`, subject_1_nino: `SYN-NI-${n}`, subject_1_family_name: `Synthname${n}`,
  phone_mentioned: n === 1 ? "07700 900001" : "", area_ref: `SYN-WING-${n}`, category: "intelligence",
  submitted_at: "2026-01-0" + n + "T09:00:00Z", title, report_text: `Invented report ${n}.`, reviewer_initials: "SY",
  classification: "OFFICIAL", handling_code: "P", action_code: "", sanitisation_code: "", originator: "unit-a", owning_unit: "unit-a",
});  // prettier-ignore
const SAMPLE_ROWS: Record<string, Record<string, string>[]> = {
  "r-visits": [{ caller: "SYN-0441", called: "SYN-0912" }, { caller: "SYN-0442", called: "SYN-0912" }, { caller: "SYN-0443", called: "SYN-0913" }],
  "r-new": [reportRow(1, "Report one"), reportRow(2, "Report two")],
};  // prettier-ignore
const ONTOLOGY = { version: 1, entity_types: [
  { name: "Document", pole_class: "object", channel: "violet", shape: "page", properties: [{ name: "title", type: "string" },
    { name: "report_id", type: "string" }, { name: "message_id", type: "string" }, { name: "sent_at", type: "datetime" },
    { name: "document_kind", type: "string" }] },
  { name: "Endpoint", pole_class: "object", channel: "violet", shape: "hexagon", properties: [{ name: "value_raw", type: "string" },
    { name: "value_normalised", type: "string" }, { name: "e164", type: "string" }, { name: "endpoint_kind", type: "string" }] },
  { name: "Person", pole_class: "person", channel: "cyan", shape: "circle", properties: [{ name: "name", type: "string" },
    { name: "prison_number", type: "string" }, { name: "nino", type: "string" }, { name: "family_name", type: "string" },
    { name: "given_names", type: "string" }, { name: "date_of_birth", type: "date" }] },
  { name: "Location", pole_class: "location", channel: "green", shape: "pin", properties: [{ name: "site_ref", type: "string" }] },
], edge_types: [
  { name: "MENTIONED_IN", from: ["Location", "Person", "Endpoint"], to: ["Document"], properties: [] },
] };  // prettier-ignore
const TRANSFORMS = [{ name: "msisdn", arity: 1 }];
const VERIFY = { rows_read: 3, sample_is_whole_source: true, values_masked: false, rows_deduplicated: 0,
  entities_by_type: { Person: { created: 3, referenced: 0 } }, edges_by_type: {}, rejections: [], nodes: [], edges: [] };  // prettier-ignore

const SCHEME = { name: "uk-le", classification: ["OFFICIAL", "SECRET"],
  handling_codes: { P: { label: "Permitted", dissemination: "permitted" } } };  // prettier-ignore

const asked: { method: string; path: string; body?: string }[] = [];
// Phase 3's exit (ADR-140 Amendment 6): a pipeline named on the canvas, created here, then given a
// registered source. Absent until created, so every other case sees the registry it always saw.
let created: Record<string, unknown> | null = null;
(window as unknown as { __asked: typeof asked }).__asked = asked;

// The routes' refusals, as the Conduit answers them (rule 15: a fake models what the real route
// refuses, not only what it grants; the review of L1.2, 7 November 2026). `verify` and `preview-graph`
// need the right `verify_pipelines` and editor level; `publish` needs `publish_pipelines` and a draft
// verified since its last edit; any edit of a draft (its pipeline, its settings, its map) clears that
// mark, `verify` sets it, and `preview-graph` leaves it alone. `?rights=no-test` drops the right.
// Publish also needs the source approver's studio role (`require_studio_role(SOURCE_APPROVER)`, a 403
// in words; `?rights=no-approve` drops it). A pipeline save refuses what `pipeline_rule_violations`
// refuses (a source reaching no load, an extract not fed by a map: 422 `pipeline_invalid`), and a kind
// the schema does not know (a 422 from validation). The sample rows refuse a draft whose source is not
// ready (409 `recipe_not_ready_for_profile`) and a row past the sample (404).
const RIGHTS = new Set(["edit_pipelines", "verify_pipelines", "publish_pipelines", "run_pipelines", "schedule_pipelines"]);
if (startParams.get("rights") === "no-test") RIGHTS.delete("verify_pipelines");
const STUDIO_ROLES = new Set(["source_author", "source_approver", "loader"]);
if (startParams.get("rights") === "no-approve") STUDIO_ROLES.delete("source_approver");
const KNOWN_KINDS = new Set(["domain_model", "source", "profile", "map", "extract", "enrich", "load"]);
/** The save gate's refusals, in its own words (`services/ingest/pipeline.py`). */
const pipelineRefusal = (body: string | undefined): Response | null => {
  const graph = JSON.parse(String(body)) as { nodes: { id: string; kind: string; label: string }[]; edges: { source: string; target: string }[] };
  if (graph.nodes.some((n) => !KNOWN_KINDS.has(n.kind)))
    return new Response(JSON.stringify({ detail: [{ type: "literal_error", loc: ["body", "nodes", "kind"] }] }), { status: 422 });
  const next = (id: string) => graph.edges.filter((e) => e.source === id).map((e) => e.target);
  const reaches = (id: string, kind: string, seen = new Set<string>()): boolean =>
    next(id).some((t) => !seen.has(t) && (seen.add(t), graph.nodes.find((n) => n.id === t)?.kind === kind || reaches(t, kind, seen)));
  const problems = [
    ...graph.nodes.filter((n) => n.kind === "source" && !reaches(n.id, "load")).map((n) => `source '${n.label}' reaches no load; its rows would go nowhere`),
    ...graph.nodes.filter((n) => n.kind === "extract" && !graph.edges.some((e) => e.target === n.id && graph.nodes.find((m) => m.id === e.source)?.kind === "map"))
      .map((n) => `extract '${n.label}' is not fed by a map; an extract works on what a map bound, never on raw bytes`),
  ];
  return problems.length ? new Response(JSON.stringify({ error: "pipeline_invalid", problems }), { status: 422 }) : null;
};
const LEVELS: Record<string, string> = { "inv-1": "author", "inv-2": "editor" };
const refusal = (path: string, right: string, level: "viewer" | "editor"): Response | null => {
  if (!RIGHTS.has(right))
    return new Response(JSON.stringify({ detail: { error: "right_required", right } }), { status: 403 });
  const caseId = path.match(/\/v1\/investigations\/([^/]+)\//)?.[1] ?? "";
  const order = ["viewer", "editor", "author"];
  if (order.indexOf(LEVELS[caseId] ?? "") < order.indexOf(level))
    return new Response(JSON.stringify({ detail: `This needs ${level} on the case.` }), { status: 403 });
  return null;
};

window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
  const path = new URL(String(input)).pathname;
  const method = init?.method ?? "GET";
  asked.push({ method, path, ...(typeof init?.body === "string" ? { body: init.body } : {}) });
  const reply = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
  if (path === "/v1/investigations") return reply(CASES);
  if (path === "/v1/handling-scheme") return reply(SCHEME);
  if (path === "/v1/ingest/connectors") return reply([{ id: "generic-csv", label: "CSV file", group: "Generic", structured: true, available: true }]);
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
  // Phase 6: what the drawer's Preview, Test and the Map editor read, for either draft.
  const recipe = path.match(/\/ingest\/recipes\/(r-visits|r-new)\//)?.[1];
  if (recipe) {
    const sample = path.match(/\/map\/sample-rows\/(\d+)$/);
    if (sample && !(recipe === "r-new" ? created?.ready_for_profile : draft.ready_for_profile))
      return reply({ error: "recipe_not_ready_for_profile" }, 409);
    if (sample) {
      const rows = SAMPLE_ROWS[recipe]!;
      const index = Number(sample[1]);
      if (index >= rows.length) return reply({ error: "row_out_of_range" }, 404);
      return reply({ row_index: index, values: rows[index], values_masked: false, is_last_row: index === rows.length - 1 });
    }
    if (path.endsWith("/profile")) return reply(recipe === "r-new" ? REPORTS_PROFILE : PROFILE);
    if ((path.endsWith("/verify") || path.endsWith("/preview-graph")) && method === "POST") {
      const refused = refusal(path, "verify_pipelines", "editor");
      if (refused) return refused;
      // Test marks the draft verified, which Deploy's gate reads; a Preview marks nothing.
      if (path.endsWith("/verify")) {
        if (recipe === "r-new" && created) created = { ...created, verified_at: day(0, 10) };
        else draft = { ...draft, verified_at: day(0, 10) };
      }
      return reply(VERIFY);
    }
    if (path.endsWith("/row-template") && method === "PUT") {
      const sent = JSON.parse(String(init?.body)) as Record<string, unknown>;
      // As `check_recipe_rules` refuses it (422 `recipe_rule`, each problem named): an element that
      // does not bind a part of the marking the source declares a column for.
      const held = (recipe === "r-new" ? created : draft)?.handling as { handling_columns?: Record<string, string> } | undefined;
      const template = sent.row_template as { entities: { ref: string; handling?: Record<string, unknown> }[];
        edges?: { type: string; handling?: Record<string, unknown> }[] };  // prettier-ignore
      const problems = Object.entries(held?.handling_columns ?? {}).flatMap(([part, column]) =>
        [...template.entities.map((e) => [e.ref, e.handling] as const), ...(template.edges ?? []).map((e) => [e.type, e.handling] as const)]
          .filter(([, handling]) => (handling?.[part] as { field?: string } | undefined)?.field !== column)
          .map(([name]) => `element '${name}' does not bind ${part}, which the source declares in column '${column}'.`));  // prettier-ignore
      if (problems.length) return reply({ error: "recipe_rule", problems }, 422);
      if (recipe === "r-new" && created) created = { ...created, ...sent, verified_at: null };
      else draft = { ...draft, ...sent, verified_at: null };
      return reply(recipe === "r-new" ? created : draft);
    }
  }
  if (path === "/v1/ontology") return reply(ONTOLOGY);
  if (path === "/v1/ingest/transforms") return reply(TRANSFORMS);
  if (path.endsWith("/publish") && method === "POST") {
    const refused = refusal(path, "publish_pipelines", "editor");
    if (refused) return refused;
    if (!STUDIO_ROLES.has("source_approver"))
      return new Response(JSON.stringify({ detail: "principal lacks required studio role: source_approver" }), { status: 403 });
    const target = path.endsWith("/r-new/publish") ? created : draft;
    if (!target?.verified_at) return reply({ error: "studio_recipe_not_verified" }, 409);
  }
  if (created && path.endsWith("/ingest/recipes/r-new/publish") && method === "POST") {
    created = { ...created, status: "published", git_path: "recipes/r-new.yaml" };
    return reply(created);
  }
  if (path.endsWith("/pipeline") && method === "PUT") {
    const refused = pipelineRefusal(init?.body as string | undefined);
    if (refused) return refused;
  }
  if (path.endsWith("/ingest/recipes/r-visits/pipeline") && method === "PUT") {
    draft = { ...draft, pipeline: JSON.parse(String(init?.body)), verified_at: null };
    return reply(draft);
  }
  if (path.endsWith("/ingest/recipes/r-visits") && method === "PATCH") {
    draft = { ...draft, ...(JSON.parse(String(init?.body)) as object), verified_at: null };
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
    created = { ...created, pipeline: JSON.parse(String(init?.body)), verified_at: null };
    return reply(created);
  }
  if (created && path.endsWith("/ingest/recipes/r-new") && method === "PATCH") {
    created = { ...created, ...(JSON.parse(String(init?.body)) as object), ready_for_profile: true, verified_at: null };
    return reply(created);
  }
  if (created && path.endsWith("/ingest/recipes/r-new")) return reply(created);
  // The draft list Connect reads to find the draft it opens (`listDrafts`).
  if (path.endsWith("/ingest/recipes") && method === "GET") return reply(created ? [draft, created] : [draft]);
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

// Phase 6: `?mode=expert` starts engineer-1 in expert mode (the preference is per person, ADR-140
// decision 3); without it every person starts guided.
if (startParams.get("mode") === "expert") window.localStorage.setItem("ospreyflow.studio.mode.engineer-1", "expert");
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
// Phase 6's states (ADR-108 Amendment 6, ADR-140 decision 3): the pipeline in guided or expert mode
// with a step's drawer open, a source's and Map's Preview, Test and Deploy in the drawer, an expert
// step read in guided mode, and the Map editor under its strip with a column chosen to bind.
const pipelineState = params.get("pipeline");
if (pipelineState && pipelineState !== "source") {
  await pressNamed("Open Visit bookings");
  if (pipelineState === "guided" || pipelineState === "expert") await pressNamed("Source: Call log");
  if (pipelineState === "preview") {
    await pressNamed("Source: Call log");
    await pressNamed("Preview");
    await pressNamed("Run preview");
  }
  if (pipelineState === "map-preview") {
    await pressNamed("Map: Map");
    await pressNamed("Preview");
    await pressNamed("Run preview");
  }
  if (pipelineState === "test") {
    await pressNamed("Test");
    await pressNamed("Run the test");
  }
  if (pipelineState === "deploy") await pressNamed("Deploy");
  if (pipelineState === "expert-step") await pressNamed("SQL transform: Visits per week");
  if (pipelineState === "map") {
    await pressNamed("Map: Map");
    await pressNamed("Open map editor");
    await pressNamed("Choose column called");
    await pressNamed("Entity 1: visitor (Person)");
  }
  for (let i = 0; i < 20; i++) await settle();
}

