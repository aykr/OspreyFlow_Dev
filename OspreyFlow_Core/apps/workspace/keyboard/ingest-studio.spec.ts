// A keyboard-only walkthrough of the Ingest Studio's four places (ADR-140 decision 1, redesign phase
// 2; `CLAUDE.md` rule 13): the tabs, the dataset switcher, the Runs tab's grid, held rows and Run now,
// Sources' Add files, and Deploy as vN with Deploy and run now — no `page.mouse`, no `.click()`. The
// harness serves itself and records every request, so each case proves its action reached its route.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { expect, test, type Page } from "@playwright/test";

import { INGEST_STUDIO_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";
import { REPORTS_HANDLING_COLUMNS, REPORTS_MAP, buildEntity, buildLink, choose, declareTheMarkingColumns, mapTheReports, meaning, type MapEdge, type MapEntity } from "./reportsMap";

const REGISTRY = "INGEST_STUDIO_ACTIONS";
/** Phase 7's exit pipeline and map (`tests/ingest/test_visits_pipeline_fixture.py` holds it to the
 * server's own build of the exit recipe). */
const CONTACTS = JSON.parse(
  readFileSync(fileURLToPath(new URL("./fixtures/visits_and_contacts_pipeline.json", import.meta.url)), "utf8"),
) as { pipeline: { nodes: { id: string; kind: string; config: Record<string, unknown> }[] };
  row_template: unknown; unmapped_fields: { field: string; note?: string }[] };  // prettier-ignore
const HARNESS = "/keyboard/ingest-studio-harness.html";

async function press(page: Page, name: string, exact = true) {
  await page.getByRole("button", { name, exact }).focus();
  await page.keyboard.press("Enter");
}

async function tab(page: Page, name: string) {
  await page.getByRole("tab", { name }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("tab", { name })).toHaveAttribute("aria-selected", "true");
}

function asked(page: Page): Promise<{ method: string; path: string; body?: string }[]> {
  return page.evaluate(() => (window as unknown as { __asked: { method: string; path: string; body?: string }[] }).__asked);
}

test("each of the four places opens by keyboard", async ({ page }) => {
  await page.goto(HARNESS);
  await tab(page, "1 Model");
  await expect(page.getByRole("region", { name: "Target model" })).toContainText("POLE core + Crime case analysis (NIEM)");
  await tab(page, "2 Sources");
  await expect(page.getByRole("region", { name: "Sources" })).toContainText("calls.csv");
  await tab(page, "4 Runs");
  await expect(page.getByRole("region", { name: "Runs by day" })).toBeVisible();
  await tab(page, "3 Pipelines");
  await expect(page.getByRole("region", { name: "Pipelines" })).toContainText("Wing phone calls");
  registerCovered(REGISTRY, "move-between-the-four-places-by-keyboard");
});

test("the dataset is switched by keyboard, through the case that loads into it", async ({ page }) => {
  await page.goto(HARNESS);
  const switcher = page.getByRole("combobox", { name: "Dataset" });
  await expect(switcher.getByRole("option", { name: "Carrier records (synthetic)" })).toBeAttached();
  await switcher.focus();
  // A native select is the browser's own keyboard control; driven as the other walkthroughs drive one.
  await switcher.selectOption("carrier-records");
  await expect(page.getByRole("status", { name: "Case the Studio works through" })).toHaveText("inv-2");
  registerCovered(REGISTRY, "switch-dataset-by-keyboard");
});

test("a day's run report opens from its cell by keyboard, and its held rows from it", async ({ page }) => {
  await page.goto(HARNESS);
  await tab(page, "4 Runs");
  // Oldest first: the refused run five days ago, then yesterday's, which held two rows.
  const cell = page.getByRole("button", { name: /Wing phone calls, .*: needs a person/ }).last();
  await cell.focus();
  await page.keyboard.press("Enter");
  const report = page.getByRole("region", { name: "Run report" });
  await expect(report).toContainText("2 held");
  await expect(report).toContainText("--revert-load SYN-LOAD-3 --reverted-by engineer-1 --stop-api");
  registerCovered(REGISTRY, "open-a-days-run-report-by-keyboard");
  await press(page, "Open held rows");
  await expect.poll(async () => (await asked(page)).some((a) => a.path.endsWith("/held-rows"))).toBe(true);
  await expect(page.getByText(/could not judge the row/)).toBeVisible();
  registerCovered(REGISTRY, "open-held-rows-from-a-run-by-keyboard");
});

test("a deployed pipeline is run from Runs by keyboard", async ({ page }) => {
  await page.goto(HARNESS);
  await tab(page, "4 Runs");
  const choose = page.getByRole("combobox", { name: "Pipeline to run or schedule" });
  await choose.focus();
  await choose.selectOption("r-calls");
  await press(page, "Run now or schedule");
  await press(page, "Run now");
  await expect.poll(async () => (await asked(page)).some((a) => a.method === "POST" && a.path.endsWith("/r-calls/run"))).toBe(true);
  await expect(page.getByText("Load id: SYN-LOAD-4")).toBeVisible();
  registerCovered(REGISTRY, "run-a-pipeline-from-runs-by-keyboard");
  await expect(page.getByText("120 rows already loaded into this case, skipped")).toBeVisible();
  await expect(page.getByText("Nodes created: 0")).toBeVisible();
  registerCovered(REGISTRY, "read-rows-already-loaded-on-a-run-report-by-keyboard");
});

test("a paused watch is resumed from Runs, and the runs read again, by keyboard", async ({ page }) => {
  await page.goto(HARNESS);
  await tab(page, "4 Runs");
  const choose = page.getByRole("combobox", { name: "Pipeline to run or schedule" });
  await choose.focus();
  await choose.selectOption("r-calls");
  await press(page, "Run now or schedule");
  await press(page, "Resume schedule");
  await expect.poll(async () => (await asked(page)).some((a) => a.method === "POST" && a.path.endsWith("/schedule/resume"))).toBe(true);
  const before = (await asked(page)).filter((a) => a.path.endsWith("/ingest/recipe-registry")).length;
  await press(page, "Read the runs again");
  await expect.poll(async () => (await asked(page)).filter((a) => a.path.endsWith("/ingest/recipe-registry")).length).toBeGreaterThan(before);
  registerCovered(REGISTRY, "resume-a-watch-and-read-the-runs-again-by-keyboard");
});

test("Add files opens on Sources by keyboard", async ({ page }) => {
  await page.goto(HARNESS);
  await tab(page, "2 Sources");
  await press(page, "Add files");
  await expect(page.getByRole("region", { name: "Add files" })).toBeVisible();
  registerCovered(REGISTRY, "add-files-from-sources-by-keyboard");
});

test("a source is registered by keyboard, through every step", async ({ page }) => {
  await page.goto(HARNESS);
  await tab(page, "2 Sources");
  await press(page, "Register a source");
  await press(page, "Next");
  const file = page.getByRole("combobox", { name: "File" });
  await file.focus();
  await file.selectOption("harbour-extract/cell_stays.csv");
  await press(page, "Next");
  for (const [name, value] of [["Classification", "OFFICIAL"], ["Handling code", "P"]] as const) {
    const field = page.getByRole("combobox", { name });
    await field.focus();
    await field.selectOption(value);
  }
  for (const [name, value] of [["Originator", "unit-a"], ["Owning unit", "unit-a"], ["Legal basis", "Synthetic demonstration"]] as const) {
    await page.getByRole("textbox", { name, exact: true }).focus();
    await page.keyboard.type(value);
  }
  await press(page, "Register");
  await expect.poll(async () => (await asked(page)).some((a) => a.method === "POST" && a.path.endsWith("/harbour-extract/sources"))).toBe(true);
  await expect(page.getByRole("region", { name: "Source cell_stays.csv" })).toBeVisible();
  registerCovered(REGISTRY, "register-a-source-by-keyboard");
});

test("a source's governance is edited by keyboard, and says which pipelines need attention", async ({ page }) => {
  await page.goto(HARNESS);
  await tab(page, "2 Sources");
  await press(page, "Open source Wing phone calls file");
  await press(page, "Edit governance");
  const classification = page.getByRole("combobox", { name: "Classification" });
  await classification.focus();
  await classification.selectOption("SECRET");
  await press(page, "Save the governance");
  await expect(page.getByRole("status").filter({ hasText: "need attention" })).toContainText("Wing phone calls");
  registerCovered(REGISTRY, "edit-a-sources-governance-by-keyboard");
});

test("a source's refresh is set to read only rows past a watermark, by keyboard", async ({ page }) => {
  await page.goto(HARNESS);
  await tab(page, "2 Sources");
  await press(page, "Open source Wing phone calls file");
  await press(page, "Edit governance");
  const mode = page.getByRole("combobox", { name: "How each file is read" });
  await mode.focus();
  await mode.selectOption("incremental");
  await expect(page.getByText(/Still to give: a watermark column/)).toBeVisible();
  const column = page.getByRole("textbox", { name: "Watermark column (its values only grow)" });
  await column.focus();
  await page.keyboard.type("called_at");
  await press(page, "Save the governance");
  const patch = (await asked(page)).find((a) => a.method === "PATCH" && a.path.endsWith("/governance"));
  const sent = JSON.parse(patch?.body ?? "{}") as { refresh?: { mode?: string; watermark_column?: string } };
  expect([sent.refresh?.mode, sent.refresh?.watermark_column]).toEqual(["incremental", "called_at"]);
  await expect(page.getByText(/reading only the rows past the highest called_at already loaded/)).toBeVisible();
  registerCovered(REGISTRY, "set-a-sources-refresh-mode-by-keyboard");
});

test("a source's refresh is paused with why and resumed, by keyboard", async ({ page }) => {
  await page.goto(HARNESS);
  await tab(page, "2 Sources");
  await press(page, "Open source Wing phone calls file");
  const why = page.getByRole("textbox", { name: "Why pause it (optional)" });
  await why.focus();
  await page.keyboard.type("waiting for the visits step");
  await press(page, "Pause the refresh");
  await expect(page.getByText("paused: waiting for the visits step")).toBeVisible();
  await press(page, "Resume the refresh");
  await expect(page.getByRole("status").filter({ hasText: "The refresh is resumed." })).toBeVisible();
  const posted = (await asked(page)).filter((a) => a.method === "POST" && a.path.includes("/refresh/")).map((a) => a.path.split("/").pop());
  expect(posted).toEqual(["pause", "resume"]);
  registerCovered(REGISTRY, "pause-and-resume-a-sources-refresh-by-keyboard");
});

test("a source is re-profiled and opened in a pipeline by keyboard", async ({ page }) => {
  await page.goto(HARNESS);
  await tab(page, "2 Sources");
  await press(page, "Open source Wing phone calls file");
  await expect(page.getByRole("region", { name: "Profile" })).toContainText("caller");
  const before = (await asked(page)).filter((a) => a.path.endsWith("/profile")).length;
  await press(page, "Re-profile");
  await expect.poll(async () => (await asked(page)).filter((a) => a.path.endsWith("/profile")).length).toBeGreaterThan(before);
  await press(page, "Open in a pipeline");
  await expect(page.getByRole("tab", { name: "3 Pipelines" })).toHaveAttribute("aria-selected", "true");
  registerCovered(REGISTRY, "re-profile-a-source-and-open-it-in-a-pipeline-by-keyboard");
});

test("a pipeline's source is chosen from the registered sources by keyboard", async ({ page }) => {
  await page.goto(HARNESS);
  await press(page, "Open Visit bookings");
  await press(page, "Source: Call log");
  const chooser = page.getByRole("combobox", { name: "Registered source" });
  await chooser.focus();
  await chooser.selectOption("src-calls");
  await press(page, "Use this source");
  await expect.poll(async () => (await asked(page)).some((a) => a.method === "PATCH" && a.path.endsWith("/r-visits"))).toBe(true);
  await expect(page.getByRole("status").filter({ hasText: "Reads Wing phone calls file" })).toBeVisible();
  registerCovered(REGISTRY, "use-a-registered-source-in-a-pipeline-by-keyboard");
});

// Phase 3's exit criterion (ADR-140 Amendment 6): cell_stays registered from the ingest root, then
// used in a new pipeline, with no marking asked inside the pipeline — the draft carries the source's.
test("a file is registered as a source and used in a new pipeline by keyboard, asking no marking there", async ({ page }) => {
  await page.goto(HARNESS);
  await tab(page, "2 Sources");
  await press(page, "Register a source");
  await press(page, "Next");
  const file = page.getByRole("combobox", { name: "File" });
  await file.focus();
  await file.selectOption("harbour-extract/cell_stays.csv");
  await press(page, "Next");
  for (const [name, value] of [["Classification", "SECRET"], ["Handling code", "P"]] as const) {
    const field = page.getByRole("combobox", { name });
    await field.focus();
    await field.selectOption(value);
  }
  for (const [name, value] of [["Originator", "unit-a"], ["Owning unit", "unit-a"], ["Legal basis", "Synthetic demonstration"]] as const) {
    await page.getByRole("textbox", { name, exact: true }).focus();
    await page.keyboard.type(value);
  }
  await press(page, "Register");
  await press(page, "Open in a pipeline");
  await expect(page.getByRole("tab", { name: "3 Pipelines" })).toHaveAttribute("aria-selected", "true");
  await page.getByRole("textbox", { name: "Pipeline name" }).focus();
  await page.keyboard.type("Cell stays");
  await press(page, "New pipeline");
  await press(page, "Source: New source");
  const chooser = page.getByRole("combobox", { name: "Registered source" });
  await chooser.focus();
  await chooser.selectOption("src-new");
  // Nothing in the pipeline asks for a marking: the source brings it.
  await expect(page.getByRole("combobox", { name: /Classification/ })).toHaveCount(0);
  await press(page, "Use this source");
  await expect(page.getByRole("status").filter({ hasText: "Reads cell_stays.csv" })).toBeVisible();
  const patch = (await asked(page)).find((a) => a.method === "PATCH" && a.path.endsWith("/ingest/recipes/r-new"));
  const sent = JSON.parse(patch?.body ?? "{}") as { source_location?: string; handling?: { classification?: string }; legal_basis?: string };
  expect(sent.source_location).toBe("harbour-extract/cell_stays.csv");
  expect(sent.handling?.classification).toBe("SECRET");
  expect(sent.legal_basis).toBe("Synthetic demonstration");
  registerCovered(REGISTRY, "register-a-source-and-use-it-in-a-new-pipeline-by-keyboard");
});

async function openDeploy(page: Page) {
  await page.goto(HARNESS);
  await press(page, "Open Visit bookings");
  await press(page, "Deploy");
}

test("a draft is deployed as its version by keyboard, without running", async ({ page }) => {
  await openDeploy(page);
  await press(page, "Deploy as v3");
  await expect(page.getByText("Deployed", { exact: true })).toBeVisible();
  // Phase 6: Deploy opens in the drawer, and the pipeline stays beside it.
  await expect(page.getByRole("group", { name: "Pipeline" })).toBeVisible();
  const requests = await asked(page);
  expect(requests.some((a) => a.method === "POST" && a.path.endsWith("/r-visits/publish"))).toBe(true);
  expect(requests.some((a) => a.path.endsWith("/r-visits/run"))).toBe(false);
  registerCovered(REGISTRY, "deploy-a-version-by-keyboard");
});

test("a draft is deployed and run at once by keyboard", async ({ page }) => {
  await openDeploy(page);
  await press(page, "Deploy and run now");
  await expect(page.getByText("Load id: SYN-LOAD-5")).toBeVisible();
  registerCovered(REGISTRY, "deploy-and-run-now-by-keyboard");
});

// --- Phase 6 (ADR-108 Amendment 6; ADR-140 decisions 3 and 14; brief §6 and §6.5) -------------------
// The drawer beside the pipeline, Preview, Test, guided and expert mode, the Map editor's strip and
// its keyboard bind; then the reports pipeline built from scratch in guided mode (phase 6's exit).

async function openVisits(page: Page, query = "") {
  await page.goto(`${HARNESS}${query}`);
  await press(page, "Open Visit bookings");
  await expect(page.getByRole("group", { name: "Pipeline" })).toBeVisible();
}

const drawer = (page: Page) => page.getByRole("complementary", { name: "Drawer" });

test("a step's drawer opens beside the canvas by keyboard, and the canvas stays", async ({ page }) => {
  await openVisits(page);
  await press(page, "Expert");
  await press(page, "Source: Call log");
  await expect(drawer(page).getByRole("heading", { name: "Source: Call log" })).toBeVisible();
  await expect(page.getByRole("group", { name: "Pipeline" }).getByRole("button", { name: "Source: Call log" })).toHaveAttribute("aria-pressed", "true");
  await press(page, "Close the drawer");
  await expect(drawer(page).getByRole("heading")).toHaveCount(0);
  registerCovered(REGISTRY, "open-a-steps-drawer-beside-the-canvas-by-keyboard");
});

test("a source step is previewed as its rows by keyboard", async ({ page }) => {
  await openVisits(page);
  await press(page, "Source: Call log");
  await press(page, "Preview");
  await press(page, "Run preview");
  await expect(drawer(page).getByText("A sample: the first 3 rows.")).toBeVisible();
  await expect(drawer(page).getByRole("cell", { name: "SYN-0443" })).toBeVisible();
  const reads = (await asked(page)).filter((a) => a.path.includes("/r-visits/map/sample-rows/"));
  expect(reads.map((a) => a.path.split("/").at(-1))).toEqual(["0", "1", "2"]);
  registerCovered(REGISTRY, "preview-a-source-step-by-keyboard");
});

test("Map is previewed as the graph it would make by keyboard", async ({ page }) => {
  await openVisits(page);
  await press(page, "Map: Map");
  await press(page, "Preview");
  await press(page, "Run preview");
  await expect(drawer(page).getByText("From a sample of 3 rows: 3 would be created, 0 referenced, 0 links; 0 rows rejected.")).toBeVisible();
  // The dry run that marks nothing, never Test's own route (the review of L1.2).
  expect((await asked(page)).some((a) => a.method === "POST" && a.path.endsWith("/r-visits/preview-graph"))).toBe(true);
  expect((await asked(page)).some((a) => a.path.endsWith("/r-visits/verify"))).toBe(false);
  registerCovered(REGISTRY, "preview-maps-graph-by-keyboard");
});

test("the whole pipeline is tested in the drawer by keyboard, beside the pipeline", async ({ page }) => {
  await openVisits(page);
  await press(page, "Test");
  await press(page, "Run the test");
  await expect.poll(async () => (await asked(page)).some((a) => a.method === "POST" && a.path.endsWith("/r-visits/verify"))).toBe(true);
  await expect(drawer(page).getByRole("heading", { name: "Test — Visit bookings" })).toBeVisible();
  await expect(page.getByRole("list", { name: "Steps" })).toBeVisible();
  registerCovered(REGISTRY, "test-the-pipeline-in-the-drawer-by-keyboard");
});

test("guided and expert mode are switched by keyboard, and the person's choice is kept", async ({ page }) => {
  await openVisits(page);
  // Guided is the default (ADR-140 Amendment 1.3): the numbered list, and a picture with nothing to press.
  await expect(page.getByRole("button", { name: "Guided" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("list", { name: "Steps" })).toBeVisible();
  await expect(page.getByRole("group", { name: "Pipeline" }).getByRole("button")).toHaveCount(0);
  await press(page, "Expert");
  await expect(page.getByRole("list", { name: "Steps" })).toBeHidden();
  await expect(page.getByRole("group", { name: "Pipeline" }).getByRole("button")).toHaveCount(5);
  await openVisits(page);
  await expect(page.getByRole("button", { name: "Expert" })).toHaveAttribute("aria-pressed", "true");
  await press(page, "Guided");
  await expect(page.getByRole("list", { name: "Steps" })).toBeVisible();
  registerCovered(REGISTRY, "switch-guided-and-expert-mode-by-keyboard");
});

test("a step opens its drawer from guided mode's numbered list by keyboard", async ({ page }) => {
  await openVisits(page);
  const step = page.getByRole("list", { name: "Steps" }).getByRole("button", { name: "Load: Load" });
  await step.focus();
  await page.keyboard.press("Enter");
  await expect(step).toHaveAttribute("aria-pressed", "true");
  await expect(drawer(page).getByRole("heading", { name: "Load: Load" })).toBeVisible();
  registerCovered(REGISTRY, "open-a-step-from-the-guided-list-by-keyboard");
});

test("an expert step reads whole and read-only in guided mode, by keyboard", async ({ page }) => {
  await openVisits(page, "?expert=1");
  await expect(page.getByRole("list", { name: "Steps" })).toContainText("Expert step, read-only here");
  await press(page, "SQL transform: Visits per week");
  const step = drawer(page).getByRole("region", { name: "Expert step" });
  await expect(step).toContainText("SELECT visitor, count(*) AS visits FROM source GROUP BY visitor");
  await expect(step.getByRole("button")).toHaveCount(0);
  await expect(step.getByRole("textbox")).toHaveCount(0);
  registerCovered(REGISTRY, "read-an-expert-step-in-guided-mode-by-keyboard");
});

async function openTheMapEditor(page: Page) {
  await press(page, "Map: Map");
  await press(page, "Open map editor");
  await expect(page.getByRole("navigation", { name: "Pipeline strip" })).toBeVisible();
}

test("a step on the Map editor's strip goes back to the pipeline with it chosen, by keyboard", async ({ page }) => {
  await openVisits(page);
  await openTheMapEditor(page);
  await expect(page.getByRole("group", { name: "Pipeline" })).toBeHidden();
  await page.getByRole("navigation", { name: "Pipeline strip" }).getByRole("button", { name: "Source: Call log" }).focus();
  await page.keyboard.press("Enter");
  await expect(drawer(page).getByRole("heading", { name: "Source: Call log" })).toBeVisible();
  await expect(page.getByRole("group", { name: "Pipeline" })).toBeVisible();
  registerCovered(REGISTRY, "go-back-to-a-step-from-the-map-strip-by-keyboard");
});

test("a column is bound in the Map editor by choosing it and the binding, then Enter", async ({ page }) => {
  await openVisits(page);
  await openTheMapEditor(page);
  await press(page, "Choose column called");
  await expect(page.getByRole("button", { name: "Let go column called" })).toHaveAttribute("aria-pressed", "true");
  await press(page, "Entity 1: visitor (Person)");
  await press(page, "Bind called here: name");
  await expect(page.getByRole("button", { name: "Choose column called" })).toBeVisible();
  await expect(page.getByLabel("Source column")).toHaveValue("called");
  await press(page, "Save draft");
  await expect.poll(async () => (await asked(page)).filter((a) => a.method === "PUT" && a.path.endsWith("/r-visits/row-template")).length).toBe(1);
  const put = (await asked(page)).find((a) => a.method === "PUT" && a.path.endsWith("/r-visits/row-template"))!;
  const sent = JSON.parse(put.body!) as { row_template: { entities: { properties: Record<string, unknown> }[] } };
  expect(sent.row_template.entities[0]!.properties).toEqual({ name: { field: "called" } });
  registerCovered(REGISTRY, "bind-a-column-by-choosing-both-and-enter");
});

// Phase 6's exit (ADR-140 Amendment 10): chapter 4's *Intelligence reports* pipeline built from
// scratch in guided mode, by keys alone, as the demo script walks it, into exactly the committed map.
// The map is read from `fixtures/pid_intel_reports_map.json`, which
// `tests/demo_fixtures/test_reports_map_fixture.py` holds to `pid_intel_reports_recipe.yaml`, and each
// entity, link, condition, content binding, handling part, transform, literal, optional binding,
// ignored column and the row key is set through the controls a person uses. The saved map must equal
// the committed one, not merely contain it.
/** Chapter 4's from-scratch walk up to the map's save: name, source, Preview, the row key, every
 * element and link, the ignored columns. Asserts the saved map is the committed one. */
async function buildTheReportsMap(page: Page) {
  await page.goto(HARNESS);
  await page.getByRole("textbox", { name: "Pipeline name" }).focus();
  await page.keyboard.type("Intelligence reports");
  await press(page, "New pipeline");
  await expect(page.getByRole("button", { name: "Guided" })).toHaveAttribute("aria-pressed", "true");
  await press(page, "Source: New source");
  const chooser = page.getByRole("combobox", { name: "Registered source" });
  await chooser.focus();
  await chooser.selectOption("src-reports");
  await press(page, "Use this source");
  await expect(page.getByRole("status").filter({ hasText: "Reads Intelligence reports file" })).toBeVisible();
  await press(page, "Preview");
  await press(page, "Run preview");
  await expect(drawer(page).getByRole("cell", { name: "Report two" })).toBeVisible();
  // On the draft's own settings: the column carrying each part of the marking (the register wizard
  // declares none), and the row key, what makes a report the same report again.
  await press(page, "Settings");
  await press(page, "The draft's own settings");
  await declareTheMarkingColumns(page);
  for (const part of REPORTS_MAP.deduplicate.key) {
    await page.getByRole("textbox", { name: "Key column name" }).focus();
    await page.keyboard.type(part.field!);
    await page.keyboard.press("Enter");
  }
  await press(page, "Save");
  await expect.poll(async () => (await asked(page)).some((a) => a.method === "PATCH" && a.path.endsWith("/r-new") && a.body!.includes('"deduplicate"'))).toBe(true);
  const patch = (await asked(page)).filter((a) => a.method === "PATCH" && a.path.endsWith("/r-new")).at(-1)!;
  const sent = JSON.parse(patch.body!) as { deduplicate: unknown; handling: { handling_columns?: unknown } };
  expect(sent.deduplicate).toEqual(REPORTS_MAP.deduplicate);
  expect(sent.handling.handling_columns).toEqual(REPORTS_HANDLING_COLUMNS);
  await press(page, "Close the drawer");
  await openTheMapEditor(page);
  await mapTheReports(page);
  await press(page, "Save draft");
  await expect.poll(async () => (await asked(page)).some((a) => a.method === "PUT" && a.path.endsWith("/r-new/row-template"))).toBe(true);
  const put = (await asked(page)).filter((a) => a.method === "PUT" && a.path.endsWith("/r-new/row-template")).at(-1)!;
  const saved = JSON.parse(put.body!) as { row_template: unknown; unmapped_fields: unknown };
  expect(meaning(saved.row_template)).toEqual(meaning(REPORTS_MAP.row_template));
  expect(meaning(saved.unmapped_fields)).toEqual(meaning(REPORTS_MAP.unmapped_fields));
  await expect(page.getByText(/does not bind/)).toHaveCount(0);
}

test("the reports pipeline is built from scratch in guided mode by keyboard, into the committed map", async ({ page }) => {
  test.setTimeout(240_000);
  page.setDefaultTimeout(8_000);
  await buildTheReportsMap(page);
  await page.getByRole("navigation", { name: "Pipeline strip" }).getByRole("button", { name: "Load: Load" }).focus();
  await page.keyboard.press("Enter");
  // The harness refuses as the routes do: the map's save cleared Test's mark, so Deploy is refused
  // until Test runs, and a Preview of Load does not count.
  await press(page, "Preview");
  await press(page, "Run preview");
  await expect(drawer(page).getByText(/^From a sample of/)).toBeVisible();
  await press(page, "Deploy");
  await press(page, "Deploy as v1");
  await expect(page.getByText(/hasn't passed Test since its last edit/)).toBeVisible();
  await press(page, "Test");
  await press(page, "Run the test");
  await expect.poll(async () => (await asked(page)).some((a) => a.method === "POST" && a.path.endsWith("/r-new/verify"))).toBe(true);
  await press(page, "Deploy");
  await press(page, "Deploy as v1");
  await expect(page.getByText("Deployed", { exact: true })).toBeVisible();
  expect((await asked(page)).some((a) => a.method === "POST" && a.path.endsWith("/r-new/publish"))).toBe(true);
  registerCovered(REGISTRY, "build-the-reports-pipeline-from-scratch-in-guided-mode-by-keyboard");
});

// Phase 6's exit, its second half: the reports pipeline, built as above, edited in expert mode. An
// Extract on the report's text is added on the canvas and set; the save carries it, fed by Map, and
// leaves the committed map as it was; Test and Deploy as v1 then take the edited pipeline.
test("the reports pipeline is edited in expert mode by keyboard, and the save carries it", async ({ page }) => {
  test.setTimeout(240_000);
  page.setDefaultTimeout(8_000);
  await buildTheReportsMap(page);
  const templateSaves = (await asked(page)).filter((a) => a.method === "PUT" && a.path.endsWith("/r-new/row-template")).length;
  await page.getByRole("navigation", { name: "Pipeline strip" }).getByRole("button", { name: "Load: Load" }).focus();
  await page.keyboard.press("Enter");
  await press(page, "Close the drawer");
  await press(page, "Expert");
  const canvas = page.getByRole("group", { name: "Pipeline" });
  await expect(canvas).toBeVisible();
  await press(page, "+ Extract");
  await expect(canvas.getByRole("button", { name: "Extract: Extract" })).toBeVisible();
  await canvas.getByRole("button", { name: "Extract: Extract" }).focus();
  await page.keyboard.press("Enter");
  const library = page.getByLabel("Extraction library");
  await library.focus();
  await library.selectOption("spacy");
  await press(page, "Apply extract settings");
  // The save after Apply is the one that carries the setting; an earlier one (the Extract added)
  // does not, so wait for a save holding an extract with any library before reading the last.
  const saves = async () => (await asked(page)).filter((a) => a.method === "PUT" && a.path.endsWith("/r-new/pipeline"));
  await expect.poll(async () => (await saves()).some((a) => /"kind":"extract"[^}]*"library"/.test(a.body ?? ""))).toBe(true);
  const put = (await saves()).at(-1)!;
  const graph = JSON.parse(put.body!) as { nodes: { id: string; kind: string; config?: { library?: string } }[]; edges: { source: string; target: string }[] };
  const extract = graph.nodes.find((n) => n.kind === "extract")!;
  expect(extract.config!.library).toBe("spacy");
  const map = graph.nodes.find((n) => n.kind === "map")!;
  expect(graph.edges).toContainEqual({ source: map.id, target: extract.id });
  // The edit is the pipeline's; the committed map is not saved again.
  expect((await asked(page)).filter((a) => a.method === "PUT" && a.path.endsWith("/r-new/row-template")).length).toBe(templateSaves);
  await press(page, "Deploy");
  await press(page, "Deploy as v1");
  await expect(page.getByText(/hasn't passed Test since its last edit/)).toBeVisible();
  await press(page, "Test");
  await press(page, "Run the test");
  await press(page, "Deploy");
  await press(page, "Deploy as v1");
  await expect(page.getByText("Deployed", { exact: true })).toBeVisible();
  registerCovered(REGISTRY, "edit-the-reports-pipeline-in-expert-mode-by-keyboard");
});

// Rule 15: the harness refuses a Map save that leaves a declared part of the marking unbound, as
// `check_recipe_rules` does, so the case above could not pass with one unbound. A report saved with
// none of the six bound is refused in words naming the part and its column.
test("a reports map leaving a declared part of the marking unbound is refused at save, by keyboard", async ({ page }) => {
  await page.goto(HARNESS);
  await page.getByRole("textbox", { name: "Pipeline name" }).focus();
  await page.keyboard.type("Intelligence reports");
  await press(page, "New pipeline");
  await press(page, "Source: New source");
  const chooser = page.getByRole("combobox", { name: "Registered source" });
  await chooser.focus();
  await chooser.selectOption("src-reports");
  await press(page, "Use this source");
  await press(page, "The draft's own settings");
  await declareTheMarkingColumns(page);
  await press(page, "Save");
  await press(page, "Close the drawer");
  await openTheMapEditor(page);
  await press(page, "+ entity");
  await press(page, "Save draft");
  await expect(page.getByRole("alert").filter({ hasText: /does not bind classification, which the source declares in column 'classification'/ })).toBeVisible();
});

// --- The review of L1.2 (7 November 2026): what the first pass left unproved -------------------

test("an expert step cannot be removed in guided mode: Remove is refused once it is chosen", async ({ page }) => {
  await openVisits(page, "?expert=1");
  const remove = page.getByRole("button", { name: "Remove selected" });
  await press(page, "Load: Load");
  await expect(remove).toBeEnabled();
  await press(page, "SQL transform: Visits per week");
  await expect(remove).toBeDisabled();
  await remove.focus().catch(() => undefined);
  await page.keyboard.press("Enter");
  expect((await asked(page)).filter((a) => a.method === "PUT" && a.path.endsWith("/r-visits/pipeline"))).toHaveLength(0);
  registerCovered(REGISTRY, "an-expert-step-cannot-be-removed-in-guided-mode-by-keyboard");
});

test("the step feeding an expert step cannot be removed in guided mode, so its input edge stays", async ({ page }) => {
  await openVisits(page, "?expert=1");
  const remove = page.getByRole("button", { name: "Remove selected" });
  await press(page, "Load: Load");
  await expect(remove).toBeEnabled();
  // Profile feeds the SQL transform in the harness's pipeline.
  await press(page, "Profile: Profile");
  await expect(remove).toBeDisabled();
  await press(page, "Expert");
  await page.getByRole("group", { name: "Pipeline" }).getByRole("button", { name: "Profile: Profile" }).focus();
  await page.keyboard.press("Enter");
  await expect(remove).toBeEnabled();
  registerCovered(REGISTRY, "the-step-feeding-an-expert-step-cannot-be-removed-in-guided-mode-by-keyboard");
});

test("a step is edited in expert mode from the canvas by keyboard, and the save carries it", async ({ page }) => {
  await openVisits(page);
  await press(page, "Expert");
  await press(page, "+ Extract");
  const canvas = page.getByRole("group", { name: "Pipeline" });
  await expect(canvas.getByRole("button", { name: "Extract: Extract" })).toBeVisible();
  await canvas.getByRole("button", { name: "Extract: Extract" }).focus();
  await page.keyboard.press("Enter");
  const library = page.getByLabel("Extraction library");
  await library.focus();
  await library.selectOption("spacy");
  const apply = page.getByRole("button", { name: "Apply extract settings" });
  await expect(apply).toBeEnabled();
  await apply.focus();
  await page.keyboard.press("Enter");
  await expect.poll(async () => (await asked(page)).filter((a) => a.method === "PUT" && a.path.endsWith("/r-visits/pipeline")).length).toBe(2);
  const puts = (await asked(page)).filter((a) => a.method === "PUT" && a.path.endsWith("/r-visits/pipeline"));
  const nodes = (JSON.parse(puts[1]!.body!) as { nodes: { kind: string; config?: { library?: string } }[] }).nodes;
  expect(nodes.find((n) => n.kind === "extract")!.config!.library).toBe("spacy");
  registerCovered(REGISTRY, "edit-a-step-in-expert-mode-by-keyboard");
});

test("the load rules open from the Load step's drawer by keyboard", async ({ page }) => {
  await openVisits(page);
  await press(page, "Load: Load");
  await press(page, "Open load rules");
  await expect(drawer(page).getByRole("heading", { name: /^Load rules/ })).toBeVisible();
  await expect.poll(async () => (await asked(page)).some((a) => a.method === "GET" && a.path.endsWith("/r-visits/checks"))).toBe(true);
  await expect(page.getByRole("list", { name: "Steps" })).toBeVisible();
  registerCovered(REGISTRY, "open-load-rules-from-the-load-step-by-keyboard");
});

test("a chosen column is let go in the Map editor by keyboard, and no binding then offers it", async ({ page }) => {
  await openVisits(page);
  await openTheMapEditor(page);
  await press(page, "Choose column called");
  await press(page, "Entity 1: visitor (Person)");
  await expect(page.getByRole("button", { name: "Bind called here: name" })).toBeVisible();
  await press(page, "Let go column called");
  await expect(page.getByRole("button", { name: "Choose column called" })).toHaveAttribute("aria-pressed", "false");
  await expect(page.getByRole("button", { name: /^Bind called here/ })).toHaveCount(0);
  registerCovered(REGISTRY, "let-go-a-chosen-column-by-keyboard");
});

test("a step's drawer goes back from Preview to its Settings by keyboard", async ({ page }) => {
  await openVisits(page);
  await press(page, "Load: Load");
  await press(page, "Preview");
  await expect(drawer(page).getByRole("button", { name: "Run preview" })).toBeVisible();
  await press(page, "Settings");
  await expect(drawer(page).getByRole("button", { name: "Settings" })).toHaveAttribute("aria-pressed", "true");
  await expect(drawer(page).getByRole("button", { name: "Open load rules" })).toBeVisible();
  await expect(drawer(page).getByRole("button", { name: "Run preview" })).toHaveCount(0);
  registerCovered(REGISTRY, "go-back-to-a-steps-settings-from-preview-by-keyboard");
});

// The review's first must-fix: a Map Preview must not count as Test. Edit the draft (the edit clears
// Test's mark, as the real store does), preview Map, and Deploy is refused until Test itself runs.
test("a Map Preview does not count as Test: Deploy is refused until Test runs", async ({ page }) => {
  await openVisits(page);
  await press(page, "+ Extract");
  await expect.poll(async () => (await asked(page)).some((a) => a.method === "PUT" && a.path.endsWith("/r-visits/pipeline"))).toBe(true);
  await press(page, "Map: Map");
  await press(page, "Preview");
  await press(page, "Run preview");
  await expect(drawer(page).getByText(/^From a sample of 3 rows/)).toBeVisible();
  expect((await asked(page)).some((a) => a.path.endsWith("/r-visits/verify"))).toBe(false);
  await press(page, "Deploy");
  await press(page, "Deploy as v3");
  await expect(page.getByText("This draft hasn't passed Test since its last edit — run Test again before deploying.")).toBeVisible();
  await press(page, "Test");
  await press(page, "Run the test");
  await expect.poll(async () => (await asked(page)).some((a) => a.method === "POST" && a.path.endsWith("/r-visits/verify"))).toBe(true);
  await press(page, "Deploy");
  await press(page, "Deploy as v3");
  await expect(page.getByText("Deployed", { exact: true })).toBeVisible();
});

test("a graph Preview is refused in words to a person without the right to test", async ({ page }) => {
  await openVisits(page, "?rights=no-test");
  await press(page, "Map: Map");
  await press(page, "Preview");
  await press(page, "Run preview");
  await expect(drawer(page).getByRole("alert")).toContainText("needs the right to test pipelines");
});

// The harness refuses as the routes do (rule 15): the save gate's words, and Deploy without the
// approver's role, each shown to the person.
test("removing the Load step is refused by the save gate in its own words", async ({ page }) => {
  await openVisits(page);
  await press(page, "Load: Load");
  await press(page, "Remove selected");
  await expect(page.getByRole("alert")).toContainText("source 'Call log' reaches no load; its rows would go nowhere");
});

test("Deploy is refused in words to a person without the source approver's role", async ({ page }) => {
  await openVisits(page, "?rights=no-approve");
  await press(page, "Deploy");
  await press(page, "Deploy as v3");
  await expect(page.getByText(/source_approver|studio role/)).toBeVisible();
  expect((await asked(page)).some((a) => a.method === "POST" && a.path.endsWith("/r-visits/publish"))).toBe(true);
  await expect(page.getByText("Deployed", { exact: true })).toHaveCount(0);
});

// --- Phase 7b (ADR-140 Amendment 12): a drawer per staging step, each with a live sample and the save
// gate's refusals in its words; then phase 7's exit, "Visits and contacts" without its expert steps,
// built by keys. The harness's `?contacts=1` draft holds two sources and Map, and its fake refuses what
// `studio_staging.staging_gate` refuses, in the same words (`stagingHarness.ts`).

async function openContacts(page: Page) {
  await page.goto(`${HARNESS}?contacts=1`);
  await press(page, "Open Visits and contacts");
  await expect(page.getByRole("list", { name: "Steps" })).toBeVisible();
}

async function typeInto(page: Page, label: string, value: string) {
  // A column field offers the sample's columns as suggestions (a `list`), which makes it a combobox.
  const box = drawer(page).getByLabel(label, { exact: true });
  await box.focus();
  await page.keyboard.press("ControlOrMeta+A");
  await page.keyboard.press("Backspace");
  await page.keyboard.type(value);
}

async function chooseIn(page: Page, label: string, value: string) {
  const select = drawer(page).getByRole("combobox", { name: label, exact: true });
  await select.focus();
  await select.selectOption(value);
}

/** *Apply step settings* is disabled while the pipeline's last save is answered (shown so), so a
 * person waits for it, as this does, before pressing it. */
async function applyStep(page: Page) {
  await expect(drawer(page).getByRole("button", { name: "Apply step settings" })).toBeEnabled();
  await press(page, "Apply step settings");
}

async function addStep(page: Page, kind: string) {
  await choose(page, "Staging step to add", kind);
  await press(page, "+ Step");
}

const pipelineSaves = async (page: Page) =>
  (await asked(page)).filter((a) => a.method === "PUT" && a.path.endsWith("/r-contacts/pipeline"));
type Saved = { nodes: { id: string; kind: string; label: string; config?: Record<string, unknown> }[]; edges: { source: string; target: string }[] };
const lastSaved = async (page: Page): Promise<Saved> => JSON.parse((await pipelineSaves(page)).at(-1)!.body!) as Saved;

/** The exit's three steps, set in their drawers by keys: a Lookup of the establishment, a left Join
 * of each number's owner on E.164, and a Derive of the booking's title. */
async function buildTheContactsSteps(page: Page) {
  await openContacts(page);
  await press(page, "Source: Visit bookings");
  await addStep(page, "lookup");
  await expect(drawer(page).getByRole("heading", { name: "Lookup: Lookup" })).toBeVisible();
  await typeInto(page, "Step name", "establishment");
  await typeInto(page, "Reference list", "establishments");
  await typeInto(page, "Match on column", "estab_id");
  await press(page, "+ Column to bring across");
  await typeInto(page, "Column 1", "name");
  await typeInto(page, "Name it (optional) 1", "establishment");
  await applyStep(page);
  await expect(drawer(page).getByRole("status").filter({ hasText: "6 rows out, from 10 source rows read." })).toBeVisible();
  await addStep(page, "join");
  await typeInto(page, "Step name", "owner of contact");
  await chooseIn(page, "Right table", "number_owners");
  await typeInto(page, "Left key column", "contact_number");
  await typeInto(page, "Right key column", "number");
  await typeInto(page, "Normalise both keys with (optional)", "msisdn");
  await chooseIn(page, "Keep", "left");
  await press(page, "+ Column to bring across");
  await typeInto(page, "Column 1", "owner_family_name");
  await applyStep(page);
  await expect(drawer(page).getByRole("list", { name: "Rows refused" })).toContainText("staging step join (right side, number_owners row 3)");
  await addStep(page, "derive");
  await typeInto(page, "Step name", "the booking's title");
  await typeInto(page, "New column", "title");
  for (const [n, column] of [[1, "establishment"], [2, "visit_at"]] as const) {
    await press(page, "+ Column it reads");
    await typeInto(page, `Column it reads ${n}`, column);
  }
  await typeInto(page, "Separator", " · ");
  await applyStep(page);
  await expect(drawer(page).getByRole("cell", { name: "HMP Fenwick Moor · Tue 4 Nov 14:00" })).toBeVisible();
  // The saved steps are the exit recipe's, under the ids the Studio gave them.
  const ids: Record<string, string> = { with_establishment: "lookup", with_owner: "join", titled: "derive" };
  const rename = (v: unknown): unknown => (typeof v === "string" ? (ids[v] ?? v) : Array.isArray(v) ? v.map(rename) : v);
  const expected = CONTACTS.pipeline.nodes
    .filter((n) => n.id in ids)
    .map((n) => ({ id: ids[n.id], kind: n.kind, config: Object.fromEntries(Object.entries(n.config).map(([k, v]) => [k, rename(v)])) }));
  await expect.poll(async () => {
    const saved = await lastSaved(page);
    return saved.nodes.filter((n) => Object.values(ids).includes(n.id)).map((n) => ({ id: n.id, kind: n.kind, config: n.config }));
  }).toEqual(expected);
  const saved = await lastSaved(page);
  expect(saved.edges).toContainEqual({ source: "derive", target: "map" });
  expect(saved.edges).not.toContainEqual({ source: "visit_bookings", target: "map" });
}

test("a staging step is added beside the pipeline and opens its drawer, by keyboard", async ({ page }) => {
  await openContacts(page);
  await press(page, "Source: Visit bookings");
  await addStep(page, "dedupe");
  await expect(drawer(page).getByRole("heading", { name: "Dedupe: Dedupe" })).toBeVisible();
  await expect(page.getByRole("list", { name: "Steps" }).getByRole("button", { name: "Dedupe: Dedupe" })).toBeVisible();
  // Saved as a node of the pipeline, reading the source chosen, and refused until it is set.
  await expect.poll(async () => (await pipelineSaves(page)).length).toBeGreaterThan(0);
  await expect(page.getByRole("alert").first()).toContainText("step 'dedupe' needs at least 1 in 'on'");
  registerCovered(REGISTRY, "add-a-staging-step-by-keyboard");
});

test("the Visits and contacts steps are set in their drawers by keyboard, each with its sample", async ({ page }) => {
  test.setTimeout(120_000);
  await buildTheContactsSteps(page);
  registerCovered(REGISTRY, "set-a-lookup-in-its-drawer-by-keyboard");
  registerCovered(REGISTRY, "set-a-join-in-its-drawer-by-keyboard");
  registerCovered(REGISTRY, "set-a-derive-in-its-drawer-by-keyboard");
});

test("a filter is set in its drawer by keyboard, a condition added and removed", async ({ page }) => {
  await openContacts(page);
  await press(page, "Source: Visit bookings");
  await addStep(page, "filter");
  await press(page, "+ Condition");
  await press(page, "+ Condition");
  await press(page, "Remove condition 2");
  await expect(drawer(page).getByLabel("Column 2", { exact: true })).toHaveCount(0);
  await typeInto(page, "Column 1", "estab_id");
  await chooseIn(page, "Test 1", "in");
  await typeInto(page, "Value 1", "FMR|HBK");
  await applyStep(page);
  await expect(drawer(page).getByRole("list", { name: "Each step's counts" })).toContainText("filter: 6 in, 5 out, 1 left out");
  const filter = (await lastSaved(page)).nodes.find((n) => n.id === "filter")!;
  expect(filter.config).toEqual({ input: "visit_bookings", keep: [{ field: "estab_id", in: ["FMR", "HBK"] }] });
  registerCovered(REGISTRY, "set-a-filter-in-its-drawer-by-keyboard");
  registerCovered(REGISTRY, "add-and-remove-a-row-in-a-steps-drawer-by-keyboard");
});

test("a union and a dedupe are set in their drawers by keyboard", async ({ page }) => {
  await openContacts(page);
  await press(page, "Source: Visit bookings");
  await addStep(page, "dedupe");
  await press(page, "+ Same row when this column matches");
  await typeInto(page, "Same row when this column matches 1", "contact_number");
  await applyStep(page);
  await expect(drawer(page).getByRole("list", { name: "Each step's counts" })).toContainText("dedupe: 6 in, 5 out, 1 repeats folded");
  await addStep(page, "union");
  const box = drawer(page).getByRole("checkbox", { name: "visit_bookings", exact: true });
  await box.focus();
  await page.keyboard.press("Space");
  await applyStep(page);
  const union = (await lastSaved(page)).nodes.find((n) => n.id === "union")!;
  expect(union.config).toEqual({ inputs: ["dedupe", "visit_bookings"] });
  registerCovered(REGISTRY, "set-a-dedupe-in-its-drawer-by-keyboard");
  registerCovered(REGISTRY, "set-a-union-in-its-drawer-by-keyboard");
});

test("a step's sample is read again, and its Preview shows the sample alone, by keyboard", async ({ page }) => {
  test.setTimeout(120_000);
  await buildTheContactsSteps(page);
  const previews = async () => (await asked(page)).filter((a) => a.method === "POST" && a.path.endsWith("/r-contacts/staging-preview")).length;
  const before = await previews();
  await press(page, "Read the sample again");
  await expect.poll(previews).toBe(before + 1);
  registerCovered(REGISTRY, "read-a-steps-sample-again-by-keyboard");
  await press(page, "Preview");
  await expect(drawer(page).getByRole("region", { name: "Sample of this step" })).toBeVisible();
  await expect(drawer(page).getByRole("button", { name: "Apply step settings" })).toHaveCount(0);
  registerCovered(REGISTRY, "preview-a-staging-step-by-keyboard");
});

test("a drawer refuses what the save gate refuses, in the same words, by keyboard", async ({ page }) => {
  test.setTimeout(120_000);
  await buildTheContactsSteps(page);
  await press(page, "Join: owner of contact");
  await typeInto(page, "Normalise both keys with (optional)", "no_such_adapter");
  await applyStep(page);
  const words = "step 'join' normalises its key with 'no_such_adapter', which is not a Knowledge Adapter that reads one column into one value of text";
  await expect(page.getByRole("alert").filter({ hasText: words }).first()).toBeVisible();
  await expect(drawer(page).getByRole("alert", { name: "What the save gate refuses" })).toContainText(words);
  registerCovered(REGISTRY, "a-drawer-refuses-what-the-save-gate-refuses-by-keyboard");
});

test("a staging step is removed by keyboard, and Map reads the step before it", async ({ page }) => {
  test.setTimeout(120_000);
  await buildTheContactsSteps(page);
  await press(page, "Derive: the booking's title");
  await press(page, "Remove selected");
  await expect.poll(async () => (await lastSaved(page)).edges).toContainEqual({ source: "join", target: "map" });
  expect((await lastSaved(page)).nodes.some((n) => n.id === "derive")).toBe(false);
  registerCovered(REGISTRY, "remove-a-staging-step-by-keyboard");
});

// Phase 7's exit (the build plan's phase 7; ADR-140 Amendment 12): "Visits and contacts" without its
// two expert steps, built by keys alone: its three steps in their drawers, then the Map over the last
// step's table, into exactly the exit recipe's map, then Test and Deploy. The run on the synthetic
// data, every created element traceable to its source rows, is `tests/ingest/test_phase7_exit.py` over
// this same pipeline, and the live walk under a lease.
test("phase 7's exit: Visits and contacts is built by keys, mapped over its staged table, tested and deployed", async ({ page }) => {
  test.setTimeout(240_000);
  // A long walk: under a loaded machine an action's own wait needs more than the default.
  page.setDefaultTimeout(15_000);
  await buildTheContactsSteps(page);
  await press(page, "Close the drawer");
  await openTheMapEditor(page);
  await expect(page.getByText("From the staged table derive: the steps over the first ten rows of each source.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Choose column title", exact: true })).toBeVisible();
  const template = CONTACTS.row_template as { entities: MapEntity[]; edges: MapEdge[] };
  for (const [i, entity] of template.entities.entries()) await buildEntity(page, entity, i + 1);
  for (const edge of template.edges) await buildLink(page, edge);
  for (const ignored of CONTACTS.unmapped_fields) {
    await page.getByRole("textbox", { name: `Note for ignoring ${ignored.field}` }).focus();
    await page.keyboard.type(ignored.note ?? "");
    await press(page, `Ignore ${ignored.field}`);
  }
  await press(page, "Save draft");
  await expect.poll(async () => (await asked(page)).some((a) => a.method === "PUT" && a.path.endsWith("/r-contacts/row-template"))).toBe(true);
  const put = (await asked(page)).filter((a) => a.method === "PUT" && a.path.endsWith("/r-contacts/row-template")).at(-1)!;
  const saved = JSON.parse(put.body!) as { row_template: unknown; unmapped_fields: unknown };
  expect(meaning(saved.row_template)).toEqual(meaning(CONTACTS.row_template));
  expect(meaning(saved.unmapped_fields)).toEqual(meaning(CONTACTS.unmapped_fields));
  await page.getByRole("navigation", { name: "Pipeline strip" }).getByRole("button", { name: "Load: Load" }).focus();
  await page.keyboard.press("Enter");
  await press(page, "Test");
  await press(page, "Run the test");
  await expect.poll(async () => (await asked(page)).some((a) => a.method === "POST" && a.path.endsWith("/r-contacts/verify"))).toBe(true);
  await press(page, "Deploy");
  await press(page, "Deploy as v1");
  await expect(page.getByText("Deployed", { exact: true })).toBeVisible();
  registerCovered(REGISTRY, "build-visits-and-contacts-by-keys-for-phase-7s-exit");
});

test("every registered Ingest Studio action has its own proving test case above", () => {
  assertAllCovered("INGEST_STUDIO_ACTIONS", INGEST_STUDIO_ACTIONS);
});
