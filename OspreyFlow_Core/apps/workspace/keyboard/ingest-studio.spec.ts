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

function asked(page: Page): Promise<{ method: string; path: string }[]> {
  return page.evaluate(() => (window as unknown as { __asked: { method: string; path: string }[] }).__asked);
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

test("Add files opens on Sources by keyboard", async ({ page }) => {
  await page.goto(HARNESS);
  await tab(page, "2 Sources");
  await press(page, "Add files");
  await expect(page.getByRole("region", { name: "Add files" })).toBeVisible();
  registerCovered(REGISTRY, "add-files-from-sources-by-keyboard");
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
