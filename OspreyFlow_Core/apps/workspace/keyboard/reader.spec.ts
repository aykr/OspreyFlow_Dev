// The full-screen reader (ADR-092), by keyboard alone (rule 13): Enter on a Document on the canvas
// opens it to read rather than expanding it; in the reader, Tab reaches Extract entities and a
// finding's Accept, and Escape closes it. No `page.mouse`, no `.click()`.
import { expect, test, type Page } from "@playwright/test";

import { READER_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

const REGISTRY = "READER_ACTIONS";

declare global {
  interface Window {
    __KEYBOARD__?: { focused: string | null; openedDocument: string | null };
    __READER__?: { closed: number; deltas: unknown[] };
  }
}

const EMAIL = {
  document_id: "email:ev-1",
  title: "Dabhol",
  text: "Dana MERCER wrote about the plant.",
  truncated: false,
  spans: [],
  sent_at: "2001-05-14T10:00:00Z",
  sender_id: "a",
  recipient_id: "b",
  edge_id: "e1",
  event_id: "ev-1",
};

async function serveReader(page: Page) {
  const json = (body: unknown) => ({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  await page.route("**/v1/investigations/inv-1/documents/*/reader", (route) => route.fulfill(json(EMAIL)));
  await page.route("**/v1/investigations/inv-1/links/e1/events/ev-1/extract", (route) =>
    route.fulfill(
      json({
        document_id: "email:ev-1",
        delta: { seq: 2, op: "add", nodes: [], edges: [] },
        candidates: [
          {
            id: "c1",
            document_id: "email:ev-1",
            entity_type: "Person",
            properties: { family_name: "MERCER", given_names: "Dana" },
            confidence: 0.9,
            status: "pending",
          },
        ],
      }),
    ),
  );
  await page.route("**/v1/investigations/inv-1/links/e1/events/ev-1/candidates/c1/accept", (route) =>
    route.fulfill(json({ node_id: "p1", delta: { seq: 3, op: "add", nodes: [], edges: [] } })),
  );
}

async function tabTo(page: Page, name: RegExp, max = 10) {
  for (let i = 0; i < max; i++) {
    await page.keyboard.press("Tab");
    const text = await page.evaluate(
      () => document.activeElement?.getAttribute("aria-label") ?? document.activeElement?.textContent ?? "",
    );
    if (name.test(text)) return;
  }
  throw new Error(`Tab never reached ${String(name)}`);
}

test("Enter on a Document on the canvas opens it to read, not to expand", async ({ page }) => {
  await page.goto("/keyboard/harness.html?fixture=emails");
  await page.getByRole("application", { name: "Network canvas" }).focus();
  for (let i = 0; i < 6; i++) {
    if ((await page.evaluate(() => window.__KEYBOARD__?.focused)) === "email:ev-1") break;
    await page.keyboard.press("Control+Shift+ArrowRight"); // every node in turn, linked or not
  }
  await expect.poll(() => page.evaluate(() => window.__KEYBOARD__?.focused)).toBe("email:ev-1");
  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => window.__KEYBOARD__?.openedDocument)).toBe("email:ev-1");
  registerCovered(REGISTRY, "enter-on-a-document-opens-it-to-read");
});

test("A Document's own menu offers Read full screen, which opens it to read", async ({ page }) => {
  await page.goto("/keyboard/harness.html?fixture=emails");
  await page.getByRole("application", { name: "Network canvas" }).focus();
  for (let i = 0; i < 6; i++) {
    if ((await page.evaluate(() => window.__KEYBOARD__?.focused)) === "email:ev-1") break;
    await page.keyboard.press("Control+Shift+ArrowRight");
  }
  await expect.poll(() => page.evaluate(() => window.__KEYBOARD__?.focused)).toBe("email:ev-1");
  await page.keyboard.press("\\"); // the node's menu, as a list
  // A Document's first action, so the menu opens on it.
  await expect(page.getByRole("menuitem", { name: "Read full screen" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => window.__KEYBOARD__?.openedDocument)).toBe("email:ev-1");
  registerCovered(REGISTRY, "read-full-screen-from-a-documents-menu");
});

test("the reader opens with focus on Close, and Escape closes it", async ({ page }) => {
  await serveReader(page);
  await page.goto("/keyboard/reader-harness.html");
  await expect(page.getByRole("dialog", { name: "Reading: Dabhol" })).toBeVisible();
  await expect(page.getByText("Dana MERCER wrote about the plant.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Close" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect.poll(() => page.evaluate(() => window.__READER__?.closed)).toBe(1);
  registerCovered(REGISTRY, "escape-closes-the-reader");
});

test("Extract entities and Accept are reached and pressed by keyboard in the reader", async ({ page }) => {
  await serveReader(page);
  await page.goto("/keyboard/reader-harness.html");
  await expect(page.getByRole("button", { name: "Close" })).toBeFocused();
  await tabTo(page, /^Extract entities$/);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("list", { name: "Entities found" })).toBeVisible();
  await tabTo(page, /Accept Person · MERCER, Dana/);
  await page.keyboard.press("Enter");
  await expect(page.getByText("Accepted")).toBeVisible();
  await expect.poll(() => page.evaluate(() => window.__READER__?.deltas.length)).toBe(2);
  registerCovered(REGISTRY, "extract-and-accept-from-the-reader-by-keyboard");
});

test("every registered reader action has its own proving test case above", () => {
  assertAllCovered("READER_ACTIONS", READER_ACTIONS);
});
