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

async function serveExtraction(page: Page) {
  const accepted: string[] = [];
  const usings: string[] = [];
  const rejected: string[] = [];
  await page.route("**/*/v1/investigations/inv-1/links/e1/events/ev-3/candidates/*/reject", async (route) => {
    rejected.push(route.request().url());
    await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });
  await page.route("**/*/v1/investigations/inv-1/links/e1/events/ev-3/extract", async (route) => {
    usings.push((route.request().postDataJSON() as { using?: string }).using ?? "");
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        document_id: "email:ev-3",
        candidates: [
          { id: "c1", document_id: "email:ev-3", entity_type: "Person", properties: { family_name: "MERCER", given_names: "Dana" }, confidence: 0.9, status: "pending" },
        ],
        delta: { seq: 2, op: "add", nodes: [], edges: [] },
      }),
    });
  });
  await page.route("**/*/v1/investigations/inv-1/links/e1/events/ev-3/candidates/*/accept", async (route) => {
    accepted.push(route.request().url());
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ node_id: "n-mercer", delta: { seq: 3, op: "add", nodes: [], edges: [] } }),
    });
  });
  return Object.assign(accepted, { usings, rejected });
}

test("Extract entities, reached and pressed by keyboard, lists the model's findings and hands the delta on", async ({ page }) => {
  await serve(page);
  await serveExtraction(page);
  await page.goto("/keyboard/link-events-harness.html");
  await expect(page.getByRole("heading", { name: "Emails (3)" })).toBeVisible();
  await tabTo(page, /Subject 3/);
  await page.keyboard.press("Enter");
  await tabTo(page, /Extract entities/);
  await page.keyboard.press("Enter");
  const list = page.getByRole("list", { name: "Entities found" });
  await expect(list).toBeVisible();
  await expect(list).toContainText("Person · MERCER, Dana");
  await expect.poll(() => page.evaluate(() => window.__LINK_EVENTS__?.deltas.length)).toBe(1);
  registerCovered(REGISTRY, "extract-entities-by-keyboard-lists-the-findings");
});

test("Accept on a finding, by keyboard, sends the accept and marks it accepted", async ({ page }) => {
  await serve(page);
  const accepted = await serveExtraction(page);
  await page.goto("/keyboard/link-events-harness.html");
  await expect(page.getByRole("heading", { name: "Emails (3)" })).toBeVisible();
  await tabTo(page, /Subject 3/);
  await page.keyboard.press("Enter");
  await tabTo(page, /Extract entities/);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("list", { name: "Entities found" })).toBeVisible();
  await tabTo(page, /^Accept Person · MERCER, Dana$/);
  await page.keyboard.press("Enter");
  await expect.poll(() => accepted.length).toBe(1);
  expect(accepted[0]).toMatch(/\/candidates\/c1\/accept$/);
  await expect(page.getByRole("list", { name: "Entities found" })).toContainText("Accepted");
  await expect.poll(() => page.evaluate(() => window.__LINK_EVENTS__?.deltas.length)).toBe(2);
  registerCovered(REGISTRY, "accept-a-finding-by-keyboard");
});

test("Read full screen on an opened email hands it to the reader, by keyboard (ADR-092 Amendment 3)", async ({ page }) => {
  await serve(page);
  await page.goto("/keyboard/link-events-harness.html");
  await expect(page.getByRole("heading", { name: "Emails (3)" })).toBeVisible();
  await tabTo(page, /Subject 3/);
  await page.keyboard.press("Enter");
  await tabTo(page, /^Read full screen$/);
  await page.keyboard.press("Enter");
  await expect
    .poll(() => page.evaluate(() => (window as unknown as { __LINK_EVENTS__: { readFullScreen: string[] } }).__LINK_EVENTS__.readFullScreen))
    .toEqual(["email:ev-3"]);
  registerCovered(REGISTRY, "read-full-screen-from-an-opened-email");
});

test("Put on the canvas, reached and pressed by keyboard, writes the emails and hands the delta on (ADR-095)", async ({ page }) => {
  await serve(page);
  const writes: unknown[] = [];
  // Registered after `serve`, so it answers the documents write (a later route wins).
  await page.route("**/*/v1/investigations/inv-1/links/e1/events/documents", async (route) => {
    writes.push(route.request().postDataJSON());
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ written: 3, without_text: 0, delta: { op: "add", seq: 9, nodes: [], edges: [] } }),
    });
  });
  await page.goto("/keyboard/link-events-harness.html");
  await expect(page.getByRole("heading", { name: "Emails (3)" })).toBeVisible();
  await tabTo(page, /^Put on the canvas$/);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status")).toHaveText("3 emails put on the canvas.");
  expect(writes).toHaveLength(1);
  expect(await page.evaluate(() => window.__LINK_EVENTS__!.deltas.length)).toBe(1);
  registerCovered(REGISTRY, "put-the-emails-on-the-canvas-from-the-list");
});

test("Ask the model to extract, by keyboard, asks the model after the fast pass (ADR-098)", async ({ page }) => {
  await serve(page);
  const asked = await serveExtraction(page);
  await page.goto("/keyboard/link-events-harness.html");
  await expect(page.getByRole("heading", { name: "Emails (3)" })).toBeVisible();
  await tabTo(page, /Subject 3/);
  await page.keyboard.press("Enter");
  await tabTo(page, /^Extract entities$/);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("list", { name: "Entities found" })).toBeVisible();
  await tabTo(page, /^Ask the model to extract$/);
  await page.keyboard.press("Enter");
  await expect.poll(() => asked.usings).toEqual(["recogniser", "model"]);
  registerCovered(REGISTRY, "ask-the-model-to-extract-by-keyboard");
});

test("Reject on a finding, by keyboard, sends the reject and marks it rejected", async ({ page }) => {
  await serve(page);
  const asked = await serveExtraction(page);
  await page.goto("/keyboard/link-events-harness.html");
  await expect(page.getByRole("heading", { name: "Emails (3)" })).toBeVisible();
  await tabTo(page, /Subject 3/);
  await page.keyboard.press("Enter");
  await tabTo(page, /^Extract entities$/);
  await page.keyboard.press("Enter");
  await tabTo(page, /^Reject Person · MERCER, Dana$/);
  await page.keyboard.press("Enter");
  await expect.poll(() => asked.rejected.length).toBe(1);
  await expect(page.getByRole("list", { name: "Entities found" })).toContainText("Rejected");
  registerCovered(REGISTRY, "reject-a-finding-by-keyboard");
});

test("every registered link-events action has its own proving test case above", () => {
  assertAllCovered("LINK_EVENTS_ACTIONS", LINK_EVENTS_ACTIONS);
});
