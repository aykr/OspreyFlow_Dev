// A keyboard-only walkthrough of ADR-133 stage (d) in the Monitoring place (`CLAUDE.md` rule 13): a
// sentence set to run on a schedule and deployed; a scheduled rule's schedule and runs read; a
// whole-deployment rule approved by a second administrator-author and another's change rejected; a
// rule's versions read; a high-severity alert's close proposed, approved by a second member, and
// another sent back; a screening list's refresh schedule set — no `page.mouse`, no `.click()`. Each
// action proves its effect reached the server. The data is synthetic (rule 9).
import { expect, test, type Locator, type Page } from "@playwright/test";

import { MONITORING_STAGE_D_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

const REGISTRY = "MONITORING_STAGE_D_ACTIONS";

const SENTENCE = { subject: "Person", conditions: [], severity: "high", team: "case", on_hit: "load" };

function rule(id: string, name: string, extra: Record<string, unknown> = {}) {
  return {
    id, investigation_id: "inv-1", owner_id: "maker", name, created_at: "2026-11-01T09:00:00Z", trigger: "post_commit",
    budget_ms: 5000, status: "active", version: 1,
    params: { typology: "sentence", pattern_id: "p1", sentence: { ...SENTENCE, runs: "post_commit", scope: "deployment" } },
    ...extra,
  };  // prettier-ignore
}

const RULES = () => [
  rule("r-wide", "Sanctioned people everywhere", { status: "pending", pending_action: "deploy", pending_by: "maker", pending_version: 1 }),
  rule("r-change", "PEPs everywhere", { pending_action: "change", pending_by: "maker", pending_version: 2 }),
  rule("r-daily", "Daily listed people", { trigger: "schedule", params: { typology: "sentence", pattern_id: "p2",
    sentence: { ...SENTENCE, runs: "schedule", scope: "this_case", schedule: { every: "daily", hour: 6 } } } }),
];  // prettier-ignore

function alertOf(id: string, status: string, extra: Record<string, unknown> = {}) {
  return {
    id, rule_id: "typology:r9", owner_id: "deployer", mode: "full", referent_node_ids: [], investigation_id: "inv-1",
    created_at: "2026-11-01T09:00:00Z", typology: "large_cash", words: "cash paid in of £12,000", severity: "high",
    status, assignee: "member-1", ...extra,
  };  // prettier-ignore
}

const LISTS = [
  { list_name: "Synthetic list", source: "opensanctions", location: "lists/synthetic_opensanctions_v1.ftm.json", dataset: null,
    synthetic: true, licence: "CC BY-NC 4.0", version: "v1", entries: 10, updated_at: "2026-11-01T08:00:00Z",
    attempted_at: "2026-11-01T08:00:00Z", failure: null },
];  // prettier-ignore

const ONTOLOGY = {
  version: 1,
  entity_types: [{ name: "Person", pole_class: "person", channel: "indigo", shape: "circle", identifiers: [], properties: [
    { name: "listing", type: "enum", values: ["sanction", "pep"] }] }],
  edge_types: [],
};  // prettier-ignore

interface Sent {
  method: string;
  path: string;
  body: unknown;
}

async function serve(page: Page, alerts: Record<string, unknown>[] = []): Promise<Sent[]> {
  const sent: Sent[] = [];
  let rules = RULES();
  await page.route("**/*/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace("/v1/investigations/inv-1/", "");
    const method = request.method();
    const json = (status: number, body: unknown) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    const body = method === "GET" ? undefined : request.postDataJSON();
    if (method !== "GET") sent.push({ method, path: url.pathname.startsWith("/v1/admin") ? url.pathname : path, body });
    if (url.pathname === "/v1/investigations")
      return json(200, [{ id: "inv-1", name: "Ledger", level: "author", created_at: "", created_by: "" }]);
    if (url.pathname === "/v1/ontology") return json(200, ONTOLOGY);
    if (path === "patterns") return json(200, { patterns: [] });
    if (path === "rules" && method === "GET") return json(200, rules);
    if (path === "rules/r-wide/approve") {
      rules = rules.map((r) => (r.id === "r-wide" ? { ...r, status: "active", pending_action: undefined } : r));
      return json(200, rules[0]);
    }
    if (path === "rules/r-change/reject") {
      rules = rules.map((r) => (r.id === "r-change" ? { ...r, pending_action: undefined } : r));
      return json(200, rules[1]);
    }
    if (path === "rules/r-daily/versions")
      return json(200, [{ rule_id: "r-daily", version: 1, action: "deploy", name: "Daily listed people", params: {}, trigger: "schedule",
        budget_ms: 5000, proposed_by: "maker", proposed_by_name: "Mo Maker", proposed_at: "2026-11-01T09:00:00Z", status: "applied",
        decided_by: "maker", decided_at: "2026-11-01T09:00:00Z" }]);  // prettier-ignore
    if (path === "rules/r-daily/runs")
      return json(200, { rule_id: "r-daily", schedule: "every day at 06:00 (Europe/London)", state: "scheduled", words: null,
        next_run: "2026-11-02T06:00:00Z", runs: [{ id: "x1", rule_id: "r-daily", rule_version: 1, slot: "2026-11-01T06:00:00Z",
        ran_at: "2026-11-01T06:00:04Z", run_as: "maker", outcome: "ran", alerts: 2, words: "Ran as maker over the last day: 2 alert(s) raised." }] });  // prettier-ignore
    if (path === "rules/sentence" && method === "POST")
      return json(201, rule("r-new", (body as { name: string }).name, { params: { typology: "sentence", pattern_id: "p9",
        sentence: (body as { sentence: unknown }).sentence } }));  // prettier-ignore
    if (path === "alert-queue")
      return json(200, alerts.map((a) => ({ alert: a, summary: "Cash paid in of £12,000", kind: "typology", severity: "high", audience: "case" })));
    const one = alerts.find((a) => path.startsWith(`alert-queue/${String(a.id)}`));
    if (one && path === `alert-queue/${String(one.id)}`)
      return json(200, { alert: one, summary: "Cash paid in of £12,000", nodes: [], edges: [], transactions: [], kind: "typology",
        severity: "high", audience: "case" });  // prettier-ignore
    if (one && path.endsWith("/disposition")) return json(200, { ...one, status: "closing", close_proposed_by: "analyst-1" });
    if (one && path.endsWith("/approve-close")) return json(200, { ...one, status: "closed" });
    if (one && path.endsWith("/send-back")) return json(200, { ...one, status: "claimed", close_proposed_by: null });
    if (path === "alert-assignees") return json(200, []);
    if (url.pathname === "/v1/admin/screening-lists" && method === "GET") return json(200, { lists: LISTS, updates: [], can_manage: true });
    if (url.pathname === "/v1/admin/screening-lists/Synthetic%20list/schedule")
      return json(200, { ...LISTS[0], schedule: (body as { schedule: unknown }).schedule, schedule_words: "every Monday at 05:00 (Europe/London)" });
    return json(404, {});
  });
  return sent;
}

async function press(page: Page, target: Locator) {
  await target.focus();
  await page.keyboard.press("Enter");
}

async function rulesTab(page: Page, query = "") {
  await page.goto(`/keyboard/alerts-harness.html${query}`);
  await press(page, page.getByRole("tab", { name: "Rules" }));
}

test("a sentence is set to run every week on a day at an hour, and deployed, by keyboard", async ({ page }) => {
  const sent = await serve(page);
  await rulesTab(page);
  // The builder offers its blanks once the ontology has been read.
  const form = page.getByRole("form", { name: "Write a rule as a sentence" });
  await expect(form.getByRole("combobox", { name: "Subject" })).toHaveValue("Person");
  await form.getByRole("combobox", { name: "Runs" }).selectOption("schedule");
  await form.getByRole("combobox", { name: "Every" }).selectOption("weekly");
  await form.getByRole("combobox", { name: "Day of the week" }).selectOption("3");
  await form.getByRole("combobox", { name: "Hour" }).selectOption("8");
  await form.getByLabel("Name of the sentence rule").focus();
  await page.keyboard.type("Weekly listed people");
  await press(page, page.getByRole("button", { name: "Deploy the sentence" }));
  await expect.poll(() => sent.find((s) => s.path === "rules/sentence")).toBeTruthy();
  const body = sent.find((s) => s.path === "rules/sentence")!.body as { sentence: { runs: string; schedule: unknown } };
  expect(body.sentence.runs).toBe("schedule");
  expect(body.sentence.schedule).toEqual({ every: "weekly", hour: 8, weekday: 3 });
  registerCovered(REGISTRY, "schedule-a-rule-by-keyboard");
});

test("a scheduled rule's schedule and runs are read, by keyboard", async ({ page }) => {
  await serve(page);
  await rulesTab(page);
  await press(page, page.getByRole("button", { name: "Schedule and runs of Daily listed people" }));
  const group = page.getByRole("group", { name: "The schedule of Daily listed people" });
  await expect(group).toContainText("Runs every day at 06:00 (Europe/London)");
  await expect(group).toContainText("Ran as maker over the last day: 2 alert(s) raised.");
  registerCovered(REGISTRY, "read-a-rules-schedule-and-runs-by-keyboard");
});

test("a second administrator-author approves one rule and rejects another's change, by keyboard", async ({ page }) => {
  const sent = await serve(page);
  await rulesTab(page, "?admin=1&account=checker");
  await expect(page.getByText(/deploying it, proposed by maker/)).toBeVisible();
  await press(page, page.getByRole("button", { name: "Approve Sanctioned people everywhere" }));
  await expect(page.getByRole("status")).toContainText("Approved the change to “Sanctioned people everywhere”.");
  expect(sent.some((s) => s.path === "rules/r-wide/approve")).toBe(true);
  registerCovered(REGISTRY, "approve-a-whole-deployment-rule-by-keyboard");
  await press(page, page.getByRole("button", { name: "Reject PEPs everywhere" }));
  await page.getByLabel("Why reject the change to PEPs everywhere").focus();
  await page.keyboard.type("too wide for every case");
  await press(page, page.getByRole("button", { name: "Send the rejection of PEPs everywhere" }));
  await expect.poll(() => sent.find((s) => s.path === "rules/r-change/reject")?.body).toEqual({ reason: "too wide for every case" });
  registerCovered(REGISTRY, "reject-a-whole-deployment-rule-change-by-keyboard");
});

test("the person who proposed a change is offered no Approve", async ({ page }) => {
  await serve(page);
  await rulesTab(page, "?admin=1&account=maker");
  await expect(page.getByText(/deploying it, proposed by maker/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve Sanctioned people everywhere" })).toHaveCount(0);
});

test("a rule's versions are read, by keyboard", async ({ page }) => {
  await serve(page);
  await rulesTab(page);
  await press(page, page.getByRole("button", { name: "Versions of Daily listed people" }));
  await expect(page.getByRole("list", { name: "Versions of Daily listed people" })).toContainText("Version 1: deployed by Mo Maker");
  registerCovered(REGISTRY, "read-a-rules-versions-by-keyboard");
});

async function openTheAlert(page: Page) {
  await press(page, page.getByRole("button", { name: /Open alert: High severity/ }));
  await expect(page.getByRole("region", { name: "What fired this alert" })).toBeVisible();
}

test("closing a high-severity alert is proposed, by keyboard", async ({ page }) => {
  const sent = await serve(page, [alertOf("h1", "claimed", { assignee: "analyst-1" })]);
  await page.goto("/keyboard/alerts-harness.html");
  await openTheAlert(page);
  await expect(page.getByText(/closing it here proposes the close/)).toBeVisible();
  await page.getByLabel("Reason for closing").focus();
  await page.keyboard.type("a known payroll deposit");
  await press(page, page.getByRole("button", { name: "Close as false positive" }));
  await expect(page.getByRole("status")).toContainText("Close proposed as a false positive");
  expect(sent.find((s) => s.path === "alert-queue/h1/disposition")?.body).toEqual({
    disposition: "false_positive", reason: "a known payroll deposit" });  // prettier-ignore
  registerCovered(REGISTRY, "propose-closing-a-high-severity-alert-by-keyboard");
});

test("a second member approves a proposed close, and another is sent back, by keyboard", async ({ page }) => {
  const closing = { status: "closing", disposition: "false_positive", disposition_reason: "known", close_proposed_by: "member-1" };
  const sent = await serve(page, [alertOf("h1", "closing", closing)]);
  await page.goto("/keyboard/alerts-harness.html?account=second-member");
  await openTheAlert(page);
  await press(page, page.getByRole("button", { name: "Approve the close" }));
  await expect(page.getByRole("status")).toContainText("Approved: the alert is closed.");
  expect(sent.some((s) => s.path === "alert-queue/h1/approve-close")).toBe(true);
  registerCovered(REGISTRY, "approve-closing-a-high-severity-alert-by-keyboard");
  await page.getByLabel("Reason for sending the close back").focus();
  await page.keyboard.type("check the second deposit first");
  await press(page, page.getByRole("button", { name: "Send back" }));
  await expect.poll(() => sent.find((s) => s.path === "alert-queue/h1/send-back")?.body).toEqual({
    reason: "check the second deposit first" });  // prettier-ignore
  registerCovered(REGISTRY, "send-back-a-proposed-close-by-keyboard");
});

test("a screening list's refresh schedule is set, by keyboard", async ({ page }) => {
  const sent = await serve(page);
  await page.goto("/keyboard/alerts-harness.html?lists=manage");
  await press(page, page.getByRole("tab", { name: "Lists" }));
  await page.getByRole("combobox", { name: "Refreshed" }).selectOption("weekly");
  await page.getByRole("combobox", { name: "Refresh day" }).selectOption("1");
  await press(page, page.getByRole("button", { name: "Save the schedule" }));
  await expect(page.getByRole("status")).toContainText("is refreshed every Monday at 05:00 (Europe/London), as you.");
  expect(sent.find((s) => s.method === "PUT")?.body).toEqual({ schedule: { every: "weekly", hour: 5, weekday: 1 } });
  registerCovered(REGISTRY, "set-a-list-refresh-schedule-by-keyboard");
});

test("every registered stage (d) Monitoring action has its own proving test case above", () => {
  assertAllCovered("MONITORING_STAGE_D_ACTIONS", MONITORING_STAGE_D_ACTIONS);
});
