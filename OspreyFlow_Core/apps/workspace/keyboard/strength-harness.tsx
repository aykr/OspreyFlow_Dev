// The Monitoring place on its Connection strength tab (ADR-139 decision 3), served by the page itself:
// for `strength.spec.ts` and the every-harness axe scan (`a11y/every-harness.spec.ts`, which finds
// this page by its directory), in both brands (`?brand=govuk`). Nothing here reaches a server; what
// the page is sent is kept in `window.__STRENGTH__.sent`, so a spec can read it.
//
// `?as=checker` (the default) is a second holder of `manage_strength_influencers` with a version
// waiting (Approve offered); `?as=maker` is that version's proposer (Approve withheld, Withdraw
// offered); `?as=author` is the case's Author with nothing waiting (the case's own override offered,
// and a new installation version to propose); `?as=editor` reads what is in force alone. The data is
// synthetic (rule 9). `&composition=client_parity` (ADR-139 Amendment 2): the case already switched to
// client parity by its own override.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { applyHarnessBrand } from "./brandHarness";
import { AlertsPlace } from "../src/alerts/AlertsPlace";
import type { EdgeTypeDef, EntityTypeDef } from "../../../packages/schemas/generated";

declare global {
  interface Window {
    __STRENGTH__?: { sent: { method: string; path: string; body: unknown }[] };
  }
}

await applyHarnessBrand();

const params = new URLSearchParams(window.location.search);
const as = params.get("as") ?? "checker";
window.__STRENGTH__ = { sent: [] };

const DIRECT = {
  id: "direct", label: "Direct link", link_types: ["COMMUNICATED_WITH", "VISITED", "SHARED_CELL_WITH"], change: "add",
  size: 0.1348, trigger: null, enabled: true, note: "to be confirmed with the client",
}; // prettier-ignore
const SOURCE = {
  id: "incident-source", label: "Evidenced by an assault, disorder or find", link_types: ["ROLE_IN", "IN_CONFLICT_WITH"],
  change: "add", size: 0.1348, trigger: { entity_type: "Incident", property: "category", values: ["assault", "disorder", "find"] },
  enabled: true, note: "to be confirmed with the client",
}; // prettier-ignore
const WAITING = {
  version: 2, influencers: [DIRECT, { ...SOURCE, size: 0.2 }], status: "pending", proposed_by: "analyst-maker",
  proposed_by_name: "Priya Shah", proposed_at: "2026-11-02T09:15:00Z", words: "The client's boost for a source, as agreed on the call",
  in_force: false,
}; // prettier-ignore
const APPROVED = {
  version: 1, influencers: [DIRECT, SOURCE], status: "approved", proposed_by: "analyst-checker", proposed_by_name: "Tom Okoro",
  proposed_at: "2026-11-01T10:00:00Z", decided_by: "analyst-maker", decided_by_name: "Priya Shah", decided_at: "2026-11-01T11:00:00Z",
  in_force: true, words: "",
}; // prettier-ignore

const state = {
  waiting: as === "checker" || as === "maker",
  override: (params.get("composition") === "client_parity"
    ? { added: [], switched_off: [], composition: "client_parity" }
    : null) as null | { added: unknown[]; switched_off: string[]; composition?: string | null },
};

function legend() {
  const off = state.override?.switched_off ?? [];
  const added = (state.override?.added ?? []) as { id: string }[];
  return {
    legend: {
      influencers: [
        ...[DIRECT, SOURCE].filter((i) => !off.includes(i.id)).map((i) => ({ influencer: i, layer: "installation", version: 1 })),
        ...added.map((i) => ({ influencer: i, layer: "case", version: 1 })),
      ],
      direct_link_types: off.includes("direct") ? [] : DIRECT.link_types,
      switched_off: off,
      rarity_note:
        "Shared-attribute rarity is worked out over what you may see: two analysts with different access can see different rarity for the same pair.",
      composition: state.override?.composition ?? "standard",
      composition_layer: state.override?.composition ? "case" : "file",
      rarity_measure: "share",
    },
    override: state.override,
    can_override: as === "author",
  };
}

window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
  const path = new URL(String(input)).pathname;
  const method = init?.method ?? "GET";
  const body = init?.body ? JSON.parse(String(init.body)) : null;
  window.__STRENGTH__!.sent.push({ method, path, body });
  const json = (status: number, value: unknown) => new Response(JSON.stringify(value), { status });
  if (path === "/v1/investigations/inv-1/strength-influencers") {
    if (method === "PUT")
      state.override = { added: body.added, switched_off: body.switched_off, composition: body.composition ?? null };
    return json(200, legend());
  }
  if (path === "/v1/strength-influencers" && method === "GET")
    return json(200, {
      versions: state.waiting ? [WAITING, APPROVED] : [APPROVED],
      defaults: [DIRECT, SOURCE],
      default_composition: "standard",
      default_rarity_measure: "share",
    });
  if (path === "/v1/strength-influencers" && method === "POST") {
    state.waiting = true;
    return json(201, { ...WAITING, version: 3, influencers: body.influencers, proposed_by: `analyst-${as}` });
  }
  if (path.endsWith("/approve")) {
    state.waiting = false;
    return json(200, { ...WAITING, status: "approved", in_force: true });
  }
  if (path.endsWith("/send-back")) {
    state.waiting = false;
    return json(200, { ...WAITING, status: "sent_back", decision_words: body.words });
  }
  // Everything else Monitoring reads on its way in: nothing here.
  if (path.endsWith("/investigations")) return json(200, [{ id: "inv-1", name: "Prison Intelligence", level: as === "author" ? "author" : "editor" }]);
  return json(200, []);
};

const ENTITIES = [
  { name: "Person", pole_class: "person", channel: "indigo", shape: "circle", identifiers: [], properties: [{ name: "family_name", type: "string" }] },
  { name: "Incident", pole_class: "event", channel: "plum", shape: "hexagon", identifiers: [], properties: [
    { name: "category", type: "enum", values: ["assault", "disorder", "find", "other", "throw_over"] }] },
] as unknown as EntityTypeDef[]; // prettier-ignore
const EDGES = [
  { name: "COMMUNICATED_WITH", label: "Communicated with", from: ["Endpoint"], to: ["Endpoint"] },
  { name: "VISITED", label: "Visited", from: ["Person"], to: ["Person"] },
  { name: "SHARED_CELL_WITH", label: "Shared a cell with", from: ["Person"], to: ["Person"] },
  { name: "IN_CONFLICT_WITH", label: "In conflict with", from: ["Person"], to: ["Person"] },
  { name: "ROLE_IN", label: "Role in", from: ["Person"], to: ["Incident"] },
] as unknown as EdgeTypeDef[]; // prettier-ignore

createRoot(document.getElementById("root")!).render(
  <AlertsPlace
    apiBaseUrl="http://strength-harness.invalid"
    bearerToken="unused"
    investigationId="inv-1"
    accountId={`analyst-${as}`}
    isAdministrator={false}
    canManageInfluencers={as !== "editor"}
    entityTypes={ENTITIES}
    edgeTypes={EDGES}
    onCanvas={() => undefined}
  />,
);

// The page opens on the Connection strength tab, as a reader would reach it by keyboard.
for (let i = 0; i < 40; i++) {
  await new Promise((resolve) => setTimeout(resolve, 50));
  const tab = [...document.querySelectorAll<HTMLButtonElement>('[role="tab"]')].find((b) => b.textContent === "Connection strength");
  if (tab) {
    if (params.get("open") !== "queue") tab.click();
    break;
  }
}
