// A keyboard-only walkthrough of Home (ADR-114 Amendment 5 point 9, ADR-115 E3, `CLAUDE.md` rule 13):
// each place's button and its key, the guide under each card (ADR-145 Amendment 10), and the mark back to
// Home from a case's workspace and from the Admin area — no `page.mouse`, no `.click()`.
import { expect, test, type Page } from "@playwright/test";

import { START_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

const REGISTRY = "START_ACTIONS";
const CASES = [{ id: "c1", name: "Operation Ledger (synthetic demo)", level: "author", created_at: "2026-10-01T09:00:00Z", created_by: "a" }];

// A guide's PDF as the Conduit answers it (synthetic, a few bytes), and the administration guide refused in
// the Conduit's words when `refuseAdministration` is set.
const GUIDE_PDF = "%PDF-1.4\n% synthetic keyboard fixture\n%%EOF\n";
const ADMINISTRATION_REFUSED =
  "The administration guide opens with Admin, which your roles do not open. Ask an administrator for a role that opens Admin.";

async function serve(page: Page, options: { refuseAdministration?: boolean } = {}): Promise<string[]> {
  const asked: string[] = [];
  await page.route("**/*/v1/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    asked.push(path);
    const json = (body: unknown) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    const guide = /^\/v1\/guides\/(user|developer|administration)$/.exec(path)?.[1];
    if (guide) {
      // The token in a header, never in the URL (ADR-145 Amendment 10).
      asked.push(`${guide}: ${route.request().headers()["authorization"] ?? "no token"}${url.search}`);
      if (guide === "administration" && options.refuseAdministration) {
        return route.fulfill({ status: 403, contentType: "application/json",
                               body: JSON.stringify({ detail: { error: "place_required", place: "admin", message: ADMINISTRATION_REFUSED } }) }); // prettier-ignore
      }
      return route.fulfill({ status: 200, contentType: "application/pdf", body: GUIDE_PDF });
    }
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
  await press(page, /^Open The Glass/);
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
  await press(page, /^Open Admin/);
  await expect(page.getByRole("navigation", { name: "Admin sections" }).getByRole("button", { name: "People and roles" })).toBeVisible();
  await expect.poll(() => asked).toContain("/v1/admin/people");
  expect(await opened(page)).toBeNull();
  registerCovered(REGISTRY, "choose-admin-from-start-by-keyboard");
  await press(page, "Osprey, go to Home");
  await expect(page.getByRole("heading", { level: 1, name: /^Good (morning|afternoon|evening)/ })).toBeVisible();
});

test("the mark returns to Start from a case's workspace by keyboard", async ({ page }) => {
  await serve(page);
  await page.goto("/keyboard/start-harness.html?case=c1");
  await expect(page.getByText("Workspace on c1, graph")).toBeVisible();
  await press(page, "Osprey, go to Home");
  await expect(page.getByRole("heading", { level: 1, name: /^Good (morning|afternoon|evening)/ })).toBeVisible();
  await press(page, /^Open Ingest Studio/);
  await expect(page.getByText("Workspace on c1, ingest")).toBeVisible();
  registerCovered(REGISTRY, "return-to-start-from-the-mark-by-keyboard");
});

test("a place opens with its key from anywhere on Home, and one the rights do not open does not", async ({ page }) => {
  await serve(page);
  await page.goto("/keyboard/start-harness.html?rights=investigate,manage_people");
  // ADR-145 N6: no card for the Studio at all.
  await expect(page.getByRole("region", { name: "Ingest Studio" })).toHaveCount(0);
  await page.keyboard.press("i");
  await expect(page.getByRole("heading", { level: 1, name: /^Good/ })).toBeVisible();
  await page.keyboard.press("a");
  await expect(page.getByRole("navigation", { name: "Admin sections" }).getByRole("button", { name: "People and roles" })).toBeVisible();
  await press(page, "Osprey, go to Home");
  await page.keyboard.press("g");
  await expect(page.getByRole("heading", { name: "Choose a case" })).toBeVisible();
  registerCovered(REGISTRY, "open-a-place-from-home-with-its-key");
});

test("each card's guide is reached and opened in a new tab by keyboard, with the token in a header", async ({ page }) => {
  const asked = await serve(page);
  await page.goto("/keyboard/start-harness.html");
  await expect(page.getByRole("heading", { level: 1, name: /^Good (morning|afternoon|evening)/ })).toBeVisible();
  for (const [card, words, guide] of [
    ["The Glass", "Read the user guide (PDF)", "user"],
    ["Ingest Studio", "Read the developer guide (PDF)", "developer"],
    ["Admin", "Read the administration guide (PDF)", "administration"],
  ] as const) {
    const link = page.getByRole("region", { name: card }).getByRole("button", { name: words, exact: true });
    // Reached by Tab from the card's own words, the way a keyboard user reads down the card.
    await link.focus();
    await page.keyboard.press("Shift+Tab");
    await page.keyboard.press("Tab");
    await expect(link).toBeFocused();
    const opened = page.waitForEvent("popup");
    await page.keyboard.press("Enter");
    const tab = await opened;
    await expect.poll(() => tab.url()).toMatch(/^blob:/);
    expect(asked).toContain(`${guide}: Bearer unused`);
    await tab.close();
    // Activating the link opens the guide and leaves Home where it was.
    await expect(page.getByRole("heading", { level: 1, name: /^Good/ })).toBeVisible();
  }
  // Rules and Monitoring has no guide; the architecture guide is linked nowhere.
  expect(asked.filter((a) => a.startsWith("/v1/guides/"))).toEqual(["/v1/guides/user", "/v1/guides/developer", "/v1/guides/administration"]);
  registerCovered(REGISTRY, "read-a-place-s-guide-from-home-by-keyboard");
});

test("a guide the Conduit refuses is said in words under its link, and no tab is left open, by keyboard", async ({ page, context }) => {
  await serve(page, { refuseAdministration: true });
  await page.goto("/keyboard/start-harness.html");
  const link = page.getByRole("region", { name: "Admin" }).getByRole("button", { name: "Read the administration guide (PDF)" });
  await link.focus();
  const opened = page.waitForEvent("popup");
  await page.keyboard.press("Enter");
  const tab = await opened;
  await expect(page.getByRole("region", { name: "Admin" }).getByText(ADMINISTRATION_REFUSED)).toBeVisible();
  await expect.poll(() => tab.isClosed()).toBe(true);
  expect(context.pages()).toHaveLength(1);
  await expect(link).toBeFocused();
  registerCovered(REGISTRY, "read-why-a-guide-was-refused-on-home-by-keyboard");
});

test("a person whose rights open no card is linked no guide", async ({ page }) => {
  await serve(page);
  await page.goto("/keyboard/start-harness.html?rights=run_pipelines");
  await expect(page.getByText("Your account opens no place yet.", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: /guide \(PDF\)$/ })).toHaveCount(0);
});

test("every registered Start action has its own proving test case above", () => {
  assertAllCovered("START_ACTIONS", START_ACTIONS);
});
