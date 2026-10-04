// The Inspector's Emails section (ADR-089), reached with the keyboard alone (rule 13): the list,
// Show more, opening an email and going back. No `page.mouse`, no `.click()`.
import { expect, test, type Page } from "@playwright/test";

import { LINK_EVENTS_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

const REGISTRY = "LINK_EVENTS_ACTIONS";

function event(i: number, truncated = false) {
  return {
    event_id: `ev-${i}`,
    edge_id: "e1",
    edge_type: "COMMUNICATED_WITH",
    source_id: "a",
    target_id: "b",
    occurred_at: `2001-05-${String(10 + i).padStart(2, "0")}T10:00:00Z`,
    direction: "outbound",
    properties: { subject: `Subject ${i}`, excerpt: `Body of email ${i}`, truncated },
    investigation_scope: "inv-1",
    handling: { classification: "OFFICIAL", handling_code: "P", originator: "unit-1", owning_unit: "unit-1" },
  };
}

async function serve(page: Page) {
  const all = [event(3, true), event(2), event(1)];
  await page.route("**/*/v1/investigations/inv-1/links/e1/events**", async (route) => {
    const url = new URL(route.request().url());
    const offset = Number(url.searchParams.get("offset") ?? "0");
    const limit = Number(url.searchParams.get("limit") ?? "50");
    const events = all.slice(offset, offset + Math.min(limit, 2)); // two a page, to have a second page
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ total: all.length, offset, limit, events }),
    });
  });
}

async function tabTo(page: Page, name: RegExp, max = 12) {
  for (let i = 0; i < max; i++) {
    await page.keyboard.press("Tab");
    const text = await page.evaluate(
      () => document.activeElement?.getAttribute("aria-label") ?? document.activeElement?.textContent ?? "",
    );
    if (name.test(text)) return;
  }
  throw new Error(`Tab never reached ${String(name)}`);
}

test("the emails are listed newest first, and Show more by keyboard appends the next page", async ({ page }) => {
  await serve(page);
  await page.goto("/keyboard/link-events-harness.html");
  await expect(page.getByRole("heading", { name: "Emails (3)" })).toBeVisible();
  const rows = page.getByRole("list", { name: "Emails" }).getByRole("listitem");
  await expect(rows).toHaveCount(2);
  await expect(rows.nth(0)).toContainText("Subject 3");
  await tabTo(page, /Show more \(1 left\)/);
  await page.keyboard.press("Enter");
  await expect(rows).toHaveCount(3);
  await expect(rows.nth(2)).toContainText("Subject 1");
  await expect(page.getByRole("button", { name: /Show more/ })).toHaveCount(0);
  registerCovered(REGISTRY, "events-list-newest-first-and-show-more-by-keyboard");
});

test("Enter on an email opens it with its text and its cut-off said, and Back returns to the list", async ({ page }) => {
  await serve(page);
  await page.goto("/keyboard/link-events-harness.html");
  await expect(page.getByRole("heading", { name: "Emails (3)" })).toBeVisible();
  await tabTo(page, /Subject 3/);
  await page.keyboard.press("Enter");
  const article = page.locator('article[aria-label="Email: Subject 3"]');
  await expect(article).toBeVisible();
  await expect(article).toContainText("Body of email 3");
  await expect(article).toContainText("first 4,000 characters");
  await expect(article).toContainText("alice@enron.com");
  // Focus moved into the email, onto Back, since the row that had it is gone.
  await expect(page.getByRole("button", { name: "Back to the list" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("list", { name: "Emails" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Emails (3)" })).toBeFocused();
  registerCovered(REGISTRY, "enter-on-an-email-opens-it-and-back-returns");
});

test("every registered link-events action has its own proving test case above", () => {
  assertAllCovered("LINK_EVENTS_ACTIONS", LINK_EVENTS_ACTIONS);
});
