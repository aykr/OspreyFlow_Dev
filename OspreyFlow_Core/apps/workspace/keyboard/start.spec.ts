// A keyboard-only walkthrough of Home (ADR-114 Amendment 5 point 9, ADR-115 E3, `CLAUDE.md` rule 13):
// each place's button and its key, and the mark back to Home from a case's workspace and from the
// Admin area — no `page.mouse`, no `.click()`.
import { expect, test, type Page } from "@playwright/test";

import { START_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

const REGISTRY = "START_ACTIONS";
const CASES = [{ id: "c1", name: "Operation Ledger (synthetic demo)", level: "author", created_at: "2026-10-01T09:00:00Z", created_by: "a" }];

async function serve(page: Page): Promise<string[]> {
  const asked: string[] = [];
  await page.route("**/*/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    asked.push(path);
    const json = (body: unknown) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    if (path === "/v1/investigations") return json(CASES);
    if (path === "/v1/admin/people") return json([]);
    if (path === "/v1/handling-scheme") return json({ classification: ["OFFICIAL"], handling_codes: {} });
    return route.fulfill({ status: 404, body: "{}" });
  });
  return asked;
}

async function press(page: Page, name: string | RegExp) {
  await page.getByRole("button", { name, exact: typeof name === "string" }).focus();
  await page.keyboard.press("Enter");
}

const opened = (page: Page) => page.evaluate(() => window.__START__?.opened);

test("the Glass is chosen from Start, then a case, by keyboard", async ({ page }) => {
  await serve(page);
  await page.goto("/keyboard/start-harness.html");
  await expect(page.getByRole("heading", { level: 1, name: /^Good (morning|afternoon|evening)/ })).toBeVisible();
  await press(page, /^Open Glass/);
  await expect(page.getByRole("heading", { name: "Choose a case" })).toBeVisible();
  await press(page, "Operation Ledger (synthetic demo)");
  await expect.poll(() => opened(page)).toEqual({ id: "c1" });
  await expect(page.getByText("Workspace on c1, graph")).toBeVisible();
  registerCovered(REGISTRY, "choose-the-glass-from-start-by-keyboard");
});

test("the Ingest Studio is chosen from Start, then the case to load into, by keyboard", async ({ page }) => {
  await serve(page);
  await page.goto("/keyboard/start-harness.html");
  await press(page, /^Open Ingest Studio/);
  await expect(page.getByRole("heading", { name: "Choose the case to load into" })).toBeVisible();
  await press(page, "Operation Ledger (synthetic demo)");
  await expect.poll(() => opened(page)).toEqual({ id: "c1", view: "ingest" });
  await expect(page.getByText("Workspace on c1, ingest")).toBeVisible();
  registerCovered(REGISTRY, "choose-the-ingest-studio-from-start-by-keyboard");
});

test("Admin is chosen from Start with no case, and Start is back by keyboard", async ({ page }) => {
  const asked = await serve(page);
  await page.goto("/keyboard/start-harness.html");
  await press(page, /^Open Admin area/);
  await expect(page.getByRole("tab", { name: "People and roles" })).toBeVisible();
  await expect.poll(() => asked).toContain("/v1/admin/people");
  expect(await opened(page)).toBeNull();
  registerCovered(REGISTRY, "choose-admin-from-start-by-keyboard");
  await press(page, "OspreyFlow, go to Home");
  await expect(page.getByRole("heading", { level: 1, name: /^Good (morning|afternoon|evening)/ })).toBeVisible();
});

test("the mark returns to Start from a case's workspace by keyboard", async ({ page }) => {
  await serve(page);
  await page.goto("/keyboard/start-harness.html?case=c1");
  await expect(page.getByText("Workspace on c1, graph")).toBeVisible();
  await press(page, "OspreyFlow, go to Home");
  await expect(page.getByRole("heading", { level: 1, name: /^Good (morning|afternoon|evening)/ })).toBeVisible();
  await press(page, /^Open Ingest Studio/);
  await expect(page.getByText("Workspace on c1, ingest")).toBeVisible();
  registerCovered(REGISTRY, "return-to-start-from-the-mark-by-keyboard");
});

test("a usable place opens with its key from anywhere on Home, and a gated one does not", async ({ page }) => {
  await serve(page);
  await page.goto("/keyboard/start-harness.html?rights=investigate,manage_people");
  await expect(page.getByText("You need the Data Engineer role for this. Ask an administrator to add it.")).toBeVisible();
  await page.keyboard.press("i");
  await expect(page.getByRole("heading", { level: 1, name: /^Good/ })).toBeVisible();
  await page.keyboard.press("a");
  await expect(page.getByRole("tab", { name: "People and roles" })).toBeVisible();
  await press(page, "OspreyFlow, go to Home");
  await page.keyboard.press("g");
  await expect(page.getByRole("heading", { name: "Choose a case" })).toBeVisible();
  registerCovered(REGISTRY, "open-a-place-from-home-with-its-key");
});

test("every registered Start action has its own proving test case above", () => {
  assertAllCovered("START_ACTIONS", START_ACTIONS);
});
