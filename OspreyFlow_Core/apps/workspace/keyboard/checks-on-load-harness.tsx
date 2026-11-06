// The Ingest Studio's "Checks on load" step and Verify's would-be alerts (ADR-133 decision 6, stage
// (d)), with a synthetic customer pipeline, served by the page itself: for the every-harness axe scan
// (`a11y/every-harness.spec.ts`, which finds this page by its directory) and for the Product Overview
// deck's screens, in both brands (`?brand=govuk`). Nothing here reaches a server. The page opens the
// pipeline's Checks on load step; `?view=verify` runs Verify instead and shows the alerts the sample
// would raise beside its rejections. The keyboard walkthrough is `checks-on-load.spec.ts`, against
// the pipeline Studio harness. The data is synthetic (rule 9): invented names.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { applyHarnessBrand } from "./brandHarness";
import { PipelineStudio } from "../src/ingest/dag/PipelineStudio";

await applyHarnessBrand();

const CHAIN = {
  nodes: [
    { id: "domain", kind: "domain_model", label: "Domain model", config: { pack: "pole" } },
    { id: "source", kind: "source", label: "New customers", config: {} },
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

const DRAFT = {
  recipe_id: "r1", version: 3, status: "draft", label: "Customer onboarding (weekly file)", connector_profile: "generic-csv",
  source_location: "onboarding/customers_week44.csv", handling: {}, legal_basis: null, owning_unit: "unit-a", created_by: "engineer-1",
  created_at: "2026-10-28T09:00:00Z", pipeline: CHAIN, unmapped_fields: [], ready_for_profile: true,
};  // prettier-ignore

const CHECKS = {
  recipe_id: "r1",
  chosen: true,
  set_by: "engineer-1",
  set_at: "2026-11-01T08:30:00Z",
  checks: [{ rule_id: "r-kyc", on_hit: "alert" }, { rule_id: "r-cash", on_hit: "hold" }],
  available: [
    { rule_id: "r-kyc", name: "New customers screened", words: "When a Person is on a screening list (name match 0.9), raise a high-severity alert for the case team, before each load commits.",
      scope: "this_case", trigger: "pre_commit", severity: "high", status: "active", can_hold: true, always_applies: false, authors_on_hit: "alert" },
    { rule_id: "r-cash", name: "Large cash paid in", words: "The large cash typology, before each load commits.", scope: "this_case",
      trigger: "pre_commit", severity: "medium", status: "active", can_hold: true, always_applies: false, authors_on_hit: "alert" },
    { rule_id: "r-often", name: "Listed people seen often", words: "When a Person whose listing is one of sanction, pep, 3 or more times by “Present at” within 7 day(s), raise a high-severity alert for the case team, after each load commits.",
      scope: "this_case", trigger: "post_commit", severity: "high", status: "active", can_hold: false, always_applies: false, authors_on_hit: "alert" },
    { rule_id: "r-wide", name: "Sanctioned people, every case", words: "When a Person is on a screening list (name match 0.9), raise a high-severity alert for every case's team, before each load commits.",
      scope: "deployment", trigger: "pre_commit", severity: "high", status: "active", can_hold: true, always_applies: true, authors_on_hit: "alert" },
  ],
};  // prettier-ignore

function person(id: string, given: string, family: string) {
  return {
    id, type: "Person", properties: { given_names: given, family_name: family },
    provenance: { state: "asserted", sources: [{ document_id: "customers_week44.csv", locator: "row 1", excerpt_hash: "h" }], first_seen: "2026-11-01T00:00:00Z" },
    handling: { classification: "OFFICIAL", handling_code: "P", originator: "unit-a", owning_unit: "unit-a" },
    audit: { created_at: "2026-11-01T00:00:00Z", created_by: "engineer-1", revision: 0 },
  };  // prettier-ignore
}

const VERIFY = {
  rows_read: 4, rows_deduplicated: 0, rows_already_loaded: 0, sample_is_whole_source: true, values_masked: false,
  entities_by_type: { Person: { created: 3, referenced: 0 } }, edges_by_type: {},
  rejections: [{ reason: "Person.listing is not a valid enum", count: 1,
    samples: [{ row_index: 3, reason: "Person.listing is not a valid enum", sample: "{'given_names': 'Ilya', 'family_name': 'Varga', 'listing': 'unknown'}" }] }],
  nodes: [person("p1", "Callum", "Okafor"), person("p2", "Dana", "Mercer"), person("p3", "Joel", "Ashby")], edges: [],
  checks_judged: 2,
  would_raise: [
    { rule_id: "r-kyc", rule_name: "New customers screened", severity: "high", on_hit: "alert", entity_id: "p1", entity_type: "Person", entity_name: "Callum Okafor" },
    { rule_id: "r-wide", rule_name: "Sanctioned people, every case", severity: "high", on_hit: "alert", entity_id: "p1", entity_type: "Person", entity_name: "Callum Okafor" },
  ],
  checks_not_judged: [
    { rule_id: "r-cash", rule_name: "Large cash paid in", why: "It reads money movements, which a dry run does not make; it is judged when the load runs." },
    { rule_id: "r-often", rule_name: "Listed people seen often", why: "It counts events, which a dry run does not make; it is judged when the load runs." },
  ],
};  // prettier-ignore

const ONTOLOGY = {
  version: 17,
  entity_types: [{ name: "Person", pole_class: "person", channel: "indigo", shape: "circle", identifiers: [], properties: [
    { name: "given_names", type: "string" }, { name: "family_name", type: "string" }] }],
  edge_types: [],
};  // prettier-ignore

window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
  const path = new URL(String(input)).pathname;
  const method = init?.method ?? "GET";
  const reply = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
  if (path.endsWith("/v1/ingest/packs")) return reply([{ name: "pole", label: "Bespoke POLE (the core model)", entity_types: [], edge_types: [] }]);
  if (path.endsWith("/v1/ontology")) return reply(ONTOLOGY);
  if (path.endsWith("/ingest/recipes/r1/checks")) return reply(method === "PUT" ? { ...CHECKS, checks: JSON.parse(String(init?.body)).checks } : CHECKS);
  if (path.endsWith("/ingest/recipes/r1/verify")) return reply(VERIFY);
  if (path.endsWith("/ingest/recipes/r1")) return reply(DRAFT);
  if (path.endsWith("/ingest/recipe-registry")) return reply([DRAFT]);
  return reply({}, 404);
};

createRoot(document.getElementById("root")!).render(
  <PipelineStudio apiBaseUrl="http://checks-harness.invalid" bearerToken="unused" investigationId="inv-1" />,
);

const settle = () => new Promise((resolve) => setTimeout(resolve, 50));
const pressButton = (name: string) => {
  const button = [...document.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent === name || b.getAttribute("aria-label") === name);
  button?.click();
  return Boolean(button);
};
const view = new URLSearchParams(window.location.search).get("view") ?? "checks";
for (let i = 0; i < 40 && !pressButton("Open Customer onboarding (weekly file)"); i++) await settle();
for (let i = 0; i < 40 && !pressButton(view === "verify" ? "Test" : "Load rules"); i++) await settle();
if (view === "verify") for (let i = 0; i < 40 && !pressButton("Run the test"); i++) await settle();
