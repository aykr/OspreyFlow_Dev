// Rules and Monitoring (ADR-146 decision 2; the Monitoring place before it) with a synthetic case's
// alerts of every kind (ADR-133 decision 5, stage (a)),
// served by the page itself: for the every-harness axe scan (`a11y/every-harness.spec.ts`, which
// finds this page by its directory) and for the Product Overview deck's screens, in both brands
// (`?brand=govuk`). Nothing here reaches a server. `?open=<id>` opens that alert; `?tab=rules`,
// `?tab=watches` and `?tab=lists` open *What raises alerts*, `?tab=held` *Held rows* and
// `?tab=changes` *Changes* (the owner's M1 tabs); `?address=missing` is an alert's address the
// reader may not see, or that does not exist (ADR-146 decision 6); `?tab=rules&sentence=preview` writes a rule as a sentence there and
// previews it (ADR-133 stage (b)). ADR-133 stage (c): `?tab=lists` opens the screening lists (with
// `&lists=manage`, as whoever may load them, after a refresh), and `?tab=rules&template=<typology>`
// fills the rule form from that template (the high-risk jurisdiction one with two codes). The data
// is synthetic (rule 9): invented names and numbers, and the user-assigned country codes XA and XB.
// ADR-133 stage (d): `?stage=d` adds a whole-deployment rule waiting for a second person, a rule that
// runs on a schedule, a high-severity alert whose close waits for approval (`open=a-close`) and a
// list refreshed on a schedule; it signs in as an administrator who did not propose the rule (so
// Approve is offered). `&opened=1` opens the scheduled rule's runs and versions; `&sentence=schedule`
// writes a sentence set to run every week.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { applyHarnessBrand } from "./brandHarness";
import { RulesPlace } from "../src/alerts/RulesPlace";

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
  // ADR-146 decision 8 and Amendment 1 (L2.10): a rule's alert routed to a team, suppressed by its
  // lead, opened by the lead (`?open=a-team`); and one taken back by a revert (G12).
  {
    alert: { ...base, id: "a-team", rule_id: "typology:r-daily", typology: "sentence", referent_node_ids: ["n4"], created_at: hoursAgo(50), status: "open", assignee: null,
      routed_team: "team-7", suppressed_until: "2026-12-01", suppress_reason: "A known pattern, reviewed weekly", suppressed_by: "analyst-1",
      words: "OKAFOR, Callum is a listed person", trigger: "post_commit", alert_node_id: null },
    summary: "OKAFOR, Callum is a listed person", kind: "typology", severity: "medium", audience: "team", team: "team-7", team_name: "Prison intel", suppressed: true,
  },
  {
    alert: { ...base, id: "a-back", rule_id: "typology:r1", typology: "structuring", referent_node_ids: ["n1"], created_at: hoursAgo(90), status: "closed", assignee: null, disposition: null,
      words: "3 movements under the threshold", trigger: "pre_commit", alert_node_id: null },
    summary: "3 movements under the threshold", kind: "typology", severity: "medium", audience: "case", team: null,
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

// ADR-133 stage (d): a whole-deployment rule waiting for a second person, and a rule on a schedule.
const STAGE_D = new URLSearchParams(window.location.search).get("stage") === "d";
const WIDE_RULE = {
  ...SENTENCE_RULE, id: "r-wide", name: "Sanctioned people, every case", status: "pending", owner_id: "analyst-1",
  pending_action: "deploy", pending_by: "analyst-1", pending_version: 1, trigger: "pre_commit",
  params: { ...SENTENCE_RULE.params, sentence: { ...SENTENCE_RULE.params.sentence, frequency: null, runs: "pre_commit",
    scope: "deployment", relationship: { kind: "on_screening_list", min_score: 0.9 }, conditions: [] } },
};  // prettier-ignore
const SCHEDULED_RULE = {
  ...SENTENCE_RULE, id: "r-daily", name: "Listed people, every morning", trigger: "schedule", version: 2,
  params: { ...SENTENCE_RULE.params, sentence: { ...SENTENCE_RULE.params.sentence, frequency: null, runs: "schedule",
    schedule: { every: "daily", hour: 6 } } },
};  // prettier-ignore
const RULE_RUNS = {
  rule_id: "r-daily", schedule: "every day at 06:00 (Europe/London)", state: "scheduled", words: null,
  next_run: new Date(NOW + 9 * 3_600_000).toISOString(),
  runs: [
    { id: "run-2", rule_id: "r-daily", rule_version: 2, slot: hoursAgo(15), ran_at: hoursAgo(15), run_as: "analyst-1",
      outcome: "ran", alerts: 2, words: "Ran as analyst-1 over the last day: 2 alert(s) raised." },
    { id: "run-1", rule_id: "r-daily", rule_version: 2, slot: hoursAgo(39), ran_at: hoursAgo(39), run_as: "analyst-1",
      outcome: "refused", alerts: 0, words: "Refused: the identity provider could not be reached to act as the rule's author." },
  ],
};  // prettier-ignore
const RULE_VERSIONS = [
  { rule_id: "r-daily", version: 1, action: "deploy", name: "Listed people, every morning", params: {}, trigger: "schedule",
    budget_ms: 5000, proposed_by: "analyst-1", proposed_by_name: "Ana Lyst", proposed_at: hoursAgo(200), status: "applied",
    decided_by: "analyst-1", decided_at: hoursAgo(200) },
  { rule_id: "r-daily", version: 2, action: "change", name: "Listed people, every morning", params: {}, trigger: "schedule",
    budget_ms: 5000, proposed_by: "analyst-2", proposed_by_name: "Priya Shah", proposed_at: hoursAgo(60), status: "applied",
    decided_by: "analyst-2", decided_at: hoursAgo(60) },
];  // prettier-ignore
if (STAGE_D) {
  QUEUE.unshift({
    alert: { ...base, id: "a-close", rule_id: "typology:r4", typology: "kyc_screening", referent_node_ids: ["n5"], created_at: hoursAgo(3),
      status: "closing", assignee: "analyst-1", disposition: "false_positive", disposition_reason: "A different company: registered 2019, not the listed party",
      close_proposed_by: "analyst-1", close_proposed_at: hoursAgo(1), words: "Harbour Freight Ltd is a close match (0.94) to a listed party",
      trigger: "pre_commit", alert_node_id: null },
    summary: "Harbour Freight Ltd is a close match (0.94) to a listed party", kind: "typology", severity: "high", audience: "case", team: null,
  } as never);  // prettier-ignore
}

// ADR-133 stage (c): the screening lists — synthetic, shaped as the Conduit sends them.
const LISTS = [
  { list_name: "Synthetic sanctions list", source: "opensanctions", location: "lists/synthetic_opensanctions_v2.ftm.json",
    dataset: null, synthetic: true, licence: "CC BY-NC 4.0: non-commercial use only, unless licensed by OpenSanctions",
    // The owner's answer of 1 November 2026: marked "licence not confirmed", with the reason.
    licence_confirmed: false,
    licence_note: "OpenSanctions is CC BY-NC 4.0, and screening in a business is commercial use, which needs OpenSanctions' own data licence",
    version: "sha256:3906852638793da1", entries: 10, updated_at: hoursAgo(1), attempted_at: hoursAgo(1), failure: null },
  { list_name: "Synthetic OFAC-format list", source: "ofac_sdn", location: "lists/SDN.CSV", dataset: null, synthetic: true,
    licence: "US Government work, in the public domain (17 U.S.C. §105)", version: "sha256:9c41d07be2a4f1e0", entries: 3,
    updated_at: hoursAgo(26), attempted_at: hoursAgo(2),
    failure: "The file could not be read as ofac_sdn: line 1 of SDN.CSV has no entry number (ent_num). The list was left as it was (version sha256:9c41d07be2a4f1e0)." },
];  // prettier-ignore
const REFRESHES = [
  { id: "u2", list_name: "Synthetic sanctions list", at: hoursAgo(1), outcome: "updated", version: "sha256:3906852638793da1",
    previous_version: "sha256:f0c7091a6a53d6a2", added: 1, changed: 1, delisted: 1, rescreened: 412, alerts: 1,
    words: "Version sha256:3906852638793da1: 1 added, 1 changed, 1 removed. 412 customers re-screened against 2 changed entries; 1 alert raised." },
  { id: "u1", list_name: "Synthetic OFAC-format list", at: hoursAgo(2), outcome: "failed", version: "sha256:9c41d07be2a4f1e0",
    previous_version: null, added: 0, changed: 0, delisted: 0, rescreened: 0, alerts: 0, words: LISTS[1].failure },
];  // prettier-ignore

function answer(path: string, search: URLSearchParams): unknown {
  if (path === "/v1/ontology") return ONTOLOGY;
  // ADR-133 stage (d): the first list refreshed on a schedule.
  const lists = STAGE_D
    ? [{ ...LISTS[0], schedule: { every: "daily", hour: 5 }, schedule_words: "every day at 05:00 (Europe/London)",
         schedule_owner: "analyst-1", next_refresh: new Date(NOW + 8 * 3_600_000).toISOString() }, LISTS[1]]
    : LISTS;  // prettier-ignore
  // The reader's route: no refreshes, and who a schedule runs as blanked, as the Conduit sends it.
  if (path === "/v1/screening-lists") return { lists: lists.map((l) => ({ ...l, schedule_owner: null })), can_manage: false };
  if (path === "/v1/admin/screening-lists") return { lists, updates: REFRESHES, can_manage: true };
  if (path.startsWith("/v1/admin/screening-lists/") && path.endsWith("/refresh")) return REFRESHES[0];
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
    // ADR-146: what fired a watch alert, and the lead's tools on the team's own alert.
    const fired = row.kind === "hotlist" || row.kind === "monitor"
      ? { fired_on: nodes.map((n) => ({ type: n.type, label: "A matched item", files: [{ name: "pid_seized_comms_batch2.csv", row: 3 }], more_files: 0 })) }
      : {};  // prettier-ignore
    const lead = row.alert.id === "a-team" ? { lead: true, team_name: "Prison intel", suppressed: true } : {};
    return { ...row, nodes, edges: [], transactions: [], ...fired, ...lead };
  }
  if (local === "alert-assignees") return [{ id: "analyst-1", name: "Ana Lyst" }, { id: "analyst-2", name: "Priya Shah" }];
  if (local === "rules") return STAGE_D ? [WIDE_RULE, SCHEDULED_RULE, SENTENCE_RULE] : [SENTENCE_RULE];
  if (local === "rules/r-daily/runs") return RULE_RUNS;
  if (local === "rules/r-daily/versions") return RULE_VERSIONS;
  if (local === "rules/preview") return PREVIEW;
  if (local === "rules/sentence/compile")
    return { words: SENTENCE_WORDS, pattern: { nodes: [{ var: "subject", entity_type: "Person", where: {} }], edges: [], limit: 50000 } };
  if (local === "patterns") return { patterns: [{ id: "sp1", pattern_id: "pat-1", version: 1, name: "Phone shared by two people", owner_id: "analyst-1", created_at: hoursAgo(500), definition: { nodes: [], edges: [] } }] };
  if (local === "hotlists") return HOTLISTS;
  if (local === "monitors") return { monitors: [{ id: "mo-1", pattern_id: "pat-1", owner_id: "analyst-1", status: "active", created_at: hoursAgo(500) }] };
  // ADR-146 decisions 5 and 8 (L2.10): the inventory and the teams a rule may go to.
  if (local === "alert-sources")
    return { sources: [
      { id: "r-daily", rule_id: "typology:r-daily", name: "Listed people", source: "rule", kind: "rule", maker: "analyst-1", maker_name: "Ana Lyst", owner: "Prison intel", state: "live", alerts_30_days: 4, not_of_interest: 0.25, last_fired_at: hoursAgo(30), suppressed: [{ alert_id: "a1", until: "2026-12-01", reason: "A known pattern", by: "analyst-1" }] },
      { id: "hl-1", rule_id: "hotlist:hl-1", name: "Hotlist 07700 900918", source: "watch", kind: "hotlist", maker: "analyst-1", owner: "analyst-1", state: "live", expires_on: "2027-01-31", alerts_30_days: 1, suppressed: [] },
    ] };  // prettier-ignore
  if (local === "alert-teams") return [{ role_id: "team-7", display_name: "Prison intel", lead: true, members: ["analyst-2"] }];
  return null;
}

window.fetch = async (input: RequestInfo | URL) => {
  const url = new URL(String(input));
  const body = answer(url.pathname, url.searchParams);
  return new Response(JSON.stringify(body ?? {}), { status: body === null ? 404 : 200 });
};

createRoot(document.getElementById("root")!).render(
  <RulesPlace
    apiBaseUrl="http://monitoring-harness.invalid"
    bearerToken="unused"
    investigationId="inv-1"
    accountId={STAGE_D ? "analyst-2" : "analyst-1"}
    isAdministrator={STAGE_D}
    canManageLists={new URLSearchParams(window.location.search).get("lists") === "manage"}
    onCanvas={() => undefined}
    address={
      new URLSearchParams(window.location.search).get("address") === "missing"
        ? { alertId: "gone", state: { status: "missing" } }
        : null
    }
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
    const label =
      { rules: "What raises alerts", watches: "What raises alerts", lists: "What raises alerts", held: "Held rows", changes: "Changes" }[tab] ??
      "Alerts";
    const button = [...document.querySelectorAll<HTMLButtonElement>('[role="tab"]')].find((b) => b.textContent === label);
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

// `?sentence=strength` (with `tab=rules`, ADR-139 decision 8): a sentence on connection strength.
// `?sentence=strength-client` (ADR-139 Amendment 2): the figure on the client's scale.
if (params.get("sentence") === "strength" || params.get("sentence") === "strength-client") {
  for (let i = 0; i < 40 && !choose("Subject", "Person"); i++) await settle();
  await settle();
  choose("Strength", "connection_strength");
  await settle();
  if (params.get("sentence") === "strength-client") {
    choose("On (scale, for strength)", "client");
    await settle();
  }
  choose("Reaches", params.get("sentence") === "strength-client" ? "1.2" : "0.85");
}

// `?template=<typology>` (with `tab=rules`): that template fills the form; a jurisdiction list is typed.
const template = params.get("template");
if (template) {
  const names: Record<string, string> = {
    high_risk_jurisdiction: "High-risk jurisdiction", large_cash: "Large cash",
    dormant_reactivated: "Dormant account reactivated", velocity_rise: "Sudden rise in velocity",
  };  // prettier-ignore
  for (let i = 0; i < 40 && !document.querySelector(`[aria-label="Use the template: ${names[template]}"]`); i++) await settle();
  document.querySelector<HTMLButtonElement>(`[aria-label="Use the template: ${names[template]}"]`)?.click();
  await settle();
  choose("High-risk jurisdictions", "XA, XB");
}

// `?lists=manage&tab=lists&refreshed=1`: a refresh just made, its words shown.
if (params.get("refreshed")) {
  for (let i = 0; i < 40 && !document.querySelector('[aria-label="Refresh now: Synthetic sanctions list"]'); i++) await settle();
  document.querySelector<HTMLButtonElement>('[aria-label="Refresh now: Synthetic sanctions list"]')?.click();
}

// `?opened=1` (with `stage=d&tab=rules`): the scheduled rule's runs and its versions shown.
if (params.get("opened")) {
  for (let i = 0; i < 40 && !document.querySelector('[aria-label="Schedule and runs of Listed people, every morning"]'); i++) await settle();
  document.querySelector<HTMLButtonElement>('[aria-label="Schedule and runs of Listed people, every morning"]')?.click();
  document.querySelector<HTMLButtonElement>('[aria-label="Versions of Listed people, every morning"]')?.click();
}

// `?sentence=schedule` (with `tab=rules`): a sentence set to run every week, on a Monday at 07:00.
if (params.get("sentence") === "schedule") {
  for (let i = 0; i < 40 && !choose("Subject", "Person"); i++) await settle();
  await settle();
  choose("Runs", "schedule");
  await settle();
  choose("Every", "weekly");
  await settle();
  choose("On (day of the week)", "1");
  choose("At (hour, Europe/London)", "7");
}
