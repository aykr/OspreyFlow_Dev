// Phase 6's exit, walked live (ADR-140 Amendment 10): chapter 4's *Intelligence reports* pipeline
// built from scratch in guided mode through the real Glass and a running Conduit, by keys alone, with
// the same steps `keyboard/ingest-studio.spec.ts` proves against its harness. Then Test, Deploy as v1
// and Run now from the Runs tab. Its map must equal the committed one, as the Conduit stores it, and
// Test and the run must read the file as chapter 4 says: 350 reports, the teaching row rejected.
//
// Not in CI and never against a deployment someone uses: it writes a pipeline into the case. It needs
// the synthetic Prison Intelligence case seeded on a throwaway stack (`scripts.seed_pid`) under the
// stack lease, and skips itself unless `OSPREY_TEST_LIVE_GLASS=1`. Run from `apps/workspace`:
//
//   OSPREY_TEST_LIVE_GLASS=1 OSPREY_LIVE_API_BASE_URL=… OSPREY_LIVE_BEARER_TOKEN=… \
//   OSPREY_LIVE_INVESTIGATION_ID=… OSPREY_WALK_REPORTS_FILE=<the file's source location> \
//   npx playwright test --config live/playwright.config.ts live/studio-reports-walk.spec.ts
import { expect, test, type Page } from "@playwright/test";

import { REPORTS_MAP, declareTheMarkingColumns, mapTheReports, meaning } from "../keyboard/reportsMap";
import { apiBaseUrl, investigationId, liveOnly, required, workspaceUrl } from "./live";

liveOnly();

// Each walk names its own pipeline, so a second walk on the same case never reads the first one's.
const NAME = `Intelligence reports, from scratch ${new Date().toISOString().slice(11, 19)}`;

async function press(page: Page, name: string | RegExp, exact = true) {
  const button = typeof name === "string" ? page.getByRole("button", { name, exact }) : page.getByRole("button", { name });
  await button.first().focus();
  await page.keyboard.press("Enter");
}

async function api(path: string): Promise<unknown> {
  const response = await fetch(`${apiBaseUrl()}${path}`, {
    headers: { Authorization: `Bearer ${required("OSPREY_LIVE_BEARER_TOKEN")}` },
  });
  if (!response.ok) throw new Error(`GET ${path}: ${response.status}`);
  return response.json();
}

test("chapter 4's reports pipeline is built from scratch in guided mode, tested, deployed and run, live", async ({ page }) => {
  test.setTimeout(900_000);
  page.setDefaultTimeout(60_000);
  const started = Date.now();
  const mark = (what: string) => console.log(`WALK ${what} at ${((Date.now() - started) / 1000).toFixed(1)}s`);
  await page.goto(workspaceUrl());
  await press(page, "Ingest Studio");
  await expect(page.getByRole("tab", { name: /Pipelines/ })).toBeVisible();
  // The reports file registered as a source, as a person registers it: its marking, the units its
  // rows may name, its legal basis (the committed recipe's defaults).
  const sources = (await api("/v1/datasets/prison-intelligence/sources")) as { location: string }[];
  const registered = sources.some((src) => src.location.endsWith("pid_intel_reports.csv"));
  if (!registered) {
    await page.getByRole("tab", { name: /Sources/ }).focus();
    await page.keyboard.press("Enter");
    await press(page, "Register a source");
    await press(page, "Next");
    const file = page.getByRole("combobox", { name: "File" });
    await file.focus();
    await file.selectOption(required("OSPREY_WALK_REPORTS_FILE"));
    await press(page, "Next");
    for (const [name, value] of [["Classification", "OFFICIAL"], ["Handling code", "P"]] as const) {
      const field = page.getByRole("combobox", { name, exact: true });
      await field.focus();
      await field.selectOption(value);
    }
    for (const [name, value] of [["Originator", "fenwick-moor-security"], ["Owning unit", "fenwick-moor-security"],
      ["Units its rows may name (comma between)", "fenwick-moor-security, regional-intel-unit"],
      ["Legal basis", "Synthetic demonstration data"]] as const) {  // prettier-ignore
      await page.getByRole("textbox", { name, exact: true }).focus();
      await page.keyboard.type(value);
    }
    await press(page, "Register");
    await expect(page.getByRole("region", { name: /^Source / })).toBeVisible();
    mark("source registered");
    await press(page, "Open in a pipeline");
  } else {
    // An earlier walk on this case registered it; the wizard no longer offers a registered file.
    await page.getByRole("tab", { name: /Pipelines/ }).focus();
    await page.keyboard.press("Enter");
  }
  await page.getByRole("textbox", { name: "Pipeline name" }).focus();
  await page.keyboard.type(NAME);
  await press(page, "New pipeline");
  await expect(page.getByRole("button", { name: "Guided" })).toHaveAttribute("aria-pressed", "true");
  mark("pipeline made");
  await press(page, /^Source: /);
  const chooser = page.getByRole("combobox", { name: "Registered source" });
  await chooser.focus();
  await chooser.selectOption({ label: await chooser.locator("option").filter({ hasText: /pid_intel_reports/ }).last().innerText() });
  await press(page, "Use this source");
  await press(page, "Preview");
  await press(page, "Run preview");
  await expect(page.getByRole("complementary", { name: "Drawer" }).getByRole("table")).toBeVisible();
  mark("source previewed");
  await press(page, "Settings");
  await press(page, "The draft's own settings");
  await declareTheMarkingColumns(page);
  for (const part of REPORTS_MAP.deduplicate.key) {
    await page.getByRole("textbox", { name: "Key column name" }).focus();
    await page.keyboard.type(part.field!);
    await page.keyboard.press("Enter");
  }
  await press(page, "Save");
  await expect(page.getByRole("list", { name: "Key columns" })).toContainText("report_ref");
  await press(page, "Close the drawer");
  await press(page, "Map: Map");
  await press(page, "Open map editor");
  await mapTheReports(page);
  await press(page, "Save draft");
  await expect(page.getByRole("alert")).toHaveCount(0);
  mark("map saved");

  // The map as the Conduit stores it, not as the browser sent it.
  type Stored = { recipe_id: string; label: string; row_template: unknown; unmapped_fields: unknown; deduplicate: unknown };
  const storedDraft = async () =>
    ((await api(`/v1/investigations/${investigationId()}/ingest/recipes`)) as Stored[]).find((d) => d.label === NAME);
  // The save lands after the button is pressed; read the draft once the Conduit holds its map.
  await expect.poll(async () => Boolean((await storedDraft())?.row_template), { timeout: 60_000 }).toBe(true);
  const stored = (await storedDraft())!;
  expect(meaning(stored.row_template)).toEqual(meaning(REPORTS_MAP.row_template));
  expect(meaning(stored.unmapped_fields)).toEqual(meaning(REPORTS_MAP.unmapped_fields));
  expect(meaning(stored.deduplicate)).toEqual(meaning(REPORTS_MAP.deduplicate));
  mark("stored map equals the committed map");

  await page.getByRole("navigation", { name: "Pipeline strip" }).getByRole("button", { name: "Load: Load" }).focus();
  await page.keyboard.press("Enter");
  await press(page, "Test");
  await press(page, "Run the test");
  const drawer = page.getByRole("complementary", { name: "Drawer" });
  await expect(drawer.getByText(/350/).first()).toBeVisible({ timeout: 300_000 });
  console.log(`WALK test report: ${(await drawer.innerText()).replace(/\s+/g, " ").slice(0, 600)}`);
  mark("tested");
  await press(page, "Deploy");
  await press(page, "Deploy as v1");
  await expect(page.getByText("Deployed", { exact: true })).toBeVisible();
  mark("deployed");
  await page.getByRole("tab", { name: /Runs/ }).focus();
  await page.keyboard.press("Enter");
  const pick = page.getByRole("combobox", { name: /Pipeline to run or schedule/ });
  await pick.focus();
  await pick.selectOption({ label: `${NAME} (v1)` });
  await press(page, "Run now or schedule");
  await press(page, "Run now");
  // The run, as the Conduit's ledger records it.
  type Run = { outcome: string; rows_read?: number; rows_rejected?: number; nodes_created?: number; edges_created?: number };
  const runs = async () => (await api(`/v1/investigations/${investigationId()}/ingest/recipes/${stored.recipe_id}/runs`)) as Run[];
  await expect.poll(async () => (await runs()).some((r) => r.outcome !== "running"), { timeout: 600_000, intervals: [5_000] }).toBe(true);
  const run = (await runs())[0]!;
  console.log(`WALK run: ${JSON.stringify(run)}`);
  expect(run.outcome).toBe("succeeded");
  expect(run.rows_read).toBe(350);
  expect(run.rows_rejected).toBe(1);
  mark("run");
});
