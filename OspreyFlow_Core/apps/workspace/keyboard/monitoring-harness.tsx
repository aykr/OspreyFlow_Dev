// The Monitoring place with a synthetic case's alerts of every kind (ADR-133 decision 5, stage (a)),
// served by the page itself: for the every-harness axe scan (`a11y/every-harness.spec.ts`, which
// finds this page by its directory) and for the Product Overview deck's screens, in both brands
// (`?brand=govuk`). Nothing here reaches a server. `?open=<id>` opens that alert; `?tab=rules` and
// `?tab=watches` open those tabs; `?tab=rules&sentence=preview` writes a rule as a sentence there and
// previews it (ADR-133 stage (b)). The data is synthetic (rule 9): invented names and numbers.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { applyHarnessBrand } from "./brandHarness";
import { AlertsPlace } from "../src/alerts/AlertsPlace";

await applyHarnessBrand();

const NOW = Date.now();
const hoursAgo = (h: number) => new Date(NOW - h * 3_600_000).toISOString();

function entity(id: string, type: string, name: string) {
  return {
    id, type, properties: { name },
    provenance: { state: "asserted", sources: [], first_seen: "2026-10-01T00:00:00Z" },
    handling: { classification: "OFFICIAL", handling_code: "P", originator: "unit-a", owning_unit: "unit-a" },
    audit: { created_at: "2026-10-01T00:00:00Z", created_by: "seed", revision: 1 },
  };  // prettier-ignore
}

const ENTITIES = {
  n1: entity("n1", "Account", "GB-MULE-0042"),
  n2: entity("n2", "Account", "GB-HUB-0007"),
  n3: entity("n3", "Endpoint", "07700 900310"),
  n4: entity("n4", "Person", "OKAFOR, Callum"),
  n5: entity("n5", "Person", "Harbour Freight Ltd"),
  n6: entity("n6", "Account", "GB-LOOP-0311"),
};

const base = { owner_id: "analyst-1", mode: "full", investigation_id: "inv-1", edge_ids: [], event_ids: [] };
const QUEUE = [
  {
    alert: { ...base, id: "a-hot", rule_id: "hotlist:hl-1", referent_node_ids: ["n3"], created_at: hoursAgo(2), status: "open", assignee: null, team: "unit-a" },
    summary: "A hotlisted identifier appeared: 07700 900310", kind: "hotlist", severity: "high", audience: "team", team: "unit-a",
  },
  {
    alert: { ...base, id: "a-kyc", rule_id: "typology:r4", typology: "kyc_screening", referent_node_ids: ["n5"], created_at: hoursAgo(5), status: "claimed", assignee: "analyst-2",
      words: "Harbour Freight Ltd is a close match (0.94) to a listed party", trigger: "pre_commit", alert_node_id: null },
    summary: "Harbour Freight Ltd is a close match (0.94) to a listed party", kind: "typology", severity: "high", audience: "case", team: null,
  },
  {
    alert: { ...base, id: "a-str", rule_id: "typology:r1", typology: "structuring", referent_node_ids: ["n1", "n2"], created_at: hoursAgo(26), status: "open", assignee: null,
      words: "4 movements from GB-MULE-0042 to GB-HUB-0007, each under 10,000, together 38,400", trigger: "pre_commit", alert_node_id: null },
    summary: "4 movements from GB-MULE-0042 to GB-HUB-0007, each under 10,000, together 38,400", kind: "typology", severity: "medium", audience: "case", team: null,
  },
  {
    alert: { ...base, id: "a-mon", rule_id: "monitor:mo-1", referent_node_ids: ["n4", "n3"], created_at: hoursAgo(30), status: "open", assignee: null, team: "unit-a" },
    summary: "A watched pattern matched: OKAFOR, Callum, 07700 900310", kind: "monitor", severity: "medium", audience: "team", team: "unit-a",
  },
  {
    alert: { ...base, id: "a-circ", rule_id: "typology:r2", typology: "circular_flow", referent_node_ids: ["n6"], created_at: hoursAgo(75), status: "open", assignee: null,
      words: "Value back at GB-LOOP-0311 in 3 movements within 9 days", trigger: "post_commit", alert_node_id: null },
    summary: "Value back at GB-LOOP-0311 in 3 movements within 9 days", kind: "typology", severity: "medium", audience: "case", team: null,
  },
  {
    alert: { ...base, id: "a-own", rule_id: "hotlist:hl-2", referent_node_ids: ["n4"], created_at: hoursAgo(80), status: "open", assignee: null },
    summary: "A hotlisted identifier appeared: OKAFOR, Callum", kind: "hotlist", severity: "high", audience: "owner", team: null,
  },
];  // prettier-ignore

const HOTLISTS = {
  hotlists: [
    { id: "hl-1", identifier: "+447700900310", identifier_typed: "07700 900310", identifier_canonical: true, owner_id: "analyst-1", review_date: "2027-01-31", status: "active", created_at: hoursAgo(400), audience: "team" },
    { id: "hl-2", identifier: "okafor", identifier_typed: "OKAFOR, Callum", identifier_canonical: false, owner_id: "analyst-1", review_date: "2027-03-01", status: "active", created_at: hoursAgo(300), audience: "only_me" },
  ],
  audience_default: "only_me",
  audience_editable: true,
};  // prettier-ignore

// ADR-133 stage (b): the ontology the sentence builder's blanks come from (a slice of the default's),
// a deployed sentence, its drawn pattern and its preview.
const ONTOLOGY = {
  version: 17,
  entity_types: [
    { name: "Person", pole_class: "person", channel: "indigo", shape: "circle", identifiers: ["nino"], properties: [
      { name: "family_name", type: "string", indexed: true }, { name: "given_names", type: "string", indexed: true },
      { name: "date_of_birth", type: "date", sensitivity: "high" },
      { name: "listing", type: "enum", values: ["sanction", "pep", "adverse_media"] }] },
    { name: "Endpoint", pole_class: "object", channel: "cyan", shape: "hexagon", identifiers: ["e164"], properties: [
      { name: "value_normalised", type: "string", indexed: true },
      { name: "endpoint_kind", type: "enum", values: ["msisdn", "email", "account"] }] },
    { name: "Location", pole_class: "location", channel: "ochre", shape: "pin", identifiers: [], properties: [
      { name: "geometry_ref", type: "string" }, { name: "name", type: "string", indexed: true }] },
  ],
  edge_types: [
    { name: "USES", from: ["Person"], to: ["Endpoint"], basis: "direct", label: "Uses" },
    { name: "PRESENT_AT", from: ["Person"], to: ["Location"], temporal: true, basis: "direct", label: "Present at" },
    { name: "TRANSACTED", from: ["Endpoint"], to: ["Endpoint"], temporal: true, basis: "direct", label: "Transacted",
      properties: [{ name: "amount", type: "float" }] },
  ],
};  // prettier-ignore

const SENTENCE_WORDS =
  "When a Person whose listing is one of sanction, pep, 3 or more times by “Present at” within 7 day(s), raise a high-severity alert for the case team, after each load commits.";
const PREVIEW = {
  days: 90, would_raise: 7, words: SENTENCE_WORDS,
  examples: [
    { node_id: "p1", name: "Callum Okafor", entity_type: "Person", words: "Callum Okafor (Person): 4 times within 7 day(s)" },
    { node_id: "p2", name: "Dana Mercer", entity_type: "Person", words: "Dana Mercer (Person): 3 times within 7 day(s)" },
    { node_id: "p3", name: "Ilya Varga", entity_type: "Person", words: "Ilya Varga (Person): 5 times within 7 day(s)" },
    { node_id: "p4", name: "Joel Ashby", entity_type: "Person", words: "Joel Ashby (Person): 3 times within 7 day(s)" },
    { node_id: "p5", name: "Mira Quinn", entity_type: "Person", words: "Mira Quinn (Person): 6 times within 7 day(s)" },
  ],
};  // prettier-ignore
const SENTENCE_RULE = {
  id: "r9", investigation_id: "inv-1", owner_id: "analyst-1", name: "Listed people seen often", status: "active",
  created_at: hoursAgo(20), trigger: "post_commit", budget_ms: 5000,
  params: { typology: "sentence", pattern_id: "pat-9", max_matches: 200, sentence: {
    subject: "Person", conditions: [{ op: "one_of", property: "listing", values: ["sanction", "pep"] }], relationship: null,
    frequency: { kind: "count", link_type: "PRESENT_AT", at_least: 3, within_days: 7 },
    severity: "high", team: "case", runs: "post_commit", on_hit: "load", scope: "this_case" } },
};  // prettier-ignore

function answer(path: string, search: URLSearchParams): unknown {
  if (path === "/v1/ontology") return ONTOLOGY;
  if (path === "/v1/investigations") return [{ id: "inv-1", name: "Operation Ledger", level: "author", created_at: "", created_by: "" }];
  const local = path.replace("/v1/investigations/inv-1/", "");
  if (local === "alert-queue") {
    const kinds = search.getAll("kind");
    const severities = search.getAll("severity");
    const status = search.get("status") ?? "active";
    return QUEUE.filter(
      (row) =>
        (kinds.length === 0 || kinds.includes(row.kind)) &&
        (severities.length === 0 || severities.includes(row.severity)) &&
        (status === "all" || (status === "active" ? row.alert.status !== "closed" : row.alert.status === status)),
    );
  }
  const row = QUEUE.find((r) => local === `alert-queue/${r.alert.id}`);
  if (row) {
    const nodes = row.alert.referent_node_ids.map((id) => ENTITIES[id as keyof typeof ENTITIES]);
    return { ...row, nodes, edges: [], transactions: [] };
  }
  if (local === "alert-assignees") return [{ id: "analyst-1", name: "Ana Lyst" }, { id: "analyst-2", name: "Priya Shah" }];
  if (local === "rules") return [SENTENCE_RULE];
  if (local === "rules/preview") return PREVIEW;
  if (local === "rules/sentence/compile")
    return { words: SENTENCE_WORDS, pattern: { nodes: [{ var: "subject", entity_type: "Person", where: {} }], edges: [], limit: 50000 } };
  if (local === "patterns") return { patterns: [{ id: "sp1", pattern_id: "pat-1", version: 1, name: "Phone shared by two people", owner_id: "analyst-1", created_at: hoursAgo(500), definition: { nodes: [], edges: [] } }] };
  if (local === "hotlists") return HOTLISTS;
  if (local === "monitors") return { monitors: [{ id: "mo-1", pattern_id: "pat-1", owner_id: "analyst-1", status: "active", created_at: hoursAgo(500) }] };
  return null;
}

window.fetch = async (input: RequestInfo | URL) => {
  const url = new URL(String(input));
  const body = answer(url.pathname, url.searchParams);
  return new Response(JSON.stringify(body ?? {}), { status: body === null ? 404 : 200 });
};

createRoot(document.getElementById("root")!).render(
  <AlertsPlace
    apiBaseUrl="http://monitoring-harness.invalid"
    bearerToken="unused"
    investigationId="inv-1"
    accountId="analyst-1"
    isAdministrator={false}
    onCanvas={() => undefined}
  />,
);

/** Sets a select or input as a person would, so React sees the change. */
function choose(label: string, value: string) {
  const field = document.querySelector<HTMLInputElement | HTMLSelectElement>(`[aria-label="${label}"]`);
  if (!field) return false;
  const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(field), "value")?.set;
  setter?.call(field, value);
  field.dispatchEvent(new Event(field instanceof HTMLSelectElement ? "change" : "input", { bubbles: true }));
  return true;
}
const pressButton = (name: string) =>
  [...document.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent === name)?.click();

// `?open=` and `?tab=`: the page opens on that alert or tab, as a reader would by keyboard.
const params = new URLSearchParams(window.location.search);
const settle = () => new Promise((resolve) => setTimeout(resolve, 50));
const tab = params.get("tab");
const open = params.get("open");
for (let i = 0; i < 40 && (tab || open); i++) {
  await settle();
  if (tab) {
    const button = [...document.querySelectorAll<HTMLButtonElement>('[role="tab"]')].find((b) => b.textContent === (tab === "rules" ? "Rules" : "Watches"));
    if (button) { button.click(); break; }
  } else if (open) {
    const row = QUEUE.find((r) => r.alert.id === open);
    const button = row && [...document.querySelectorAll<HTMLButtonElement>("button[aria-pressed]")].find((b) => b.textContent?.includes(row.summary));
    if (button) { button.click(); break; }
  }
}

// `?sentence=preview` (with `tab=rules`): a sentence written blank by blank and previewed.
if (params.get("sentence") === "preview") {
  for (let i = 0; i < 40 && !choose("Subject", "Person"); i++) await settle();
  await settle();
  pressButton("Add a condition");
  await settle();
  choose("Condition 1: property", "listing");
  await settle();
  choose("Condition 1: test", "one_of");
  await settle();
  for (const value of ["sanction", "pep"]) document.querySelector<HTMLInputElement>(`[aria-label="Condition 1: ${value}"]`)?.click();
  await settle();
  choose("Frequency", "count");
  await settle();
  choose("Severity", "high");
  await settle();
  pressButton("Show the drawn pattern");
  await settle();
  pressButton("Preview on the last 90 days");
}
