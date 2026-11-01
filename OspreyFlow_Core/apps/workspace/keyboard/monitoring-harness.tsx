// The Monitoring place with a synthetic case's alerts of every kind (ADR-133 decision 5, stage (a)),
// served by the page itself: for the every-harness axe scan (`a11y/every-harness.spec.ts`, which
// finds this page by its directory) and for the Product Overview deck's screens, in both brands
// (`?brand=govuk`). Nothing here reaches a server. `?open=<id>` opens that alert; `?tab=rules` and
// `?tab=watches` open those tabs. The data is synthetic (rule 9): invented names and numbers.
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

function answer(path: string, search: URLSearchParams): unknown {
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
  if (local === "rules") return [];
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
