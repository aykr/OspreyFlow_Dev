// A keyboard-only walkthrough of the Admin area (ADR-110 Amendment 1, ADR-112, `CLAUDE.md` rule 13):
// save a person's roles, register and remove a dashboard, ask the system again — no `page.mouse`, no
// `.click()`; each proves its call reached the server.
import { expect, test, type Page } from "@playwright/test";

import { ADMIN_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

const REGISTRY = "ADMIN_ACTIONS";
const PERSON = { id: "u1", username: "osprey-demo-analyst", name: "Demo Analyst", enabled: true, roles: ["analyst"],
                 clearance: "OFFICIAL", org_unit: "verify" };  // prettier-ignore

// ADR-110 decision 8: one scheduled recipe, last run succeeded.
const SCHEDULE = {
  recipe_id: "feed", label: "Daily custody export", case_id: "case-1", cron: "0 6 * * 1-5", timezone: "Europe/London",
  schedule: "every weekday at 06:00 (Europe/London)", owner: "approver-1", next_run: "2026-06-03T05:00:00Z",
  paused: false, paused_reason: null, flagged: false,
  last_run: { run_id: "r1", trigger: "schedule", slot: "2026-06-02T05:00:00Z", started_at: "2026-06-02T05:00:01Z",
              finished_at: "2026-06-02T05:00:09Z", outcome: "succeeded", run_as: "approver-1", withheld: false,
              rows_read: 40, nodes_created: 12, nodes_referenced: 3, edges_created: 20, rows_rejected: 1, rows_held: 0,
              load_id: "l1", failure: null },
};  // prettier-ignore

// L2.4 part 2: a dataset with its Authors and linked cases, two of them removed. Synthetic (rule 9).
const DATASET = { id: "enron", name: "Enron corpus", owning_unit: "verify", egress: "none", kind: "source",
                  highest_marking: null, promotion_policy: "author_promotes" };  // prettier-ignore
const AUTHORS = { dataset_id: "enron", has_home_case: true, team: null,
                  people: [{ id: "eng-1", name: "D. Engineer", approves: true }] };  // prettier-ignore
const LINKED = { dataset_id: "enron", cases: [
  { investigation_id: "open-1", name: "Op Kestrel", state: "open", home_case: false, through: null, items: 3, links: 2, size_bytes: 700 },
  { investigation_id: "gone-1", name: "Op Heron", state: "removed", home_case: false, through: null, items: 5, links: 4, size_bytes: 50000 },
  { investigation_id: "gone-2", name: "Op Wren", state: "removed", home_case: false, through: null, items: 1, links: 0, size_bytes: 90 },
] };  // prettier-ignore

// L2.5: the roles (one custom role made a team), the rows (a case with no Author) and a disable plan.
const TEAM = { role_id: "r1", display_name: "Intel", mailbox: "intel@example.org", lead: "u1", cover: null,
               cover_until: null, acting_lead: "u1", members: [{ id: "u1", name: "Demo Analyst" }, { id: "u3", name: "Bea Engineer" }] };  // prettier-ignore
const CATALOGUE = {
  built_in: [
    { id: "analyst", label: "Analyst", rights: ["investigate", "triage_alerts"], gives: [] },
    { id: "data_engineer", label: "Data Engineer", rights: ["edit_pipelines", "review_promotions"], gives: [] },
    { id: "super_user", label: "Super user", rights: ["investigate", "edit_pipelines"], gives: ["analyst", "data_engineer", "rule_author"] },
  ],
  custom: [{ id: "r1", name: "Intel desk", version: 1, rights: ["investigate"], changed_by: "a", changed_at: "", holders: 1, team: TEAM }],
};  // prettier-ignore
const ROWS = { rows: [{ id: "u1", levels: [{ investigation_id: "c1", name: "Op Kestrel", level: "author", through: null }] }],
               without_author: [{ investigation_id: "c3", name: "Op Wren" }] };  // prettier-ignore
// L2.5b: L3.8's kinds are in the plan beside the case, each with its own *Transfer to…*.
const PLAN = { person: "u1", not_yet_listed: ["promotions waiting for review", "reviews waiting on them"],
               items: [{ kind: "case_author", id: "c1", label: "Only Author of the case Op Kestrel" },
                       { kind: "drawn_watch", id: "w1", investigation_id: "c1",
                         label: "A watch on an item they drew in the case Op Kestrel" }] };  // prettier-ignore
const COLLEAGUE = { ...PERSON, id: "u3", username: "bea", name: "Bea Engineer", roles: ["data_engineer"] };

// L2.6: an audit page of the stream (one entry's words withheld), a rule audit, and Operations' ageing.
const AUDIT_ENTRY = { recorded_at: "2026-11-08T09:00:00Z", who: "Demo Analyst",
                      action: "confirm_node", kind: "assertions", held_in: "case_and_admin", investigation_id: "c1",
                      case_name: "Op Kestrel", detail: null, words_withheld: true, result_cardinality: null };  // prettier-ignore
const AGEING = { alert_after_days: 3, promotions_recorded: false, waiting: [],
                 rules: [{ what: "A promotion waiting for review", after_days: 3, then: "After 3 days it is flagged overdue." }] };  // prettier-ignore

async function serve(page: Page, opts: { owns?: boolean } = {}): Promise<string[]> {
  const asked: string[] = [];
  let dashboards = [{ client_id: "osprey-dashboard-old", account_id: "sa-0", clearance: "OFFICIAL", org_unit: "verify" }];
  await page.route("**/*/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace("/v1/admin/", "");
    asked.push(`${request.method()} ${path}`);
    const json = (status: number, body: unknown) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (path === "audit" || path === "audit/rules") {
      const q = new URL(request.url()).searchParams;
      asked.push(`AUDIT ${path} ${q.toString()}`);
      const offset = Number(q.get("offset") ?? 0);
      const rules = path === "audit/rules";
      const entry = rules ? { ...AUDIT_ENTRY, action: "rule_deployed", kind: "rules", held_in: "rules",
                              detail: { rule_id: "r1" }, words_withheld: false, result_cardinality: 1 } : AUDIT_ENTRY;  // prettier-ignore
      return json(200, { entries: [entry], total: rules ? 1 : 120, offset, limit: 50, note: null,
                         people: ["Demo Analyst", "Zed Reviewer"] });  // prettier-ignore
    }
    if (path === "operations/ageing") return json(200, AGEING);
    if (path === "settings/promotion-alert-days" && request.method() === "PUT") return json(200, request.postDataJSON());
    if (path === "people" && request.method() === "POST") {
      const sent = request.postDataJSON() as { username: string };
      return json(201, { person: { ...PERSON, id: "u2", username: sent.username, name: sent.username, must_set_password: true },
                         delivery: "one_time_code", one_time_code: "ABCD-EFGH-JKLM-NPQR" });  // prettier-ignore
    }
    if (path === "people") return json(200, [PERSON, COLLEAGUE]);
    if (path === "people/rows") return json(200, ROWS);
    if (path === "people/u1/disable-plan") return json(200, opts.owns ? PLAN : { ...PLAN, items: [] });
    if (path === "roles" && request.method() === "POST") {
      const sent = request.postDataJSON() as { name: string; rights: string[] };
      return json(201, { id: "r2", version: 1, changed_by: "a", changed_at: "", holders: 0, team: null, ...sent });
    }
    if (path === "roles") return json(200, CATALOGUE);
    if (path === "roles/r1/versions")
      return json(200, [{ version: 1, name: "Intel desk", rights: ["investigate"], changed_by: "adm-1", changed_at: "2026-11-08T09:00:00Z" }]);
    if (path === "roles/r1" && request.method() === "PUT")
      return json(200, { ...CATALOGUE.custom[0], ...(request.postDataJSON() as object), version: 2 });
    if (path === "roles/r1/team" && request.method() === "PUT") return json(200, { ...TEAM, ...(request.postDataJSON() as object) });
    if (path === "teams/r1/lead" && request.method() === "PUT") return json(200, { ...TEAM, ...(request.postDataJSON() as object) });
    if (path === "teams/r1/cover" && request.method() === "PUT") {
      const sent = request.postDataJSON() as { cover: string; until: string };
      return json(200, { ...TEAM, cover: sent.cover, cover_until: sent.until });
    }
    if (path === "cases/c3/authors/u3" && request.method() === "PUT") return route.fulfill({ status: 204 });
    if (path === "organisation-arrivals")
      return json(200, [{ subject: "sub-1", provider_username: "pat.example", last_refused: "2026-11-05T09:30:00Z", attempts: 1 }]);
    if (path === "people/u1/organisation-link" && request.method() === "POST")
      return json(200, { ...PERSON, organisation_linked: true });
    if (path === "people/u1/access") return json(200, { ...PERSON, ...(request.postDataJSON() as object) });
    if (path === "people/u1/disable") return json(200, { ...PERSON, enabled: false });
    if (path === "people/u1/enable") return json(200, { ...PERSON, enabled: true });
    if (path === "people/u1" && request.method() === "DELETE") return json(200, PERSON);
    if (path === "people/u1/reset-sign-in")
      return json(200, { person: { ...PERSON, must_set_password: true }, delivery: "one_time_code", one_time_code: "WXYZ-WXYZ-WXYZ-WXYZ" });
    if (path === "people/u1/roles") return json(200, { ...PERSON, roles: (request.postDataJSON() as { roles: string[] }).roles });
    if (path === "dashboards" && request.method() === "POST") {
      const made = { client_id: "osprey-dashboard-board", account_id: "sa-1", clearance: "OFFICIAL", org_unit: "verify" };
      dashboards = [...dashboards, made];
      return json(201, { dashboard: made, secret: "s3cret" });
    }
    if (path === "dashboards") return json(200, dashboards);
    if (path.startsWith("dashboards/")) return route.fulfill({ status: 204 });
    if (path === "/v1/handling-scheme") return json(200, { classification: ["OFFICIAL", "SECRET"], handling_codes: { P: {}, C: {} } });
    if (path === "demo-packs")
      return json(200, [{ id: "hmp", title: "HMP — organised crime (synthetic)", shows: "A prison.", delivery: "seed",
                          licence: "Generated by OspreyFlow, owned outright", attribution: null,
                          case_name: "HMP fixture (synthetic demo)", loaded_case_id: null,
                          command: "ospreyflow demo add hmp", source_page: null, size_bytes: null }]);  // prettier-ignore
    if (path === "system") return json(200, { components: [{ name: "Graph store", ok: true, millis: 12 }] });
    // ADR-136 decision 2: the Datasets tab.
    if (path === "datasets") return json(200, [DATASET]);
    if (path === "datasets/enron/egress" && request.method() === "PUT")
      return json(200, { ...DATASET, ...(request.postDataJSON() as object) });
    // ADR-145 decision 8 and Amendment 4 decisions 6 and 7; ADR-143 Amendment 2 decisions 1 and 2.
    if (path === "datasets/enron/promotion-policy" && request.method() === "PUT")
      return json(200, { ...DATASET, ...(request.postDataJSON() as object) });
    if (path === "datasets/enron/authors") return json(200, AUTHORS);
    if (path === "datasets/enron/owners" && request.method() === "PUT") {
      const people = (request.postDataJSON() as { people: string[] }).people;
      return json(200, { ...AUTHORS, people: people.map((id) => ({ id, name: null, approves: false })) });
    }
    if (path === "datasets/enron/cases") return json(200, LINKED);
    if (path === "datasets/enron/cases/gone-1/merge/dry-run" && request.method() === "POST")
      return json(200, { investigation_id: "gone-1", action: "merge", items: 5, links: 4, size_bytes: 50000,
                         would: "Would merge 5 items and 4 links (48.8 kB) from Op Heron's layer into Enron corpus. Nothing has been written." });  // prettier-ignore
    if (path === "datasets/enron/cases/gone-1/delete/dry-run" && request.method() === "POST")
      return json(200, { investigation_id: "gone-1", action: "delete", items: 5, links: 4, size_bytes: 50000,
                         would: "Op Heron's layer holds 5 items and 4 links (48.8 kB). Deleting it withdraws those not promoted; promoted items are never touched. Nothing has been written." });  // prettier-ignore
    if (path === "datasets/enron/cases/gone-2/merge/dry-run" && request.method() === "POST")
      return json(403, { error: "not_an_author", right: "investigate",
                         detail: "Only one of the dataset's Authors may merge a removed case's layer into it, in the Ingest Studio's 4 Runs: an Author of its home case who holds Investigate." });  // prettier-ignore
    if (path === "datasets/enron/cases/gone-1/delete" && request.method() === "POST")
      return json(200, { investigation_id: "gone-1", words: "The layer was deleted: its items are withdrawn and kept in the audit. Promoted items were not touched." });
    if (path === "settings/dataset-owners" && request.method() === "PUT") return json(200, request.postDataJSON());
    if (path === "settings/dataset-owners") return json(200, { owners_may_be: "people_and_teams" });
    // L2.7: Policies' Grading scheme, read-only.
    if (path === "/v1/grading-scheme")
      return json(200, { scheme: "admiralty", source: ["A", "B", "C", "D", "E", "F"], intelligence: ["1", "2", "3", "4", "5", "6"], handling: ["P", "C"] });
    // ADR-140 Amendment 4: the Connections tab.
    if (path === "connections" && request.method() === "POST") {
      const sent = request.postDataJSON() as { kind: string; name: string };
      return json(201, { ...sent, id: "c2", created_by: "admin-1", created_at: "" });
    }
    // L2.7 (ADR-140 Amendment 13): an API connection, its Test connection answered in words.
    if (path === "connections/c-api/test" && request.method() === "POST")
      return json(200, { ok: true, words: "The host is allowed and the secret is set." });
    if (path === "connections") return json(200, [
      { id: "files", kind: "files", name: "Files: the ingest root", created_by: "system", created_at: "" },
      { id: "c-api", kind: "api", name: "Telco lookup (synthetic)", created_by: "admin-1", created_at: "", datasets: ["enron"],
        settings: { kind: "api", base_url: "https://telco.example", auth: "bearer", secret: "TELCO", pagination: "none" } },
    ]); // prettier-ignore
    if (path === "schedules") return json(200, [SCHEDULE]);
    if (path === "schedules/feed/pause") return json(200, { ...SCHEDULE, paused: true, paused_reason: "paused by admin-1" });
    if (path === "schedules/feed/resume") return json(200, SCHEDULE);
    if (path === "schedules/feed/run") return json(200, SCHEDULE);
    if (path === "schedules/feed" && request.method() === "PUT")
      return json(200, { ...SCHEDULE, cron: "30 7 * * 1-5", schedule: "every weekday at 07:30 (Europe/London)" });
    if (path === "/v1/ingest/schedule-preview")
      return json(200, { words: "every weekday at 07:30 (Europe/London)", next_runs: ["2026-06-08T06:30:00Z"] });
    if (path === "schedules/feed/runs")
      return json(200, [{ ...SCHEDULE.last_run, run_id: "r0", outcome: "missed", rows_read: null, failure: "the deployment was not running then" }]);
    return json(404, {});
  });
  return asked;
}

async function press(page: Page, name: string) {
  await page.getByRole("button", { name, exact: true }).focus();
  await page.keyboard.press("Enter");
}

/** A section in the Admin place's side list (ADR-145 decision 5). */
const section = (page: Page, name: string) =>
  page.getByRole("navigation", { name: "Admin sections" }).getByRole("button", { name, exact: true });

/** Opens a section from the side list by keyboard: focused, then Enter. */
async function open(page: Page, name: string) {
  await section(page, name).focus();
  await page.keyboard.press("Enter");
}

test("a person's roles are saved by keyboard", async ({ page }) => {
  const asked = await serve(page);
  await page.goto("/keyboard/admin-harness.html");
  await page.getByLabel("Data Engineer for osprey-demo-analyst").focus();
  await page.keyboard.press("Space");
  await press(page, "Save roles for osprey-demo-analyst");
  await expect(page.getByText("Saved.")).toBeVisible();
  expect(asked).toContain("PUT people/u1/roles");
  registerCovered(REGISTRY, "save-a-persons-roles-by-keyboard");
});

test("a dashboard is registered and removed by keyboard", async ({ page }) => {
  const asked = await serve(page);
  await page.goto("/keyboard/admin-harness.html?rights=manage_dashboards");
  await page.getByLabel("Dashboard name").fill("Board");
  await page.getByLabel("Dashboard unit").fill("verify");
  await press(page, "Register");
  await expect(page.getByText("s3cret")).toBeVisible();
  registerCovered(REGISTRY, "register-a-dashboard-by-keyboard");
  await press(page, "Remove osprey-dashboard-old");
  await expect.poll(() => asked).toContain("DELETE dashboards/osprey-dashboard-old");
  registerCovered(REGISTRY, "remove-a-dashboard-by-keyboard");
});

// ADR-136 decision 2 (rule 13): the Datasets tab is reached, a dataset's egress changed and saved, by
// keyboard alone; the PUT carries the setting chosen.
test("a dataset's egress is set by keyboard", async ({ page }) => {
  const asked = await serve(page);
  const sent: unknown[] = [];
  page.on("request", (request) => {
    if (request.method() === "PUT" && request.url().endsWith("/datasets/enron/egress")) sent.push(request.postDataJSON());
  });
  await page.goto("/keyboard/admin-harness.html?rights=administer_system");
  await open(page, "Datasets");
  const egress = page.getByLabel("Egress for Enron corpus", { exact: true });
  await egress.focus();
  // A closed select takes an arrow key differently by platform; typing an option's start chooses it.
  await page.keyboard.type("any");
  await expect(egress).toHaveValue("any");
  await press(page, "Save egress for Enron corpus");
  await expect(page.getByText("Enron corpus: egress is now any.")).toBeVisible();
  expect(asked).toContain("PUT datasets/enron/egress");
  expect(sent).toEqual([{ egress: "any" }]);
  registerCovered(REGISTRY, "set-a-datasets-egress-by-keyboard");
});

/** Opens Datasets and a dataset's details by keyboard; its linked cases are read. */
async function details(page: Page) {
  await open(page, "Datasets");
  await press(page, "Details for Enron corpus");
  await expect(page.getByRole("table", { name: "Cases linked to Enron corpus" })).toBeVisible();
}

/** What the page sent to a route, by method and path end. */
function sentTo(page: Page, method: string, end: string): unknown[] {
  const sent: unknown[] = [];
  page.on("request", (request) => {
    if (request.method() === method && request.url().endsWith(end)) sent.push(request.postDataJSON());
  });
  return sent;
}

// ADR-145 Amendment 4 decision 6 (rule 13): Change owner… opened, the people named and saved, by keyboard.
test("a dataset's owners are changed by keyboard", async ({ page }) => {
  const asked = await serve(page);
  const sent = sentTo(page, "PUT", "/datasets/enron/owners");
  await page.goto("/keyboard/admin-harness.html?rights=administer_system");
  await details(page);
  await press(page, "Change owner of Enron corpus");
  const owners = page.getByLabel("New owners of Enron corpus");
  await expect(owners).toHaveValue("eng-1");
  await owners.focus();
  await page.keyboard.press("ControlOrMeta+A");
  await page.keyboard.type("eng-1, per-2");
  await press(page, "Save owners of Enron corpus");
  await expect(page.getByText("Enron corpus's Authors are now eng-1, per-2.")).toBeVisible();
  expect(asked).toContain("PUT datasets/enron/owners");
  expect(sent).toEqual([{ people: ["eng-1", "per-2"] }]);
  registerCovered(REGISTRY, "change-a-datasets-owner-by-keyboard");
});

// ADR-145 decision 8: the promotion policy chosen and saved by keyboard; the warning below two shows.
test("a dataset's promotion policy is set by keyboard", async ({ page }) => {
  const asked = await serve(page);
  const sent = sentTo(page, "PUT", "/datasets/enron/promotion-policy");
  await page.goto("/keyboard/admin-harness.html?rights=administer_system");
  await details(page);
  const policy = page.getByLabel("Promotion policy for Enron corpus", { exact: true });
  await policy.focus();
  await page.keyboard.type("Second");
  await expect(policy).toHaveValue("second_person_reviews");
  await press(page, "Save promotion policy for Enron corpus");
  await expect(page.getByText("Enron corpus: Second person reviews.")).toBeVisible();
  await expect(page.getByRole("note")).toContainText("Fewer than two people can approve");
  expect(asked).toContain("PUT datasets/enron/promotion-policy");
  expect(sent).toEqual([{ promotion_policy: "second_person_reviews" }]);
  registerCovered(REGISTRY, "set-a-datasets-promotion-policy-by-keyboard");
});

// ADR-143 Amendment 2 decision 1 (rule 13): each removed case's entry, run dry by keyboard; an open
// case offers none, and a refusal is said in the Conduit's words.
test("a removed case's layer is merged, as a dry run, by keyboard", async ({ page }) => {
  const asked = await serve(page);
  await page.goto("/keyboard/admin-harness.html?rights=administer_system");
  await details(page);
  await expect(page.getByRole("button", { name: "Merge Op Kestrel into the dataset (dry run)" })).toHaveCount(0);
  await press(page, "Merge Op Heron into the dataset (dry run)");
  await expect(page.getByRole("status")).toContainText("Would merge 5 items and 4 links (48.8 kB)");
  expect(asked).toContain("POST datasets/enron/cases/gone-1/merge/dry-run");
  await press(page, "Merge Op Wren into the dataset (dry run)");
  await expect(page.getByRole("alert")).toContainText("Only one of the dataset's Authors may merge");
  await expect(page.getByRole("alert")).toContainText("An Author also needs Investigate");
  registerCovered(REGISTRY, "dry-run-a-removed-cases-merge-by-keyboard");
});

test("a removed case's layer is deleted, as a dry run, by keyboard", async ({ page }) => {
  const asked = await serve(page);
  await page.goto("/keyboard/admin-harness.html?rights=administer_system");
  await details(page);
  await expect(page.getByRole("button", { name: "Delete Op Kestrel's layer (dry run)" })).toHaveCount(0);
  await press(page, "Delete Op Heron's layer (dry run)");
  await expect(page.getByRole("status")).toContainText("Deleting it withdraws those not promoted; promoted items are never touched.");
  expect(asked).toContain("POST datasets/enron/cases/gone-1/delete/dry-run");
  registerCovered(REGISTRY, "dry-run-a-removed-cases-delete-by-keyboard");
});

// L2.5c (ADR-143 Amendment 5 decision 7; rule 13): Admin's own Delete, only after its dry run, by
// keyboard end to end; the Conduit's words said.
test("a removed case's layer is deleted by keyboard after its dry run", async ({ page }) => {
  const asked = await serve(page);
  await page.goto("/keyboard/admin-harness.html?rights=administer_system");
  await details(page);
  await expect(page.getByRole("button", { name: "Delete Op Heron's layer now" })).toHaveCount(0);
  await press(page, "Delete Op Heron's layer (dry run)");
  await expect(page.getByRole("status")).toContainText("You may delete it below");
  await press(page, "Delete Op Heron's layer now");
  await expect(page.getByText("Op Heron: The layer was deleted: its items are withdrawn and kept in the audit. Promoted items were not touched.")).toBeVisible();
  expect(asked).toContain("POST datasets/enron/cases/gone-1/delete");
  await expect.poll(() => asked.filter((a) => a === "GET datasets/enron/cases").length).toBe(2);
  await expect(page.getByRole("status")).toBeFocused();
  registerCovered("ADMIN_ACTIONS", "delete-a-removed-cases-layer-by-keyboard");
});

// ADR-145 Amendment 4 decision 7: Admin › System's Dataset owners may be, chosen and saved by keyboard.
test("who may own a dataset is set in System by keyboard", async ({ page }) => {
  const asked = await serve(page);
  const sent = sentTo(page, "PUT", "/settings/dataset-owners");
  await page.goto("/keyboard/admin-harness.html?rights=administer_system");
  await open(page, "System");
  const setting = page.getByLabel("Dataset owners may be", { exact: true });
  await setting.focus();
  await page.keyboard.type("Teams");
  await expect(setting).toHaveValue("teams_only");
  await press(page, "Save who dataset owners may be");
  await expect(page.getByText("Dataset owners may now be: teams only.")).toBeVisible();
  expect(asked).toContain("PUT settings/dataset-owners");
  expect(sent).toEqual([{ owners_may_be: "teams_only" }]);
  registerCovered(REGISTRY, "set-who-may-own-a-dataset-by-keyboard");
});

test("the system is asked again by keyboard", async ({ page }) => {
  const asked = await serve(page);
  await page.goto("/keyboard/admin-harness.html?rights=administer_system");
  await open(page, "System");
  await expect(page.getByText("answered in 12 ms")).toBeVisible();
  await press(page, "Ask again");
  await expect.poll(() => asked.filter((a) => a === "GET system").length).toBe(2);
  registerCovered(REGISTRY, "ask-the-system-again-by-keyboard");
});

// ADR-114 Amendment 5 (B4c): people, each action by keyboard alone.
test("a person is invited by keyboard and their one-time code is shown", async ({ page }) => {
  const asked = await serve(page);
  await page.goto("/keyboard/admin-harness.html?rights=manage_people");
  await page.getByLabel("Sign-in name").fill("new.person");
  await page.getByLabel("Invite unit").fill("verify");
  await page.getByLabel("Invite with handling code P").focus();
  await page.keyboard.press("Space");
  await page.getByLabel("Invite as Analyst").focus();
  await page.keyboard.press("Space");
  await press(page, "Invite");
  await expect(page.getByText("ABCD-EFGH-JKLM-NPQR")).toBeVisible();
  expect(asked).toContain("POST people");
  registerCovered(REGISTRY, "invite-a-person-by-keyboard");
});

test("a person's access is edited by keyboard", async ({ page }) => {
  const asked = await serve(page);
  await page.goto("/keyboard/admin-harness.html?rights=manage_people");
  await press(page, "Edit access for osprey-demo-analyst");
  await page.getByLabel("Unit for osprey-demo-analyst").fill("intel");
  await press(page, "Save access for osprey-demo-analyst");
  await expect.poll(() => asked).toContain("PUT people/u1/access");
  registerCovered(REGISTRY, "edit-a-persons-access-by-keyboard");
});

test("a person is disabled and enabled again by keyboard", async ({ page }) => {
  const asked = await serve(page);
  await page.goto("/keyboard/admin-harness.html?rights=manage_people");
  await press(page, "Disable osprey-demo-analyst");
  await press(page, "Confirm disabling osprey-demo-analyst");
  await expect(page.getByText("Disabled", { exact: true })).toBeVisible();
  await press(page, "Enable osprey-demo-analyst");
  await expect.poll(() => asked).toContain("POST people/u1/enable");
  expect(asked).toContain("POST people/u1/disable");
  registerCovered(REGISTRY, "disable-and-enable-a-person-by-keyboard");
});

test("a person's sign-in is reset by keyboard and the new code shown", async ({ page }) => {
  const asked = await serve(page);
  await page.goto("/keyboard/admin-harness.html?rights=manage_people");
  await press(page, "Reset sign-in for osprey-demo-analyst");
  await expect(page.getByText("WXYZ-WXYZ-WXYZ-WXYZ")).toBeVisible();
  expect(asked).toContain("POST people/u1/reset-sign-in");
  registerCovered(REGISTRY, "reset-a-persons-sign-in-by-keyboard");
});

// ADR-112 Amendment 3 (build order step 33 (a)): a person removed, only once confirmed, by keyboard.
test("a person is removed by keyboard once the removal is confirmed", async ({ page }) => {
  const asked = await serve(page);
  await page.goto("/keyboard/admin-harness.html?rights=manage_people");
  await press(page, "Remove osprey-demo-analyst");
  await expect(page.getByRole("group", { name: "Remove osprey-demo-analyst" })).toContainText("This cannot be undone.");
  expect(asked).not.toContain("DELETE people/u1");
  await press(page, "Confirm removing osprey-demo-analyst");
  await expect(page.getByText("Demo Analyst (osprey-demo-analyst) was removed.", { exact: false })).toBeVisible();
  expect(asked).toContain("DELETE people/u1");
  registerCovered(REGISTRY, "remove-a-person-by-keyboard");
});

// ADR-112 Amendment 3 (build order step 33 (b)): a refused organisation arrival joined, by keyboard.
test("a refused organisation arrival is joined to an account by keyboard", async ({ page }) => {
  const asked = await serve(page);
  const sent: unknown[] = [];
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().endsWith("/organisation-link")) sent.push(request.postDataJSON());
  });
  await page.goto("/keyboard/admin-harness.html?rights=manage_people");
  await press(page, "Join pat.example");
  await expect(page.getByRole("group", { name: "Join pat.example" })).toContainText("the same person");
  await press(page, "Confirm joining pat.example");
  await expect(page.getByText("pat.example is joined to osprey-demo-analyst.", { exact: false })).toBeVisible();
  expect(asked).toContain("POST people/u1/organisation-link");
  expect(sent).toEqual([{ subject: "sub-1" }]);
  registerCovered(REGISTRY, "join-an-organisation-arrival-by-keyboard");
});

test("a demo pack's command is copied by keyboard", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  const asked = await serve(page);
  await page.goto("/keyboard/admin-harness.html?rights=administer_system");
  await open(page, "Demo packs");
  await press(page, "Copy the command for hmp");
  await expect(page.getByText("Copied. Run it in a terminal on the machine OspreyFlow runs on.")).toBeVisible();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe("ospreyflow demo add hmp");
  expect(asked).toContain("GET demo-packs");
  registerCovered(REGISTRY, "copy-a-demo-pack-command-by-keyboard");
});

test("a schedule is paused and resumed by keyboard", async ({ page }) => {
  const asked = await serve(page);
  await page.goto("/keyboard/admin-harness.html?rights=operate_schedules");
  await press(page, "Pause Daily custody export");
  await expect(page.getByText("paused by admin-1")).toBeVisible();
  expect(asked).toContain("POST schedules/feed/pause");
  await press(page, "Resume Daily custody export");
  await expect(page.getByRole("button", { name: "Pause Daily custody export" })).toBeVisible();
  expect(asked).toContain("POST schedules/feed/resume");
  registerCovered(REGISTRY, "pause-and-resume-a-schedule-by-keyboard");
});

test("a schedule's runs are shown by keyboard", async ({ page }) => {
  const asked = await serve(page);
  await page.goto("/keyboard/admin-harness.html?rights=operate_schedules");
  await press(page, "Show runs of Daily custody export");
  await expect(page.getByRole("list", { name: "Runs of Daily custody export" })).toContainText(
    "Missed: the deployment was not running then",
  );
  expect(asked).toContain("GET schedules/feed/runs");
  await expect(page.getByRole("button", { name: "Hide runs of Daily custody export" })).toBeFocused();
  registerCovered(REGISTRY, "show-a-schedules-runs-by-keyboard");
});

test("a schedule is run now by keyboard, as its owner", async ({ page }) => {
  const asked = await serve(page);
  await page.goto("/keyboard/admin-harness.html?rights=operate_schedules");
  await press(page, "Run now: Daily custody export");
  await expect(page.getByRole("status")).toContainText("runs as approver-1");
  expect(asked).toContain("POST schedules/feed/run");
  registerCovered(REGISTRY, "run-a-schedule-now-by-keyboard");
});

test("a schedule is changed by keyboard, keeping its owner", async ({ page }) => {
  const asked = await serve(page);
  await page.goto("/keyboard/admin-harness.html?rights=operate_schedules");
  await press(page, "Change schedule of Daily custody export");
  const often = page.getByLabel("Run on a schedule (how often)");
  await often.selectOption("weekdays"); // a native select, as the other walkthroughs drive one
  await often.focus();
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("At (time)", { exact: true })).toBeFocused();
  await page.keyboard.type("0730");
  await expect(page.getByRole("status", { name: "Schedule preview" })).toContainText("every weekday at 07:30");
  await press(page, "Save schedule of Daily custody export");
  await expect(page.getByText("now runs every weekday at 07:30 (Europe/London), still as approver-1")).toBeVisible();
  expect(asked).toContain("PUT schedules/feed");
  registerCovered(REGISTRY, "change-a-schedule-by-keyboard");
});

test("a connection is named by keyboard", async ({ page }) => {
  const asked = await serve(page);
  await page.goto("/keyboard/admin-harness.html?rights=administer_system");
  await open(page, "Connections");
  await expect(page.getByText("Files: the ingest root")).toBeVisible();
  await page.getByRole("textbox", { name: "Connection name" }).focus();
  await page.keyboard.type("Second folder");
  await press(page, "Name the connection");
  await expect(page.getByText("Named Second folder.")).toBeVisible();
  expect(asked).toContain("POST connections");
  registerCovered(REGISTRY, "name-a-connection-by-keyboard");
});

// L2.7 (ADR-140 Amendments 13 and 15; rule 13): a SQL connection named with its fields by keyboard,
// its secret by name, and a JSON connection bound to its dataset.
test("a SQL and a JSON connection are named with their fields by keyboard", async ({ page }) => {
  await serve(page);
  const sent = sentTo(page, "POST", "/v1/admin/connections");
  await page.goto("/keyboard/admin-harness.html?rights=administer_system");
  await open(page, "Connections");
  await page.getByLabel("Kind").selectOption("sql");
  const type = async (name: string, text: string, clear = false) => {
    await page.getByRole("textbox", { name, exact: true }).focus();
    if (clear) await page.keyboard.press("ControlOrMeta+a");
    await page.keyboard.type(text);
  };
  await type("Connection name", "Client replica (synthetic)");
  await page.getByRole("checkbox", { name: "Enron corpus" }).focus();
  await page.keyboard.press("Space");
  await type("Host", "replica.client.example");
  await type("Database", "nomis");
  await type("Read-only login", "osprey_reader");
  await type("Secret's name (the login's password)", "NOMIS_REPLICA");
  await press(page, "Name the connection");
  await expect(page.getByText("Named Client replica (synthetic).")).toBeVisible();
  registerCovered(REGISTRY, "name-a-sql-connection-by-keyboard");
  await page.getByLabel("Kind").selectOption("json");
  await type("Connection name", "Exports (synthetic)");
  await page.getByRole("checkbox", { name: "Enron corpus" }).focus();
  await page.keyboard.press("Space");
  await press(page, "Name the connection");
  await expect(page.getByText("Named Exports (synthetic).")).toBeVisible();
  expect(sent).toEqual([
    { kind: "sql", name: "Client replica (synthetic)", datasets: ["enron"],
      settings: { kind: "sql", host: "replica.client.example", port: 5432, database: "nomis", user: "osprey_reader",
                  secret: "NOMIS_REPLICA", tls: "verify-full", schemas: ["public"] } },
    { kind: "json", name: "Exports (synthetic)", datasets: ["enron"], settings: { kind: "json" } },
  ]); // prettier-ignore
  registerCovered(REGISTRY, "name-a-json-connection-by-keyboard");
});

// L1.9 (ADR-148; rule 13): an Amazon S3 bucket and Amazon Athena named with their fields by keyboard,
// the cloud role's words read with the region, and no field a key or a secret could be typed into.
test("an S3 and an Athena connection are named with their fields by keyboard", async ({ page }) => {
  await serve(page);
  const sent = sentTo(page, "POST", "/v1/admin/connections");
  await page.goto("/keyboard/admin-harness.html?rights=administer_system");
  await open(page, "Connections");
  const type = async (name: string, text: string, clear = false) => {
    await page.getByRole("textbox", { name, exact: true }).focus();
    if (clear) await page.keyboard.press("ControlOrMeta+a");
    await page.keyboard.type(text);
  };
  await page.getByLabel("Kind").selectOption("s3");
  await expect(page.getByRole("textbox", { name: /secret|key|password|token/i })).toHaveCount(0);
  await type("Connection name", "Client exports (synthetic)");
  await page.getByRole("checkbox", { name: "Enron corpus" }).focus();
  await page.keyboard.press("Space");
  await expect(page.getByRole("textbox", { name: "Region", exact: true })).toHaveAccessibleDescription(/never with a key/);
  await type("Bucket", "synthetic-exports");
  await type("Folder sources may read under (empty for the whole bucket)", "client-a/");
  await press(page, "Name the connection");
  await expect(page.getByText("Named Client exports (synthetic).")).toBeVisible();
  registerCovered(REGISTRY, "name-an-s3-connection-by-keyboard");
  await page.getByLabel("Kind").selectOption("athena");
  await expect(page.getByRole("textbox", { name: /secret|key|password|token/i })).toHaveCount(0);
  await type("Connection name", "Client Athena (synthetic)");
  await page.getByRole("checkbox", { name: "Enron corpus" }).focus();
  await page.keyboard.press("Space");
  await type("Databases a source may read (comma-separated)", "visits");
  // The catalog, by keyboard too (09 §2; the orchestrator's review of L1.9, round 1, item 8).
  await expect(page.getByRole("textbox", { name: "Catalog", exact: true })).toHaveValue("AwsDataCatalog");
  await type("Catalog", "client_catalog", true);
  await press(page, "Name the connection");
  await expect(page.getByText("Named Client Athena (synthetic).")).toBeVisible();
  expect(sent).toEqual([
    { kind: "s3", name: "Client exports (synthetic)", datasets: ["enron"],
      settings: { kind: "s3", region: "eu-west-2", bucket: "synthetic-exports", prefix: "client-a/" } },
    { kind: "athena", name: "Client Athena (synthetic)", datasets: ["enron"],
      settings: { kind: "athena", region: "eu-west-2", workgroup: "primary", catalog: "client_catalog",
                  databases: ["visits"] } },
  ]); // prettier-ignore
  registerCovered(REGISTRY, "name-an-athena-connection-by-keyboard");
});

// L2.7 (ADR-145 decision 12, ADR-143 Amendment 6; rule 13): the grading scheme read, and its change
// command, the dry run's, copied by keyboard; nothing on the page changes the scheme.
test("the grading scheme is read and its change command copied by keyboard", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  const asked = await serve(page);
  await page.goto("/keyboard/admin-harness.html?rights=administer_system");
  await open(page, "Grading scheme");
  await expect(page.getByRole("table", { name: "The grades of admiralty" })).toContainText("A, B, C, D, E, F");
  await press(page, "Copy the grading change command");
  await expect(page.getByText("Copied. Run it in a terminal on the machine OspreyFlow runs on, the dry run first.")).toBeVisible();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe("ospreyflow grading change --to <scheme> --mapping <file> --dry-run");
  expect(asked.filter((a) => !a.startsWith("GET "))).toEqual([]);
  registerCovered(REGISTRY, "copy-the-grading-change-command-by-keyboard");
});

// L2.7 (ADR-140 Amendments 13 and 15; rule 13): an API connection's fields filled by keyboard, its
// dataset ticked by Space, its secret by name with the tip read with it; then Test connection.
test("an API connection is named with its fields, and a connection tested, by keyboard", async ({ page }) => {
  const asked = await serve(page);
  const sent = sentTo(page, "POST", "/v1/admin/connections");
  await page.goto("/keyboard/admin-harness.html?rights=administer_system");
  await open(page, "Connections");
  await page.getByLabel("Kind").selectOption("api"); // a native select, as the other walkthroughs drive one
  await page.getByRole("textbox", { name: "Connection name" }).focus();
  await page.keyboard.type("Carrier API (synthetic)");
  await page.getByRole("checkbox", { name: "Enron corpus" }).focus();
  await page.keyboard.press("Space");
  const base = page.getByRole("textbox", { name: "Base URL" });
  await base.focus();
  await page.keyboard.press("ControlOrMeta+a");
  await page.keyboard.type("https://carrier.example");
  await page.getByLabel("Sign-in").selectOption("bearer");
  const secret = page.getByRole("textbox", { name: "Secret's name (the token)" });
  await secret.focus();
  await expect(secret).toHaveAccessibleDescription(/never the password or token itself/);
  await page.keyboard.type("CARRIER_API");
  await press(page, "Name the connection");
  await expect(page.getByText("Named Carrier API (synthetic).")).toBeVisible();
  expect(sent).toEqual([{ kind: "api", name: "Carrier API (synthetic)", datasets: ["enron"],
                          settings: { kind: "api", base_url: "https://carrier.example", auth: "bearer", secret: "CARRIER_API", pagination: "none" } }]); // prettier-ignore
  registerCovered(REGISTRY, "name-an-api-connection-by-keyboard");
  await press(page, "Test connection: Telco lookup (synthetic)");
  await expect(page.getByRole("status").filter({ hasText: "The host is allowed" })).toBeVisible();
  expect(asked).toContain("POST connections/c-api/test");
  registerCovered(REGISTRY, "test-a-connection-by-keyboard");
});

// ADR-145 decision 5 (rule 13): the side list is walked by Tab and a section opened by Enter; focus
// moves to the section's heading, the list marks it current, and its screen reads from the Conduit.
test("Admin's sections are moved between by keyboard", async ({ page }) => {
  const asked = await serve(page);
  await page.goto("/keyboard/admin-harness.html?rights=manage_people,manage_dashboards,administer_system");
  await expect(page.getByRole("heading", { name: "People and roles" })).toBeVisible();
  await section(page, "People and roles").focus();
  await page.keyboard.press("Tab");
  await expect(section(page, "Roles")).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(section(page, "Dashboard identities")).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Dashboard identities" })).toBeFocused();
  await expect(section(page, "Dashboard identities")).toHaveAttribute("aria-current", "page");
  await expect(section(page, "People and roles")).not.toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("table", { name: "Dashboard identities" })).toBeVisible();
  expect(asked).toContain("GET dashboards");
  registerCovered(REGISTRY, "move-between-admin-sections-by-keyboard");
});

// ADR-145 decision 5: a section not built yet opens by keyboard to say what it will hold, and asks the
// Conduit nothing.
test("a coming section is opened by keyboard, and calls nothing", async ({ page }) => {
  const asked = await serve(page);
  await page.goto("/keyboard/admin-harness.html?rights=administer_system");
  await expect(page.getByRole("heading", { name: "Datasets" })).toBeVisible();
  await expect.poll(() => asked).toContain("GET datasets");
  const before = asked.length;
  await open(page, "Uploads (coming)");
  await expect(page.getByRole("heading", { name: "Uploads" })).toBeFocused();
  await expect(page.getByText(/^Coming: The largest picture/)).toBeVisible();
  await expect(section(page, "Uploads (coming)")).toHaveAttribute("aria-current", "page");
  expect(asked.length).toBe(before);
  registerCovered(REGISTRY, "open-a-coming-admin-section-by-keyboard");
});

// L2.5 (ADR-145 decisions 6 and 7 and Amendment 5; rule 13): every new action of People and Roles, by
// keyboard alone, each proving its call reached the server with what it says.
test("a person is given the Super user preset by keyboard", async ({ page }) => {
  const asked = await serve(page);
  const sent: unknown[] = [];
  page.on("request", (r) => r.url().endsWith("/people/u1/roles") && sent.push(r.postDataJSON()));
  await page.goto("/keyboard/admin-harness.html?rights=manage_people");
  await press(page, "Super user preset for osprey-demo-analyst");
  await press(page, "Save roles for osprey-demo-analyst");
  await expect.poll(() => asked).toContain("PUT people/u1/roles");
  expect((sent[0] as { roles: string[] }).roles.slice().sort()).toEqual(["analyst", "data_engineer", "rule_author"]);
  registerCovered(REGISTRY, "give-the-super-user-preset-by-keyboard");
});

test("a person is given a custom role by keyboard", async ({ page }) => {
  const asked = await serve(page);
  const sent: unknown[] = [];
  page.on("request", (r) => r.url().endsWith("/people/u1/roles") && sent.push(r.postDataJSON()));
  await page.goto("/keyboard/admin-harness.html?rights=manage_people");
  await page.getByLabel("Intel desk for osprey-demo-analyst").focus();
  await page.keyboard.press("Space");
  await press(page, "Save roles for osprey-demo-analyst");
  await expect.poll(() => asked).toContain("PUT people/u1/roles");
  expect((sent[0] as { roles: string[] }).roles).toContain("role:r1");
  registerCovered(REGISTRY, "give-a-custom-role-by-keyboard");
});

test("an Author is named for a case with none by keyboard", async ({ page }) => {
  const asked = await serve(page);
  await page.goto("/keyboard/admin-harness.html?rights=manage_people");
  await page.getByLabel("Author for Op Wren").focus();
  // A closed select takes an arrow key differently by platform; typing an option's start chooses it.
  await page.keyboard.type("Bea");
  await expect(page.getByLabel("Author for Op Wren")).toHaveValue("u3");
  await press(page, "Name an Author of Op Wren");
  await expect.poll(() => asked).toContain("PUT cases/c3/authors/u3");
  await expect(page.getByText("Bea Engineer is now an Author of Op Wren.")).toBeVisible();
  registerCovered(REGISTRY, "name-an-author-by-keyboard");
});

test("a person's case is transferred and they are disabled by keyboard", async ({ page }) => {
  const asked = await serve(page, { owns: true });
  const sent: unknown[] = [];
  page.on("request", (r) => r.url().endsWith("/people/u1/disable") && sent.push(r.postDataJSON()));
  await page.goto("/keyboard/admin-harness.html?rights=manage_people");
  await press(page, "Disable osprey-demo-analyst");
  for (const label of ["Only Author of the case Op Kestrel", "A watch on an item they drew in the case Op Kestrel"]) {
    const choice = page.getByLabel(`Transfer to, for ${label}`);
    await choice.focus();
    await page.keyboard.type("Bea");
    await expect(choice).toHaveValue("u3");
  }
  await press(page, "Transfer and disable osprey-demo-analyst");
  await expect.poll(() => asked).toContain("POST people/u1/disable");
  expect(sent[0]).toEqual({
    transfers: [
      { kind: "case_author", id: "c1", to: "u3" },
      { kind: "drawn_watch", id: "w1", to: "u3" },
    ],
  });
  registerCovered(REGISTRY, "transfer-and-disable-a-person-by-keyboard");
});

test("a built-in role is copied into a new role by keyboard", async ({ page }) => {
  const asked = await serve(page);
  const sent: unknown[] = [];
  page.on("request", (r) => r.url().endsWith("/v1/admin/roles") && r.method() === "POST" && sent.push(r.postDataJSON()));
  await page.goto("/keyboard/admin-harness.html?rights=manage_people");
  await open(page, "Roles");
  await press(page, "Copy Analyst into a new role");
  await page.getByLabel("Role name").fill("Desk analyst");
  await page.getByLabel("Triage alerts").focus();
  await page.keyboard.press("Space");
  await press(page, "Save new role");
  await expect.poll(() => asked).toContain("POST roles");
  expect(sent[0]).toEqual({ name: "Desk analyst", rights: ["investigate"] });
  registerCovered(REGISTRY, "copy-a-built-in-role-by-keyboard");
});

test("a custom role is made by keyboard", async ({ page }) => {
  const asked = await serve(page);
  await page.goto("/keyboard/admin-harness.html?rights=manage_people");
  await open(page, "Roles");
  await press(page, "New role");
  await page.getByLabel("Role name").fill("Reports desk");
  await page.getByLabel("Investigate").focus();
  await page.keyboard.press("Space");
  await press(page, "Save new role");
  await expect.poll(() => asked).toContain("POST roles");
  await expect(page.getByText("Reports desk saved as v1.")).toBeVisible();
  registerCovered(REGISTRY, "make-a-custom-role-by-keyboard");
});

// ADR-145 Amendment 4 decision 12 (L2.12): each right's tip is read with its box when it takes focus,
// and the one help page opens from Admin and is left, by keyboard.
test("a right's tip is read with its box, and Roles, teams and Authors is opened and left, by keyboard", async ({ page }) => {
  await serve(page);
  await page.goto("/keyboard/admin-harness.html?rights=manage_people");
  await open(page, "Roles");
  await press(page, "New role");
  const box = page.getByLabel("Review promotions");
  await box.focus();
  await expect(box).toHaveAccessibleDescription("Review items proposed for a dataset.");
  registerCovered(REGISTRY, "read-a-rights-tip-by-keyboard");
  await press(page, "Roles, teams and Authors");
  await expect(page.getByRole("heading", { level: 2, name: "Roles, teams and Authors" })).toBeVisible();
  await expect(page.getByRole("button", { name: "← Back to Admin" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("navigation", { name: "Admin sections" })).toBeVisible();
  registerCovered(REGISTRY, "open-and-leave-roles-teams-and-authors-from-admin-by-keyboard");
});

test("a custom role's versions are shown by keyboard", async ({ page }) => {
  const asked = await serve(page);
  await page.goto("/keyboard/admin-harness.html?rights=manage_people");
  await open(page, "Roles");
  await press(page, "Versions of Intel desk");
  await expect.poll(() => asked).toContain("GET roles/r1/versions");
  await expect(page.getByRole("list", { name: "Versions of Intel desk" })).toContainText("v1, 2026-11-08 by adm-1: Investigate");
  registerCovered(REGISTRY, "show-a-roles-versions-by-keyboard");
});

test("a custom role is edited by keyboard into its next version", async ({ page }) => {
  const asked = await serve(page);
  await page.goto("/keyboard/admin-harness.html?rights=manage_people");
  await open(page, "Roles");
  await press(page, "Edit Intel desk");
  await page.getByLabel("Triage alerts").focus();
  await page.keyboard.press("Space");
  await press(page, "Save Intel desk");
  await expect.poll(() => asked).toContain("PUT roles/r1");
  await expect(page.getByText("Intel desk saved as v2.")).toBeVisible();
  registerCovered(REGISTRY, "edit-a-custom-role-by-keyboard");
});

test("a role's team is saved, its lead handed over and a cover named by keyboard", async ({ page }) => {
  const asked = await serve(page);
  await page.goto("/keyboard/admin-harness.html?rights=manage_people");
  await open(page, "Roles");
  await press(page, "Team for Intel desk");
  await page.getByLabel("Team mailbox for Intel desk").fill("intel-desk@example.org");
  await press(page, "Save team Intel desk");
  await expect.poll(() => asked).toContain("PUT roles/r1/team");
  registerCovered(REGISTRY, "make-a-role-a-team-by-keyboard");
  const lead = page.getByLabel("Lead of Intel", { exact: true });
  await lead.focus();
  await page.keyboard.type("Bea");
  await expect(lead).toHaveValue("u3");
  await press(page, "Hand over the lead of Intel");
  await expect.poll(() => asked).toContain("PUT teams/r1/lead");
  registerCovered(REGISTRY, "hand-over-a-teams-lead-by-keyboard");
  const cover = page.getByLabel("Cover for Intel", { exact: true });
  await cover.focus();
  await page.keyboard.type("Demo");
  await expect(cover).toHaveValue("u1");
  await page.getByLabel("Cover's last day for Intel").fill("2026-11-14");
  await press(page, "Save cover for Intel");
  await expect.poll(() => asked).toContain("PUT teams/r1/cover");
  await expect(page.getByText("Cover saved.")).toBeVisible();
  registerCovered(REGISTRY, "name-a-teams-cover-by-keyboard");
  await cover.focus();
  await page.keyboard.type("No cover");
  await expect(cover).toHaveValue("");
  const ended = page.waitForRequest((r) => r.url().endsWith("/teams/r1/cover") && r.postDataJSON()?.cover === null);
  await press(page, "End cover for Intel");
  expect((await ended).postDataJSON()).toEqual({ cover: null, until: null });
  await expect(page.getByText("Cover ended.")).toBeVisible();
  registerCovered(REGISTRY, "end-a-teams-cover-by-keyboard");
});

// L2.6 (ADR-145 decisions 9 and 10; rule 13): Audit's filters, its rule audit and its paging, and
// Operations' N days, by keyboard alone, each proving its call reached the server with what it says.
test("the audit is read by kind and person by keyboard", async ({ page }) => {
  const asked = await serve(page);
  await page.goto("/keyboard/admin-harness.html?rights=read_audit");
  await expect(page.getByRole("heading", { name: "Audit" })).toBeVisible();
  await expect(page.getByRole("table", { name: "Audit entries" })).toContainText("Withheld");
  const kind = page.getByLabel("Kind");
  await kind.focus();
  await page.keyboard.type("Analyst");
  await expect(kind).toHaveValue("assertions");
  const person = page.getByLabel("Person");
  await person.focus();
  await page.keyboard.type("Zed");
  await expect(person).toHaveValue("Zed Reviewer");
  await press(page, "Show entries");
  await expect.poll(() => asked.filter((a) => a.startsWith("AUDIT"))).toContainEqual(
    expect.stringContaining("AUDIT audit kind=assertions&who=Zed+Reviewer"),
  );
  registerCovered(REGISTRY, "read-the-audit-by-kind-and-person-by-keyboard");
});

test("a case's rule audit is read in Audit by keyboard", async ({ page }) => {
  const asked = await serve(page);
  await page.goto("/keyboard/admin-harness.html?rights=read_audit,read_rule_audit");  // the Conduit asks osprey-admin too
  await expect(page.getByRole("table", { name: "Audit entries" })).toBeVisible();
  const record = page.getByLabel("Record");
  await record.focus();
  await page.keyboard.type("Rule");
  await expect(record).toHaveValue("rules");
  await page.getByLabel("Case (id, required)").focus();
  await page.keyboard.type("c1");
  await press(page, "Show entries");
  await expect.poll(() => asked).toContainEqual(expect.stringContaining("AUDIT audit/rules case=c1"));
  await expect(page.getByRole("table", { name: "Audit entries" })).toContainText("rule deployed");
  registerCovered(REGISTRY, "read-a-cases-rule-audit-by-keyboard");
});

test("the audit is paged by keyboard", async ({ page }) => {
  const asked = await serve(page);
  await page.goto("/keyboard/admin-harness.html?rights=read_audit");
  await expect(page.getByText("Entries 1–1 of 120, newest first.")).toBeVisible();
  await press(page, "Older entries");
  await expect(page.getByText("Entries 51–51 of 120, newest first.")).toBeVisible();
  expect(asked).toContainEqual(expect.stringContaining("offset=50"));
  await press(page, "Newer entries");
  await expect(page.getByText("Entries 1–1 of 120, newest first.")).toBeVisible();
  registerCovered(REGISTRY, "page-through-the-audit-by-keyboard");
});

test("when promotions are overdue is set in Operations by keyboard", async ({ page }) => {
  const asked = await serve(page);
  await page.goto("/keyboard/admin-harness.html?rights=operate_schedules");
  await expect(page.getByText("After 3 days it is flagged overdue.")).toBeVisible();
  const days = page.getByLabel("Alert the reviewers and administrators after N days");
  await days.focus();
  await page.keyboard.press("ArrowUp");
  await expect(days).toHaveValue("4");
  const sent = page.waitForRequest((r) => r.url().endsWith("/settings/promotion-alert-days") && r.method() === "PUT");
  await press(page, "Save when promotions are overdue");
  expect((await sent).postDataJSON()).toEqual({ alert_after_days: 4 });
  // The request is seen as it leaves; the harness records it as it answers, so wait for that.
  await expect.poll(() => asked).toContain("PUT settings/promotion-alert-days");
  registerCovered(REGISTRY, "set-when-promotions-are-overdue-by-keyboard");
});

// L2.7 (ADR-145 Amendment 4 decision 12; rule 13): the tips of People, Roles and Datasets, each read
// with the control it explains as that control takes focus, in roles' names and never people.
test("a role's, a team lead's and a dataset's Authors' tips are read with their controls by keyboard", async ({ page }) => {
  await serve(page);
  await page.goto("/keyboard/admin-harness.html?rights=manage_people,administer_system");
  await open(page, "People and roles");
  const box = page.getByRole("checkbox", { name: "Data Engineer for osprey-demo-analyst" });
  await box.focus();
  await expect(box).toBeFocused();
  await expect(box).toHaveAccessibleDescription(/reviews promotions into a dataset/);
  registerCovered(REGISTRY, "read-a-roles-tip-by-keyboard");
  await open(page, "Roles");
  await press(page, "Team for Intel desk");
  const lead = page.getByRole("combobox", { name: "Lead of Intel" });
  await lead.focus();
  await expect(lead).toHaveAccessibleDescription(/A team's lead may give a team alert to a named member/);
  await expect(lead).not.toHaveAccessibleDescription(/Demo Analyst|Bea Engineer/);
  registerCovered(REGISTRY, "read-a-teams-lead-tip-by-keyboard");
  await details(page);
  const owner = page.getByRole("button", { name: "Change owner of Enron corpus" });
  await owner.focus();
  await expect(owner).toHaveAccessibleDescription(/A dataset's Authors answer for it/);
  registerCovered(REGISTRY, "read-a-datasets-authors-tip-by-keyboard");
});

test("every registered Admin action has its own proving test case above", () => {
  assertAllCovered("ADMIN_ACTIONS", ADMIN_ACTIONS);
});
