// A keyboard-only walkthrough of the Ingest Studio's "Checks on load" step (`06_DECISIONS.md` ADR-133
// decision 6, stage (d); `CLAUDE.md` rule 13): reached from a pipeline, a case rule attached and set
// to hold its rows on a hit, the choice saved (rule ids and choices only — nothing here writes a
// rule), and Verify's would-be alerts read beside the rejection report — no `page.mouse`, no
// `.click()`. Each action proves its effect reached the server. Synthetic data only (rule 9).
import { expect, test, type Locator, type Page } from "@playwright/test";

import { CHECKS_ON_LOAD_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

const REGISTRY = "CHECKS_ON_LOAD_ACTIONS";

const CHAIN = {
  nodes: [
    { id: "domain", kind: "domain_model", label: "Domain model", config: { pack: "pole" } },
    { id: "source", kind: "source", label: "Customers", config: {} },
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
  recipe_id: "r1", version: 1, status: "draft", label: "Customer onboarding", connector_profile: "generic-csv",
  source_location: null, handling: {}, legal_basis: null, owning_unit: "unit-1", created_by: "engineer",
  created_at: "2026-11-01T09:00:00Z", pipeline: CHAIN, unmapped_fields: [], ready_for_profile: false,
};  // prettier-ignore

const CHECKS = {
  recipe_id: "r1",
  chosen: false,
  checks: [],
  available: [
    { rule_id: "r-case", name: "Listed people", words: "When a Person whose listing is one of sanction, pep, raise a high-severity alert for the case team, after each load commits.",
      scope: "this_case", trigger: "post_commit", severity: "high", status: "active", can_hold: false, always_applies: false, authors_on_hit: "alert" },
    { rule_id: "r-cash", name: "Large cash", words: "The large cash typology, before each load commits.", scope: "this_case",
      trigger: "pre_commit", severity: "medium", status: "active", can_hold: true, always_applies: false, authors_on_hit: "alert" },
    { rule_id: "r-wide", name: "Sanctions everywhere", words: "When a Person is on a screening list (name match 0.9), raise a high-severity alert for every case's team, before each load commits.",
      scope: "deployment", trigger: "pre_commit", severity: "high", status: "active", can_hold: true, always_applies: true, authors_on_hit: "alert" },
  ],
};  // prettier-ignore

const VERIFY = {
  rows_read: 3, rows_deduplicated: 0, rows_already_loaded: 0, sample_is_whole_source: true, values_masked: false,
  entities_by_type: { Person: { created: 3, referenced: 0 } }, edges_by_type: {},
  rejections: [{ reason: "Person.listing is not a valid enum", count: 1, samples: [{ row_index: 2, reason: "Person.listing is not a valid enum", sample: "{'name': 'Adeyemi', 'listing': 'none'}" }] }],
  nodes: [], edges: [], checks_judged: 2,
  would_raise: [
    { rule_id: "r-cash", rule_name: "Large cash", severity: "medium", on_hit: "hold", entity_id: "p1", entity_type: "Person", entity_name: "Callum Okafor" },
    { rule_id: "r-wide", rule_name: "Sanctions everywhere", severity: "high", on_hit: "alert", entity_id: "p1", entity_type: "Person", entity_name: "Callum Okafor" },
  ],
  checks_not_judged: [{ rule_id: "r-case", rule_name: "Listed people", why: "It counts events, which a dry run does not make; it is judged when the load runs." }],
};  // prettier-ignore

const ONTOLOGY = {
  version: 1,
  entity_types: [{ name: "Person", pole_class: "person", channel: "cyan", shape: "circle", properties: [] }],
  edge_types: [],
};

interface Sent {
  method: string;
  path: string;
  body: unknown;
}

async function serveChecks(page: Page): Promise<Sent[]> {
  const sent: Sent[] = [];
  await page.route("**/*/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();
    const json = (status: number, body: unknown) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    const body = method === "GET" ? undefined : request.postDataJSON();
    if (method !== "GET") sent.push({ method, path, body });
    if (path.endsWith("/v1/ingest/packs")) return json(200, [{ name: "pole", label: "Bespoke POLE (the core model)", entity_types: [], edge_types: [] }]);
    if (path.endsWith("/v1/ontology")) return json(200, ONTOLOGY);
    if (path.endsWith("/ingest/recipes/r1/checks") && method === "GET") return json(200, CHECKS);
    if (path.endsWith("/ingest/recipes/r1/checks") && method === "PUT")
      return json(200, { ...CHECKS, chosen: true, checks: (body as { checks: unknown[] }).checks, set_by: "engineer" });
    if (path.endsWith("/ingest/recipes/r1/verify") && method === "POST") return json(200, VERIFY);
    if (path.endsWith("/ingest/recipes/r1") && method === "GET") return json(200, DRAFT);
    if (path.endsWith("/ingest/recipe-registry")) return json(200, [DRAFT]);
    return json(404, {});
  });
  await page.goto("/keyboard/pipeline-studio-harness.html");
  return sent;
}

async function press(page: Page, target: Locator) {
  await target.focus();
  await page.keyboard.press("Enter");
}

async function openChecks(page: Page) {
  await press(page, page.getByRole("button", { name: "Open Customer onboarding" }));
  await press(page, page.getByRole("button", { name: "Load rules" }));
  await expect(page.getByRole("heading", { name: "Load rules" })).toBeVisible();
}

test("the Checks on load step opens from a pipeline, by keyboard", async ({ page }) => {
  await serveChecks(page);
  await openChecks(page);
  await expect(page.getByText(/Nothing has been chosen yet/)).toBeVisible();
  await expect(page.getByRole("checkbox", { name: "Apply Sanctions everywhere" })).toBeDisabled();
  registerCovered(REGISTRY, "open-checks-on-load-by-keyboard");
});

test("a rule is attached, left off and set to hold on a hit, and the choice saved, by keyboard", async ({ page }) => {
  const sent = await serveChecks(page);
  await openChecks(page);
  // Before anyone chooses, every case rule applies: leave one off with Space.
  await page.getByRole("checkbox", { name: "Apply Listed people" }).focus();
  await page.keyboard.press("Space");
  await expect(page.getByRole("checkbox", { name: "Apply Listed people" })).not.toBeChecked();
  await page.getByRole("combobox", { name: "A hit of Large cash" }).selectOption("hold");
  registerCovered(REGISTRY, "attach-a-rule-and-hold-on-a-hit-by-keyboard");
  await press(page, page.getByRole("button", { name: "Save the load rules" }));
  await expect(page.getByRole("status")).toContainText("Saved: 1 rule(s) attached to this pipeline.");
  const put = sent.find((s) => s.method === "PUT");
  expect(put?.body).toEqual({ checks: [{ rule_id: "r-cash", on_hit: "hold" }] });
  registerCovered(REGISTRY, "save-the-checks-by-keyboard");
});

test("Verify's would-be alerts are read beside the rejections, by keyboard", async ({ page }) => {
  await serveChecks(page);
  await press(page, page.getByRole("button", { name: "Open Customer onboarding" }));
  await press(page, page.getByRole("button", { name: "Test", exact: true }));
  await press(page, page.getByRole("button", { name: "Run the test" }));
  const raised = page.getByRole("list", { name: "Alerts this sample would raise" });
  await expect(raised).toContainText("Large cash · medium severity · Callum Okafor (Person) would hold its rows for review");
  await expect(page.getByRole("list", { name: "Checks a dry run cannot judge" })).toContainText("It counts events");
  await expect(page.getByText(/Nothing was raised, held or written/)).toBeVisible();
  await expect(page.getByText("Person.listing is not a valid enum", { exact: false }).first()).toBeVisible();
  registerCovered(REGISTRY, "read-the-alerts-a-sample-would-raise-by-keyboard");
});

test("every registered Checks on load action has its own proving test case above", () => {
  assertAllCovered("CHECKS_ON_LOAD_ACTIONS", CHECKS_ON_LOAD_ACTIONS);
});
