// A keyboard-only walkthrough of the Ingest Studio's four places (ADR-140 decision 1, redesign phase
// 2; `CLAUDE.md` rule 13): the tabs, the dataset switcher, the Runs tab's grid, held rows and Run now,
// Sources' Add files, and Deploy as vN with Deploy and run now — no `page.mouse`, no `.click()`. The
// harness serves itself and records every request, so each case proves its action reached its route.
import { expect, test, type Page } from "@playwright/test";

import { INGEST_STUDIO_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

const REGISTRY = "INGEST_STUDIO_ACTIONS";
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

test("every registered Ingest Studio action has its own proving test case above", () => {
  assertAllCovered("INGEST_STUDIO_ACTIONS", INGEST_STUDIO_ACTIONS);
});
