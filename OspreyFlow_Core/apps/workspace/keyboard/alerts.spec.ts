// A keyboard-only walkthrough of the Alerts place (ADR-109 phase B, `CLAUDE.md` rule 13): open an
// alert from the queue, claim and release it, show it on the canvas, close it with a reason, filter
// the queue; deploy and retire a rule; release and reject held rows; page the rule audit — no
// `page.mouse`, no `.click()`. Each action proves its effect reached the server (or the canvas
// callback), not merely that a control received focus.
import { expect, test, type Locator, type Page } from "@playwright/test";

import { ALERTS_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

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

async function press(page: Page, target: Locator) {
  await target.focus();
  await page.keyboard.press("Enter");
}

async function openTheAlert(page: Page) {
  await press(page, page.getByRole("button", { name: /Open alert: Structuring/ }));
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
  await page.getByLabel("Reason for closing").fill("Matches the SAR");
  await press(page, page.getByRole("button", { name: "Close as true positive" }));
  await expect(page.getByText(/Closed as a true positive/)).toBeVisible();
  expect(state.sent.find((s) => s.path === "alert-queue/a1/disposition")?.body).toEqual({
    disposition: "true_positive",
    reason: "Matches the SAR",
  });
  registerCovered(REGISTRY, "close-an-alert-with-a-reason-by-keyboard");
});

test("the queue is filtered, by keyboard", async ({ page }) => {
  const state = await serve(page);
  await page.goto("/keyboard/alerts-harness.html");
  await page.getByRole("combobox", { name: "Which alerts" }).selectOption("closed");
  await expect.poll(() => state.queueFilters).toContain("closed");
  registerCovered(REGISTRY, "filter-the-queue-by-keyboard");
});

test("a rule is deployed and another retired, by keyboard", async ({ page }) => {
  const state = await serve(page);
  await page.goto("/keyboard/alerts-harness.html");
  await press(page, page.getByRole("tab", { name: "Rules" }));
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
  await press(page, page.getByRole("tab", { name: "Rules" }));
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
  await press(page, page.getByRole("tab", { name: "Rules" }));
  await page.getByLabel("Rule name").fill("Drawn: company with a phone");
  await page.getByRole("combobox", { name: "Typology" }).selectOption("pattern");
  await page.getByRole("combobox", { name: "Saved pattern" }).selectOption("pat-1");
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
  await press(page, page.getByRole("tab", { name: "Audit" }));
  await expect(page.getByText("Showing 50 of 60 entries.")).toBeVisible();
  await press(page, page.getByRole("button", { name: "Show more" }));
  await expect(page.getByText("Showing 60 of 60 entries.")).toBeVisible();
  registerCovered(REGISTRY, "page-the-rule-audit-by-keyboard");
});

test("an Editor is offered triage but neither deployment nor the audit", async ({ page }) => {
  await serve(page, "editor");
  await page.goto("/keyboard/alerts-harness.html");
  await expect(page.getByRole("tab", { name: "Held rows" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Audit" })).toHaveCount(0);
  await press(page, page.getByRole("tab", { name: "Rules" }));
  await expect(page.getByText("A case Author deploys and retires rules.")).toBeVisible();
});

test("every registered Alerts action has its own proving test case above", () => {
  assertAllCovered("ALERTS_ACTIONS", ALERTS_ACTIONS);
});
