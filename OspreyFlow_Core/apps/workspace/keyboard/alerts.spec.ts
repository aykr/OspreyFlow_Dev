// A keyboard-only walkthrough of the Alerts place (ADR-109 phase B, `CLAUDE.md` rule 13): open an
// alert from the queue, claim and release it, show it on the canvas, close it with a reason, filter
// the queue; deploy and retire a rule; release and reject held rows; page the rule audit — no
// `page.mouse`, no `.click()`. Each action proves its effect reached the server (or the canvas
// callback), not merely that a control received focus.
import { expect, test, type Locator, type Page } from "@playwright/test";

import { ALERTS_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";
import { chooseByTyping } from "./chooseByTyping";

const REGISTRY = "ALERTS_ACTIONS";

function account(id: string, name: string) {
  return {
    id,
    type: "Account",
    properties: { account_number: name },
    provenance: { state: "asserted", sources: [], first_seen: "2026-01-01T00:00:00Z" },
    handling: { classification: "OFFICIAL", handling_code: "P", originator: "u", owning_unit: "u" },
    audit: { created_at: "2026-01-01T00:00:00Z", created_by: "seed", revision: 1 },
  };
}

interface State {
  status: "open" | "claimed" | "closed";
  assignee: string | null;
  rules: Record<string, unknown>[];
  held: Record<string, unknown>[];
  sent: { method: string; path: string; body: unknown }[];
  queueFilters: string[];
  queueSearches: string[];
}

function alert(state: State) {
  return {
    id: "a1", rule_id: "typology:r1", owner_id: "deployer", mode: "full",
    referent_node_ids: ["n1", "n2"], investigation_id: "inv-1", created_at: "2026-09-01T12:00:00Z",
    typology: "structuring", words: "4 movements from n1 to n2", edge_ids: ["e1"], event_ids: ["v1"],
    window: { valid_from: "2026-09-01T09:00:00Z", valid_to: "2026-09-01T12:00:00Z" },
    trigger: "pre_commit", alert_node_id: "al1", status: state.status, assignee: state.assignee,
  };  // prettier-ignore
}

const AUDIT = Array.from({ length: 60 }, (_, i) => ({
  recorded_at: `2026-09-01T12:${String(i % 60).padStart(2, "0")}:00Z`,
  principal_id: "analyst-1",
  action: i % 2 ? "rule_evaluated" : "rule_fired",
  detail: { rule_id: "r1", trigger: "pre_commit", findings: 1 },
  result_cardinality: 1,
}));

async function serve(page: Page, level: "editor" | "author" = "author"): Promise<State> {
  const state: State = {
    status: "open",
    assignee: null,
    rules: [
      {
        id: "r1", investigation_id: "inv-1", owner_id: "analyst-1", name: "Deposits", status: "active",
        created_at: "2026-09-01T00:00:00Z", trigger: "pre_commit", budget_ms: 5000,
        params: { typology: "structuring", threshold: 10000, window_days: 7, minimum_count: 3 },
      },
    ],
    held: [
      {
        id: "h1", investigation_id: "inv-1", recipe_id: "ledger", recipe_version: 1, load_id: "L1",
        source: "export.csv", row_index: 4, row: { amount: "9500" }, rule_id: "r1",
        reason: "it overran its 5,000 ms budget", status: "held", held_at: "2026-09-01T12:00:00Z",
        handling: { classification: "OFFICIAL", handling_code: "P", originator: "u", owning_unit: "u" },
      },
      {
        id: "h2", investigation_id: "inv-1", recipe_id: "ledger", recipe_version: 1, load_id: "L2",
        source: "export.csv", row_index: 9, row: { amount: "9600" }, rule_id: "r1",
        reason: "it overran its 5,000 ms budget", status: "held", held_at: "2026-09-02T12:00:00Z",
        handling: { classification: "OFFICIAL", handling_code: "P", originator: "u", owning_unit: "u" },
      },
    ],
    sent: [],
    queueFilters: [],
    queueSearches: [],
  };  // prettier-ignore
  await page.route("**/*/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace("/v1/investigations/inv-1/", "");
    const method = request.method();
    const json = (status: number, body: unknown) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (method === "POST") state.sent.push({ method, path, body: request.postDataJSON() });
    if (url.pathname === "/v1/investigations")
      return json(200, [{ id: "inv-1", name: "Ledger", level, created_at: "", created_by: "" }]);
    if (path === "alert-queue") {
      state.queueFilters.push(url.searchParams.get("status") ?? "");
      state.queueSearches.push(url.search);
      return json(200, [{ alert: alert(state), summary: "4 movements from GB-MULE to GB-HUB" }]);
    }
    if (path === "alert-queue/a1")
      return json(200, {
        alert: alert(state),
        summary: "4 movements from GB-MULE to GB-HUB",
        nodes: [account("n1", "GB-MULE"), account("n2", "GB-HUB")],
        edges: [],
        transactions: [
          { event_id: "v1", edge_id: "e1", source_id: "n1", target_id: "n2", occurred_at: "2026-09-01T09:00:00Z", amount: 9500 },
        ],
      });
    if (path === "alert-queue/a1/claim") {
      state.status = "claimed";
      state.assignee = "analyst-1";
      return json(200, alert(state));
    }
    if (path === "alert-queue/a1/release") {
      state.status = "open";
      state.assignee = null;
      return json(200, alert(state));
    }
    if (path === "alert-queue/a1/disposition") {
      state.status = "closed";
      return json(200, alert(state));
    }
    if (path === "alert-assignees")
      return json(200, [{ id: "analyst-1", name: "Ana Lyst" }, { id: "analyst-2", name: "Priya Shah" }]);
    if (path === "alert-queue/a1/assign") {
      state.status = "claimed";
      state.assignee = (request.postDataJSON() as { assignee: string }).assignee;
      return json(200, alert(state));
    }
    if (path === "alert-queue/a1/canvas")
      return json(200, { delta: { seq: 2, op: "add", nodes: [], edges: [] }, added_nodes: 3, added_links: 3 });
    if (path === "patterns")
      return json(200, { patterns: [{ id: "sp1", pattern_id: "pat-1", version: 1, name: "Company with a phone",
        owner_id: "analyst-1", created_at: "2026-10-01T00:00:00Z", definition: { nodes: [], edges: [] } }] });  // prettier-ignore
    if (path === "rules" && method === "GET") return json(200, state.rules);
    if (path === "rules" && method === "POST") {
      const made = { ...(request.postDataJSON() as object), id: "r2", investigation_id: "inv-1", owner_id: "analyst-1", status: "active", created_at: "2026-09-03T00:00:00Z" };
      state.rules = [made, ...state.rules];
      return json(201, made);
    }
    if (path === "rules/r1/retire") {
      state.rules = state.rules.map((r) => (r.id === "r1" ? { ...r, status: "retired" } : r));
      return json(200, state.rules.find((r) => r.id === "r1"));
    }
    if (path === "rules/audit") {
      const offset = Number(url.searchParams.get("offset") ?? 0);
      return json(200, { entries: AUDIT.slice(offset, offset + 50), total: AUDIT.length });
    }
    // ADR-133 stage (b): the ontology the sentence builder offers its blanks from, the preview,
    // the drawn pattern and the deploy.
    if (url.pathname === "/v1/ontology") return json(200, ONTOLOGY);
    // ADR-146 decision 3 (L2.11): the datasets the rule editor offers; none unless a case asks.
    if (path === "rules/datasets") return json(200, []);
    if (path === "rules/preview")
      return json(200, { days: 90, would_raise: 2, words: "When a Person…", examples: [
        { node_id: "p1", name: "Callum Okafor", entity_type: "Person", words: "Callum Okafor (Person)" },
        { node_id: "p2", name: "Dana Okafor", entity_type: "Person", words: "Dana Okafor (Person)" }] });  // prettier-ignore
    if (path === "rules/sentence/compile")
      return json(200, { words: "When a Person whose listing is one of sanction, pep, raise a high-severity alert for the case team, after each load commits.",
        pattern: { nodes: [{ var: "subject", entity_type: "Person", where: {} }], edges: [], limit: 50000 } });  // prettier-ignore
    if (path === "rules/sentence" && method === "POST") {
      const body = request.postDataJSON() as { name: string; sentence: unknown };
      const made = { name: body.name, id: "r3", investigation_id: "inv-1", owner_id: "analyst-1", status: "active", trigger: "post_commit",
        created_at: "2026-11-01T00:00:00Z", params: { typology: "sentence", pattern_id: "pat-9", sentence: body.sentence } };  // prettier-ignore
      state.rules = [made, ...state.rules];
      return json(201, made);
    }
    // ADR-133 stage (c): the screening lists (synthetic, rule 9).
    if (url.pathname === "/v1/screening-lists") return json(200, { lists: LISTS, can_manage: false });
    if (url.pathname === "/v1/admin/screening-lists" && method === "GET") return json(200, { lists: LISTS, updates: [], can_manage: true });
    if (url.pathname === "/v1/admin/screening-lists" && method === "POST")
      return json(201, { ...LISTS[0], ...(request.postDataJSON() as object), version: null, entries: 0, updated_at: null });
    if (url.pathname === "/v1/admin/screening-lists/Synthetic%20list/refresh")
      return json(200, { id: "u1", list_name: "Synthetic list", at: "2026-11-01T09:00:00Z", outcome: "updated", added: 1, changed: 1,
        delisted: 1, rescreened: 4, alerts: 1, words: "Version v2: 1 added, 1 changed, 1 removed. 4 customers re-screened against 2 changed entries; 1 alert raised." });  // prettier-ignore
    if (path === "held-rows") return json(200, state.held);
    if (path === "held-rows/reject") {
      const ids = (request.postDataJSON() as { ids: string[] }).ids;
      state.held = state.held.filter((h) => !ids.includes(h.id as string));
      return json(200, []);
    }
    if (path === "ingest/recipes/ledger/held-rows/release") {
      const ids = (request.postDataJSON() as { ids: string[] }).ids;
      state.held = state.held.filter((h) => !ids.includes(h.id as string));
      return json(200, { edges_created: 1, nodes_created: 2, rule_notes: [] });
    }
    return json(404, {});
  });
  return state;
}

const LISTS = [
  { list_name: "Synthetic list", source: "opensanctions", location: "lists/synthetic_opensanctions_v1.ftm.json", dataset: null,
    synthetic: true, licence: "CC BY-NC 4.0: non-commercial use only, unless licensed by OpenSanctions", version: "v1",
    entries: 10, updated_at: "2026-11-01T08:00:00Z", attempted_at: "2026-11-01T08:00:00Z", failure: null },
];  // prettier-ignore

const ONTOLOGY = {
  version: 1,
  entity_types: [
    { name: "Person", pole_class: "person", channel: "indigo", shape: "circle", identifiers: [], properties: [
      { name: "family_name", type: "string", indexed: true },
      { name: "listing", type: "enum", values: ["sanction", "pep", "adverse_media"] }] },
    { name: "Location", pole_class: "location", channel: "ochre", shape: "pin", identifiers: [], properties: [] },
  ],
  edge_types: [{ name: "PRESENT_AT", from: ["Person"], to: ["Location"], temporal: true, basis: "direct", label: "Present at" }],
};  // prettier-ignore

async function press(page: Page, target: Locator) {
  await target.focus();
  await page.keyboard.press("Enter");
}


async function openTheAlert(page: Page) {
  await press(page, page.getByRole("button", { name: /Open alert: Medium severity, Structuring — / }));
  await expect(page.getByRole("table", { name: "Transactions this alert cites" })).toBeVisible();
}

test("an alert opens from the queue and explains itself, by keyboard", async ({ page }) => {
  await serve(page);
  await page.goto("/keyboard/alerts-harness.html");
  await openTheAlert(page);
  await expect(page.getByRole("cell", { name: "GB-MULE" })).toBeVisible();
  registerCovered(REGISTRY, "open-an-alert-from-the-queue-by-keyboard");
});

test("an alert is claimed and released, by keyboard", async ({ page }) => {
  const state = await serve(page);
  await page.goto("/keyboard/alerts-harness.html");
  await openTheAlert(page);
  await press(page, page.getByRole("button", { name: "Claim" }));
  await expect(page.getByText("You have claimed this alert.")).toBeVisible();
  expect(state.sent.map((s) => s.path)).toContain("alert-queue/a1/claim");
  registerCovered(REGISTRY, "claim-an-alert-by-keyboard");
  await press(page, page.getByRole("button", { name: "Release" }));
  await expect(page.getByText("Released for someone else.")).toBeVisible();
  expect(state.status).toBe("open");
  registerCovered(REGISTRY, "release-an-alert-by-keyboard");
});

test("an alert goes onto the canvas with its nodes to highlight, by keyboard", async ({ page }) => {
  await serve(page);
  await page.goto("/keyboard/alerts-harness.html");
  await openTheAlert(page);
  await press(page, page.getByRole("button", { name: "Show on the canvas" }));
  await expect.poll(() => page.evaluate(() => window.__ALERTS__?.canvasNodeIds)).toEqual(["n1", "n2"]);
  registerCovered(REGISTRY, "show-an-alert-on-the-canvas-by-keyboard");
});

test("an alert is closed with its reason, by keyboard", async ({ page }) => {
  const state = await serve(page);
  await page.goto("/keyboard/alerts-harness.html");
  await openTheAlert(page);
  // The closing reason: one of the owner's closed list, chosen with Space on the first.
  await page.getByRole("radio", { name: "True match" }).focus();
  await page.keyboard.press("Space");
  await expect(page.getByRole("radio", { name: "True match" })).toBeChecked();
  await page.getByLabel("Why, in words: the reason for closing").fill("Matches the SAR");
  await press(page, page.getByRole("button", { name: "Close the alert" }));
  await expect(page.getByText(/Closed as True match/).first()).toBeVisible();
  expect(state.sent.find((s) => s.path === "alert-queue/a1/disposition")?.body).toEqual({
    disposition: "true_positive",
    reason: "Matches the SAR",
  });
  registerCovered(REGISTRY, "close-an-alert-with-a-reason-by-keyboard");
});

test("a closing reason is chosen from the closed list with the arrow keys, by keyboard", async ({ page }) => {
  const state = await serve(page);
  await page.goto("/keyboard/alerts-harness.html");
  await openTheAlert(page);
  const close = page.getByRole("button", { name: "Close the alert" });
  await page.getByLabel("Why, in words: the reason for closing").fill("Passed to the NCA");
  await expect(close).toBeDisabled(); // words alone are not a closing reason
  await page.getByRole("radio", { name: "True match" }).focus();
  for (let i = 0; i < 4; i += 1) await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("radio", { name: "Referred" })).toBeChecked();
  await expect(page.getByRole("radio", { name: "Referred" })).toBeFocused();
  await press(page, close);
  expect(state.sent.find((s) => s.path === "alert-queue/a1/disposition")?.body).toEqual({
    disposition: "referred",
    reason: "Passed to the NCA",
  });
  registerCovered(REGISTRY, "choose-a-closing-reason-by-keyboard");
});

test("the watches are reached with the rules, by keyboard (ADR-146: one queue, the inbox gone)", async ({ page }) => {
  // ADR-146: the hotlists and watched patterns are kept with the rules (*What raises alerts*); the
  // inbox went in L2.10, its alerts in the one queue.
  await serve(page);
  const fulfil = (body: unknown, status = 200) => ({ status, contentType: "application/json", body: JSON.stringify(body) });
  await page.route("**/*/v1/investigations/inv-1/hotlists", (route) => route.fulfill(fulfil({ hotlists: [], audience_default: "only_me", audience_editable: true })));
  await page.route("**/*/v1/investigations/inv-1/monitors", (route) => route.fulfill(fulfil({ monitors: [] })));
  await page.route("**/*/v1/investigations/inv-1/patterns", (route) => route.fulfill(fulfil({ patterns: [] })));
  await page.goto("/keyboard/alerts-harness.html");
  await expect(page.getByRole("button", { name: /Open alert:/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Alert inbox" })).toHaveCount(0);
  await press(page, page.getByRole("tab", { name: "What raises alerts" }));
  await expect(page.getByRole("heading", { name: "Hotlists" })).toBeVisible();
  registerCovered(REGISTRY, "reach-the-watches-kept-with-the-rules-by-keyboard");
});

test("the queue is filtered by whose and by age, by keyboard (ADR-146 decision 2)", async ({ page }) => {
  const state = await serve(page);
  await page.goto("/keyboard/alerts-harness.html");
  await chooseByTyping(page, page.getByRole("combobox", { name: "Whose alerts" }), "unassigned");
  await expect.poll(() => state.queueSearches).toContain("?status=active&show=unassigned");
  await page.getByRole("spinbutton", { name: "Older than, in days" }).focus();
  await page.keyboard.type("7");
  await expect.poll(() => state.queueSearches).toContain("?status=active&show=unassigned&older_than_days=7");
  registerCovered(REGISTRY, "filter-the-queue-by-whose-and-age-by-keyboard");
});

async function serveARoutedAlert(page: Page, state: State) {
  const routed = { ...alert(state), routed_team: "team-7" };
  const fulfil = (body: unknown) => ({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  await page.route("**/*/v1/investigations/inv-1/alert-queue?*", (route) =>
    route.fulfill(fulfil([{ alert: routed, summary: "4 movements from GB-MULE to GB-HUB", audience: "team", team: "team-7", team_name: "Prison intel" }])),
  );
  await page.route("**/*/v1/investigations/inv-1/alert-queue/a1", (route) =>
    route.fulfill(fulfil({
      alert: routed, summary: "4 movements from GB-MULE to GB-HUB", audience: "team", team: "team-7", team_name: "Prison intel",
      lead: true, nodes: [account("n1", "GB-MULE"), account("n2", "GB-HUB")], edges: [],
      transactions: [{ event_id: "v1", edge_id: "e1", source_id: "n1", target_id: "n2", occurred_at: "2026-09-01T09:00:00Z", amount: 9500 }],
    })),
  );  // prettier-ignore
  await page.route("**/*/v1/investigations/inv-1/alert-teams", (route) =>
    route.fulfill(fulfil([{ role_id: "team-7", display_name: "Prison intel", lead: true, members: ["analyst-2"], member_names: { "analyst-2": "Priya Shah" } }])),
  );
  await page.route("**/*/v1/investigations/inv-1/alert-queue/a1/suppress", (route) => {
    state.sent.push({ method: "POST", path: "alert-queue/a1/suppress", body: route.request().postDataJSON() });
    return route.fulfill(fulfil({ ...routed, suppressed_until: "2026-12-01" }));
  });
}

test("a team's lead gives one of its alerts to a member, by keyboard (ADR-146 Amendment 1)", async ({ page }) => {
  const state = await serve(page);
  await serveARoutedAlert(page, state);
  await page.goto("/keyboard/alerts-harness.html");
  await openTheAlert(page);
  const lead = page.getByRole("group", { name: "As the team's lead" });
  const give = lead.getByRole("combobox", { name: "Give to (a member of the team)" });
  // ADR-106: each member by name, never by their identity-provider id.
  await expect(give.getByRole("option", { name: "Priya Shah" })).toHaveCount(1);
  await chooseByTyping(page, give, "analyst-2");
  await press(page, lead.getByRole("button", { name: "Give to the member" }));
  await expect.poll(() => state.sent.find((s) => s.path === "alert-queue/a1/assign")?.body).toEqual({ assignee: "analyst-2" });
  registerCovered(REGISTRY, "give-a-team-alert-to-a-member-by-keyboard");
});

test.describe("a date typed as a person types it", () => {
  // Day, month, year: the segments a British browser's date field takes, whatever the machine's.
  test.use({ locale: "en-GB" });

test("a team's lead suppresses one of its alerts until a day, with a reason, by keyboard (ADR-146 Amendment 1)", async ({ page }) => {
  const state = await serve(page);
  await serveARoutedAlert(page, state);
  await page.goto("/keyboard/alerts-harness.html");
  await openTheAlert(page);
  const lead = page.getByRole("group", { name: "As the team's lead" });
  // A native date field, its day, month and year typed as segments (the locale is set above).
  const until = lead.getByLabel("Suppress until (at most 90 days ahead)");
  await until.focus();
  await page.keyboard.type("01122026");
  await expect(until).toHaveValue("2026-12-01");
  await lead.getByLabel("Why, in words: the reason for suppressing it").focus();
  await page.keyboard.type("A known pattern, reviewed weekly");
  await press(page, lead.getByRole("button", { name: "Suppress until…" }));
  await expect.poll(() => state.sent.find((s) => s.path === "alert-queue/a1/suppress")?.body).toEqual({
    until: "2026-12-01", reason: "A known pattern, reviewed weekly",
  });  // prettier-ignore
  registerCovered(REGISTRY, "suppress-a-team-alert-by-keyboard");
});
});

test("What raises alerts is filtered by a column, by keyboard (ADR-146 decision 5)", async ({ page }) => {
  await serve(page);
  await page.route("**/*/v1/investigations/inv-1/alert-sources", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ sources: [
      { id: "r1", rule_id: "typology:r1", name: "Deposits", source: "rule", kind: "rule", maker: "analyst-1", owner: "analyst-1", state: "live", alerts_30_days: 3, suppressed: [] },
      { id: "h1", rule_id: "hotlist:h1", name: "Hotlist 07700 900918", source: "watch", kind: "hotlist", maker: "analyst-1", owner: "analyst-1", state: "live", alerts_30_days: 1, suppressed: [] },
    ] }) }),
  );  // prettier-ignore
  await page.goto("/keyboard/alerts-harness.html");
  await press(page, page.getByRole("tab", { name: "What raises alerts" }));
  const table = page.getByRole("table", { name: "Rules and watches" });
  await expect(table.getByText("Deposits")).toBeVisible();
  await page.getByRole("textbox", { name: "Filter by source" }).focus();
  await page.keyboard.type("watch");
  await expect(table.getByText("Deposits")).toHaveCount(0);
  await expect(table.getByText("Hotlist 07700 900918")).toBeVisible();
  registerCovered(REGISTRY, "filter-what-raises-alerts-by-keyboard");
});

test("the queue is filtered, by keyboard", async ({ page }) => {
  const state = await serve(page);
  await page.goto("/keyboard/alerts-harness.html");
  await page.getByRole("combobox", { name: "Show which alerts" }).selectOption("closed");
  await expect.poll(() => state.queueFilters).toContain("closed");
  registerCovered(REGISTRY, "filter-the-queue-by-keyboard");
});

test("the queue is filtered by kind and severity, by keyboard (ADR-133 stage a)", async ({ page }) => {
  const state = await serve(page);
  await page.goto("/keyboard/alerts-harness.html");
  // A native select, chosen as "the queue is filtered" chooses one (its keyboard is the browser's).
  await page.getByRole("combobox", { name: "Kind of alert" }).selectOption("hotlist");
  await expect.poll(() => state.queueSearches).toContain("?status=active&kind=hotlist");
  await page.getByRole("combobox", { name: "Severity" }).selectOption("high");
  await expect.poll(() => state.queueSearches).toContain("?status=active&kind=hotlist&severity=high");
  registerCovered(REGISTRY, "filter-the-queue-by-kind-and-severity-by-keyboard");
});

test("a case alert is given to a member, by keyboard (ADR-133 stage a)", async ({ page }) => {
  const state = await serve(page);
  await page.goto("/keyboard/alerts-harness.html");
  await openTheAlert(page);
  await page.getByRole("combobox", { name: "Give to (a member of the case)" }).selectOption("analyst-2");
  await press(page, page.getByRole("button", { name: "Give", exact: true }));
  await expect(page.getByText("Given to Priya Shah.")).toBeVisible();
  expect(state.sent.find((s) => s.path === "alert-queue/a1/assign")?.body).toEqual({ assignee: "analyst-2" });
  expect(state.assignee).toBe("analyst-2");
  registerCovered(REGISTRY, "give-an-alert-to-a-member-by-keyboard");
});

test("a template fills the rule form, which is then deployed, by keyboard (ADR-133 stage a)", async ({ page }) => {
  const state = await serve(page);
  await page.goto("/keyboard/alerts-harness.html");
  await press(page, page.getByRole("tab", { name: "What raises alerts" }));
  await press(page, page.getByRole("button", { name: "Use the template: Circular flow" }));
  // The keyboard is put on the filled form's name.
  await expect(page.getByLabel("Rule name")).toBeFocused();
  await expect(page.getByLabel("Rule name")).toHaveValue("Circular flow");
  await press(page, page.getByRole("button", { name: "Deploy", exact: true }));
  await expect(page.getByText("Deployed “Circular flow”.")).toBeVisible();
  expect(state.sent.find((s) => s.path === "rules")?.body).toEqual({
    name: "Circular flow",
    params: { typology: "circular_flow", max_hops: 4, window_days: 30 },
    trigger: "post_commit",
    budget_ms: 5000,
  });
  registerCovered(REGISTRY, "use-a-template-by-keyboard");
});

test("a rule is deployed and another retired, by keyboard", async ({ page }) => {
  const state = await serve(page);
  await page.goto("/keyboard/alerts-harness.html");
  await press(page, page.getByRole("tab", { name: "What raises alerts" }));
  await page.getByLabel("Rule name").fill("Pass-through");
  await page.getByRole("combobox", { name: "Typology" }).selectOption("rapid_movement");
  await page.getByRole("combobox", { name: "When the rule runs" }).selectOption("pre_commit");
  await press(page, page.getByRole("button", { name: "Deploy", exact: true }));
  await expect(page.getByText("Deployed “Pass-through”.")).toBeVisible();
  expect(state.sent.find((s) => s.path === "rules")?.body).toEqual({
    name: "Pass-through",
    params: { typology: "rapid_movement", within_hours: 48, keep_fraction: 0.8 },
    trigger: "pre_commit",
    budget_ms: 5000,
  });
  registerCovered(REGISTRY, "deploy-a-rule-by-keyboard");
  await press(page, page.getByRole("button", { name: "Retire Deposits" }));
  await expect(page.getByText("Retired “Deposits”.")).toBeVisible();
  registerCovered(REGISTRY, "retire-a-rule-by-keyboard");
});

test("a KYC screening rule is deployed with its switch, by keyboard", async ({ page }) => {
  const state = await serve(page);
  await page.goto("/keyboard/alerts-harness.html");
  await press(page, page.getByRole("tab", { name: "What raises alerts" }));
  await page.getByLabel("Rule name").fill("Onboarding screen");
  await page.getByRole("combobox", { name: "Typology" }).selectOption("kyc_screening");
  await page.getByRole("checkbox", { name: "Screen beneficial owners too" }).focus();
  await page.keyboard.press("Space");
  await press(page, page.getByRole("button", { name: "Deploy", exact: true }));
  await expect(page.getByText("Deployed “Onboarding screen”.")).toBeVisible();
  expect(state.sent.find((s) => s.path === "rules")?.body).toEqual({
    name: "Onboarding screen",
    params: { typology: "kyc_screening", min_score: 0.9, owner_threshold: 25, screen_owners: false },
    trigger: "post_commit",
    budget_ms: 5000,
  });
  registerCovered(REGISTRY, "deploy-a-kyc-rule-by-keyboard");
});

test("a pattern drawn in the Query builder is deployed as a rule, by keyboard", async ({ page }) => {
  const state = await serve(page);
  await page.goto("/keyboard/alerts-harness.html");
  await press(page, page.getByRole("tab", { name: "What raises alerts" }));
  await page.getByLabel("Rule name").fill("Drawn: company with a phone");
  await page.getByRole("combobox", { name: "Typology" }).selectOption("pattern");
  // The rule form's own: *What raises alerts* also holds the watched patterns' (ADR-146 decision 5).
  const form = page.getByRole("form", { name: "Deploy a rule" });
  await form.getByRole("combobox", { name: "Saved pattern", exact: true }).selectOption("pat-1");
  await press(page, page.getByRole("button", { name: "Deploy", exact: true }));
  await expect(page.getByText("Deployed “Drawn: company with a phone”.")).toBeVisible();
  expect(state.sent.find((s) => s.path === "rules")?.body).toEqual({
    name: "Drawn: company with a phone",
    params: { typology: "pattern", pattern_id: "pat-1", max_matches: 200 },
    trigger: "post_commit",
    budget_ms: 5000,
  });
  registerCovered(REGISTRY, "deploy-a-drawn-pattern-rule-by-keyboard");
});

test("held rows are released and rejected, by keyboard", async ({ page }) => {
  const state = await serve(page);
  await page.goto("/keyboard/alerts-harness.html");
  await press(page, page.getByRole("tab", { name: "Held rows" }));
  const first = page.getByRole("region", { name: "Held from load L1" });
  await press(page, first.getByRole("button", { name: "Release and load" }));
  await expect(page.getByText(/Released and loaded/)).toBeVisible();
  expect(state.sent.find((s) => s.path.endsWith("held-rows/release"))?.body).toEqual({ ids: ["h1"], reason: null });
  registerCovered(REGISTRY, "release-held-rows-by-keyboard");
  const second = page.getByRole("region", { name: "Held from load L2" });
  await second.getByLabel("Reason for load L2").fill("Duplicate export");
  await press(page, second.getByRole("button", { name: "Reject" }));
  await expect(page.getByText(/Rejected 1 row/)).toBeVisible();
  expect(state.held).toEqual([]);
  registerCovered(REGISTRY, "reject-held-rows-by-keyboard");
});

test("the rule audit pages, by keyboard", async ({ page }) => {
  await serve(page);
  await page.goto("/keyboard/alerts-harness.html");
  await press(page, page.getByRole("tab", { name: "Changes" }));
  await expect(page.getByText("Showing 50 of 60 entries.")).toBeVisible();
  await press(page, page.getByRole("button", { name: "Show more" }));
  await expect(page.getByText("Showing 60 of 60 entries.")).toBeVisible();
  registerCovered(REGISTRY, "page-the-rule-audit-by-keyboard");
});

test("an Editor is offered triage but neither deployment nor the audit", async ({ page }) => {
  await serve(page, "editor");
  await page.goto("/keyboard/alerts-harness.html");
  await expect(page.getByRole("tab", { name: "Held rows" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Changes" })).toHaveCount(0);
  await press(page, page.getByRole("tab", { name: "What raises alerts" }));
  await expect(page.getByText("A case Author deploys and retires rules.")).toBeVisible();
});

// ADR-133 stage (b): a rule written as a sentence, blank by blank, its drawn pattern shown, previewed
// on the last 90 days and deployed — each step proven at the server it reached.
async function writeTheSentence(page: Page) {
  // Every blank by keys alone (rule 13; the lane-reviewer's round on the L2.10 fix): each select by
  // typing its option's label, the count typed over the field's own.
  await press(page, page.getByRole("tab", { name: "What raises alerts" }));
  await chooseByTyping(page, page.getByRole("combobox", { name: "Subject" }), "Person");
  await press(page, page.getByRole("button", { name: "Add a condition" }));
  await chooseByTyping(page, page.getByRole("combobox", { name: "Condition 1: property" }), "listing");
  await chooseByTyping(page, page.getByRole("combobox", { name: "Condition 1: test" }), "one_of");
  for (const value of ["sanction", "pep"]) {
    await page.getByRole("checkbox", { name: `Condition 1: ${value}` }).focus();
    await page.keyboard.press("Space");
  }
  await chooseByTyping(page, page.getByRole("combobox", { name: "Frequency" }), "count");
  await page.getByLabel("Times or more").focus();
  await page.keyboard.press("ControlOrMeta+A");
  await page.keyboard.type("3");
  await expect(page.getByLabel("Times or more")).toHaveValue("3");
  await chooseByTyping(page, page.getByRole("combobox", { name: "Severity" }), "high");
}

const WRITTEN = {
  subject: "Person",
  conditions: [{ op: "one_of", property: "listing", values: ["sanction", "pep"] }],
  relationship: null,
  frequency: { kind: "count", link_type: "PRESENT_AT", at_least: 3, within_days: 7 },
  severity: "high", team: "case", runs: "post_commit", on_hit: "load", scope: "this_case",
};  // prettier-ignore

test("a rule is written as a sentence, shown as its drawn pattern and deployed, by keyboard", async ({ page }) => {
  const state = await serve(page);
  await page.goto("/keyboard/alerts-harness.html");
  await writeTheSentence(page);
  await press(page, page.getByRole("button", { name: "Show the drawn pattern" }));
  await expect(page.getByRole("region", { name: "The drawn pattern" })).toContainText("When a Person whose listing is one of sanction, pep");
  expect(state.sent.find((s) => s.path === "rules/sentence/compile")?.body).toEqual(WRITTEN);
  await page.getByLabel("Name of the sentence rule").focus();
  await page.keyboard.type("Listed people seen often");
  await press(page, page.getByRole("button", { name: "Deploy the sentence" }));
  await expect(page.getByText("Deployed “Listed people seen often”.")).toBeVisible();
  expect(state.sent.find((s) => s.path === "rules/sentence")?.body).toEqual({ name: "Listed people seen often", sentence: WRITTEN });
  await expect(page.getByText(/When a Person whose listing is one of sanction, pep, 3 or more times by PRESENT_AT/)).toBeVisible();
  registerCovered(REGISTRY, "build-a-rule-as-a-sentence-by-keyboard");
});

test("a rule is written on a dataset, saved as a draft, tested and made live, by keyboard (ADR-146 decision 3)", async ({ page }) => {
  const state = await serve(page);
  const draft = {
    id: "r-new", investigation_id: "inv-1", owner_id: "analyst-1", name: "Listed people on the prison records",
    status: "draft", created_at: "2026-11-10T09:00:00Z", trigger: "post_commit", budget_ms: 5000, dataset_id: "ds-prison",
    params: { typology: "sentence", pattern_id: "p", sentence: WRITTEN },
  };  // prettier-ignore
  const fulfil = (body: unknown, status = 200) => ({ status, contentType: "application/json", body: JSON.stringify(body) });
  const record = (path: string) => (route: import("@playwright/test").Route) => {
    state.sent.push({ method: "POST", path, body: route.request().postDataJSON() });
  };
  await page.route("**/*/v1/investigations/inv-1/rules/datasets", (route) =>
    route.fulfill(fulfil([{ id: "ds-prison", name: "Prison records", kind: "source", second_person: false, ontology: ONTOLOGY, lists: [] }])),
  );
  await page.route("**/*/v1/investigations/inv-1/rules/drafts", (route) => {
    record("rules/drafts")(route);
    return route.fulfill(fulfil(draft, 201));
  });
  await page.route("**/*/v1/investigations/inv-1/rules/r-new/test", (route) => {
    record("rules/r-new/test")(route);
    return route.fulfill(fulfil({ rule_id: "r-new", version: 1, days: 30, would_raise: 2, words: "" }));
  });
  await page.route("**/*/v1/investigations/inv-1/rules/r-new/make-live", (route) => {
    record("rules/r-new/make-live")(route);
    return route.fulfill(fulfil({ ...draft, status: "active" }));
  });
  await page.goto("/keyboard/alerts-harness.html");
  await press(page, page.getByRole("tab", { name: "What raises alerts" }));
  await chooseByTyping(page, page.getByRole("combobox", { name: "The dataset this rule watches" }), "ds-prison");
  await press(page, page.getByRole("button", { name: "Choose the dataset" }));
  registerCovered(REGISTRY, "choose-a-rules-dataset-by-keyboard");
  const form = page.getByRole("form", { name: "Write a rule on Prison records" });
  await chooseByTyping(page, form.getByRole("combobox", { name: "Subject" }), "Person");
  await expect(form.getByRole("status", { name: "Where its alerts go" })).toHaveText("Its alerts will appear in Alerts, seen by this case's team.");
  await form.getByLabel("Name of the rule").focus();
  await page.keyboard.type("Listed people on the prison records");
  await press(page, form.getByRole("button", { name: "Save the draft" }));
  await expect.poll(() => (state.sent.find((s) => s.path === "rules/drafts")?.body as { dataset_id?: string } | undefined)?.dataset_id).toBe("ds-prison");
  registerCovered(REGISTRY, "save-a-rule-draft-by-keyboard");
  const live = page.getByRole("button", { name: "Make live" });
  await expect(live).toBeDisabled();
  await press(page, page.getByRole("button", { name: "Test on the last 30 days" }));
  await expect(page.getByRole("status", { name: "Test result" })).toContainText("It would have raised 2 alerts in the last 30 days.");
  registerCovered(REGISTRY, "test-a-rule-draft-by-keyboard");
  await press(page, live);
  await expect(page.getByText("“Listed people on the prison records” is live.")).toBeVisible();
  expect(state.sent.some((s) => s.path === "rules/r-new/make-live")).toBe(true);
  registerCovered(REGISTRY, "make-a-rule-live-by-keyboard");
});

test("a sentence's alerts are sent to a named team, by keyboard (ADR-146 decision 8)", async ({ page }) => {
  const state = await serve(page);
  await page.route("**/*/v1/investigations/inv-1/alert-teams", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([{ role_id: "team-7", display_name: "Prison intel", lead: false, members: [] }]) }),
  );
  await page.goto("/keyboard/alerts-harness.html");
  await writeTheSentence(page);
  await chooseByTyping(page, page.getByRole("combobox", { name: "Alert goes to (team)" }), "team:team-7");
  await page.getByLabel("Name of the sentence rule").focus();
  await page.keyboard.type("Listed people for the team");
  await press(page, page.getByRole("button", { name: "Deploy the sentence" }));
  await expect.poll(() => (state.sent.find((s) => s.path === "rules/sentence")?.body as { sentence?: Record<string, unknown> } | undefined)?.sentence).toMatchObject({
    team: "team",
    team_id: "team-7",
  });
  registerCovered(REGISTRY, "send-a-rules-alerts-to-a-named-team-by-keyboard");
});

test("a sentence is previewed on the last 90 days, by keyboard, and nothing is deployed", async ({ page }) => {
  const state = await serve(page);
  await page.goto("/keyboard/alerts-harness.html");
  await writeTheSentence(page);
  await press(page, page.getByRole("button", { name: "Preview on the last 90 days" }));
  const preview = page.getByRole("region", { name: "Preview" });
  await expect(preview.getByRole("status")).toHaveText("It would have raised 2 alerts in the last 90 days.");
  await expect(preview.getByRole("listitem")).toHaveText(["Callum Okafor (Person)", "Dana Okafor (Person)"]);
  expect(state.sent.find((s) => s.path === "rules/preview")?.body).toEqual({ sentence: WRITTEN });
  expect(state.sent.map((s) => s.path)).not.toContain("rules/sentence");
  registerCovered(REGISTRY, "preview-a-rule-by-keyboard");
});

test("an AML template is deployed with its jurisdiction list, by keyboard (ADR-133 stage c)", async ({ page }) => {
  const state = await serve(page);
  await page.goto("/keyboard/alerts-harness.html");
  await press(page, page.getByRole("tab", { name: "What raises alerts" }));
  await press(page, page.getByRole("button", { name: "Use the template: High-risk jurisdiction" }));
  await expect(page.getByLabel("Rule name")).toBeFocused();
  await page.getByRole("textbox", { name: "High-risk jurisdictions" }).focus();
  await page.keyboard.type("xa, xb");
  await press(page, page.getByRole("button", { name: "Deploy", exact: true }));
  await expect(page.getByText("Deployed “High-risk jurisdiction”.")).toBeVisible();
  expect(state.sent.find((s) => s.path === "rules")?.body).toEqual({
    name: "High-risk jurisdiction",
    params: { typology: "high_risk_jurisdiction", jurisdictions: ["XA", "XB"] },
    trigger: "post_commit",
    budget_ms: 5000,
  });
  registerCovered(REGISTRY, "deploy-an-aml-template-by-keyboard");
});

test("the screening lists are read by keyboard, with no action offered to a reader (ADR-133 stage c)", async ({ page }) => {
  await serve(page);
  await page.goto("/keyboard/alerts-harness.html");
  await press(page, page.getByRole("tab", { name: "What raises alerts" }));
  const table = page.getByRole("table", { name: "Screening lists and their versions" });
  await expect(table).toContainText("Synthetic list");
  await expect(table).toContainText("Up to date with its last refresh.");
  await expect(page.getByRole("button", { name: /Refresh now/ })).toHaveCount(0);
  registerCovered(REGISTRY, "read-the-screening-lists-by-keyboard");
});

test("a screening list is refreshed and another subscribed to, by keyboard (ADR-133 stage c)", async ({ page }) => {
  const state = await serve(page);
  await page.goto("/keyboard/alerts-harness.html?lists=manage");
  await press(page, page.getByRole("tab", { name: "What raises alerts" }));
  await press(page, page.getByRole("button", { name: "Refresh now: Synthetic list" }));
  await expect(page.getByRole("status")).toContainText("1 alert raised");
  expect(state.sent.some((s) => s.path === "/v1/admin/screening-lists/Synthetic%20list/refresh")).toBe(true);
  registerCovered(REGISTRY, "refresh-a-screening-list-by-keyboard");
  const form = page.getByRole("form", { name: "Subscribe to a list" });
  await form.getByLabel("List name").focus();
  await page.keyboard.type("UN list");
  await form.getByRole("combobox", { name: "Connector" }).selectOption("un_consolidated");
  await form.getByLabel("File in the ingest folder").focus();
  await page.keyboard.type("lists/consolidated.xml");
  await press(page, form.getByRole("button", { name: "Subscribe" }));
  await expect(page.getByRole("status")).toContainText("Subscribed to “UN list”");
  expect(state.sent.find((s) => s.path === "/v1/admin/screening-lists")?.body).toEqual({
    list_name: "UN list", source: "un_consolidated", location: "lists/consolidated.xml", dataset: null, use: "local_development",
  });  // prettier-ignore
  registerCovered(REGISTRY, "subscribe-to-a-screening-list-by-keyboard");
});

test("every registered Alerts action has its own proving test case above", () => {
  assertAllCovered("ALERTS_ACTIONS", ALERTS_ACTIONS);
});
