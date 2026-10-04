// A scripted, keyboard-only walkthrough of the Inspector's *Change this link* form (ADR-080, rule
// 13). It never calls `page.mouse` or `.click()`. The change route is intercepted at the transport
// so the request that went out can be read back; a save needs a reason, and the old link is kept by
// the server, which is why nothing here edits the link in the page.
import { expect, test, type Page } from "@playwright/test";

import { LINK_CHANGE_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

declare global {
  interface Window {
    __CHANGED__?: { change: { reason: string } } | null;
  }
}

const REGISTRY = "LINK_CHANGE_ACTIONS";

async function serve(page: Page) {
  const requests: { url: string; body: Record<string, unknown> }[] = [];
  await page.route("**/*/v1/investigations/inv-1/links/e1/change", async (route) => {
    const body = route.request().postDataJSON() as Record<string, unknown>;
    requests.push({ url: route.request().url(), body });
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        edge: { id: "e2", type: body.type ?? "ASSOCIATE_OF", source: "a", target: "b" },
        delta: { seq: 2, op: "replace_edge", old_edge_id: "e1" },
        change: { id: "c1", reason: body.reason },
      }),
    });
  });
  return requests;
}

async function focusedName(page: Page): Promise<string> {
  return page.evaluate(
    () => document.activeElement?.getAttribute("aria-label") ?? document.activeElement?.textContent ?? "",
  );
}

async function tabTo(page: Page, name: RegExp | string, max = 12) {
  const matches = (text: string) => (typeof name === "string" ? text.trim() === name : name.test(text));
  for (let i = 0; i < max; i++) {
    const label = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null;
      const labelled = el?.closest("label")?.textContent;
      return el?.getAttribute("aria-label") ?? labelled ?? el?.textContent ?? "";
    });
    if (matches(label)) return;
    await page.keyboard.press("Tab");
  }
  throw new Error(`Tab never reached "${String(name)}" (stopped on "${await focusedName(page)}")`);
}

/** Picks COLLEAGUE_OF on the focused type box by typing its first letter. A closed `<select>` takes
 * an arrow key differently by platform (on macOS it opens the menu instead of moving the choice,
 * which is why ArrowDown worked on the Linux build machines and not on the owner's Mac); typing a
 * letter selects the first matching option everywhere. */
async function chooseColleagueOf(page: Page) {
  await expect(page.getByLabel("Link type")).toBeFocused();
  await page.keyboard.type("C");
  await expect(page.getByLabel("Link type")).toHaveValue("COLLEAGUE_OF");
}

async function openByKeyboard(page: Page) {
  await page.goto("/keyboard/link-change-harness.html");
  await expect(page.getByRole("button", { name: "Change this link…" })).toBeVisible();
  await page.keyboard.press("Tab"); // the only control: Change this link…
  expect((await focusedName(page)).trim()).toBe("Change this link…");
  await page.keyboard.press("Enter");
  await expect(page.getByLabel("Link type")).toBeFocused();
}

test("Enter on Change this link… opens the form with focus on the link type", async ({ page }) => {
  await serve(page);
  await openByKeyboard(page);
  await expect(page.getByLabel(/Why is it being changed/)).toBeVisible();
  registerCovered(REGISTRY, "enter-on-change-this-link-opens-the-form-at-the-type");
});

test("Changing the type and pressing Ctrl+Enter in the reason box saves, with the reason", async ({ page }) => {
  const requests = await serve(page);
  await openByKeyboard(page);
  await chooseColleagueOf(page);
  await expect(page.getByLabel("Link type")).toHaveValue("COLLEAGUE_OF");
  // What stands behind it is asked each time, with no default (ADR-081): Direct, as it was.
  await tabTo(page, /^Direct/); // the radio's label carries a hint after the word
  await page.keyboard.press("Space");
  await tabTo(page, /Why is it being changed/);
  await page.keyboard.type("Both are named on the staff list for the same site.");
  await page.keyboard.press("Control+Enter");

  await expect.poll(() => requests.length).toBe(1);
  expect(requests[0]!.url).toMatch(/\/links\/e1\/change$/);
  expect(requests[0]!.body).toEqual({
    reason: "Both are named on the staff list for the same site.",
    type: "COLLEAGUE_OF",
    // A new type starts without the old type's properties, which is sent so they are cleared.
    properties: {},
  });
  await expect(page.getByText(/Link changed/)).toBeVisible();
  await expect.poll(() => page.evaluate(() => window.__CHANGED__?.change.reason)).toBe(
    "Both are named on the staff list for the same site.",
  );
  registerCovered(REGISTRY, "change-the-type-and-save-with-ctrl-enter");
});

test("Without a reason Save change is off and Ctrl+Enter sends nothing", async ({ page }) => {
  const requests = await serve(page);
  await openByKeyboard(page);
  await chooseColleagueOf(page);
  await expect(page.getByRole("button", { name: "Save change" })).toBeDisabled();
  await tabTo(page, /Why is it being changed/);
  await page.keyboard.press("Control+Enter");
  await page.keyboard.type("   "); // spaces are not a reason
  await page.keyboard.press("Control+Enter");
  await page.waitForTimeout(300);
  expect(requests).toHaveLength(0);
  await expect(page.getByRole("button", { name: "Save change" })).toBeDisabled();
  registerCovered(REGISTRY, "save-needs-a-reason");
});

test("Escape closes the form, changes nothing and leaves the link as it was", async ({ page }) => {
  const requests = await serve(page);
  await openByKeyboard(page);
  await chooseColleagueOf(page);
  await tabTo(page, /Why is it being changed/);
  await page.keyboard.type("Typed, then thought better of it.");
  await page.keyboard.press("Escape");
  await expect(page.getByLabel("Link type")).toHaveCount(0);
  expect(requests).toHaveLength(0);
  // Reopened, it starts again from the link as it is.
  await page.getByRole("button", { name: "Change this link…" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByLabel("Link type")).toHaveValue("ASSOCIATE_OF");
  await expect(page.getByLabel(/Why is it being changed/)).toHaveValue("");
  registerCovered(REGISTRY, "escape-closes-the-form-and-changes-nothing");
});

test("Opened by the link menu's Change link…, focus is already on the link type", async ({ page }) => {
  await serve(page);
  await page.goto("/keyboard/link-change-harness.html?signal=1");
  await expect(page.getByLabel("Link type")).toBeFocused();
  registerCovered(REGISTRY, "opened-by-the-link-menu-lands-on-the-type");
});

test("Saving asks what stands behind the link; choosing Probabilistic by keyboard sends the mark", async ({ page }) => {
  const requests = await serve(page);
  await openByKeyboard(page);
  await tabTo(page, /Why is it being changed/);
  await page.keyboard.type("The pairing is inferred from timing, not from a record.");
  await page.keyboard.press("Control+Enter");
  await expect(page.getByRole("alert")).toHaveText(/stands behind/i);
  expect(requests).toHaveLength(0);
  await page.getByLabel("Probabilistic").focus();
  await page.keyboard.press("Space");
  await expect(page.getByLabel("Probabilistic")).toBeChecked();
  await page.getByLabel(/Why is it being changed/).focus();
  await page.keyboard.press("Control+Enter");
  await expect.poll(() => requests.length).toBe(1);
  expect(requests[0]!.body).toEqual({
    reason: "The pairing is inferred from timing, not from a record.",
    basis: "probabilistic",
  });
  registerCovered(REGISTRY, "choose-what-stands-behind-the-link-before-saving");
});

test("every registered link-change action has its own proving test case above", () => {
  assertAllCovered("LINK_CHANGE_ACTIONS", LINK_CHANGE_ACTIONS);
});
