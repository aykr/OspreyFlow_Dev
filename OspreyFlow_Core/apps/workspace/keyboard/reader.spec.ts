// The full-screen reader (ADR-092), by keyboard alone (rule 13): Enter on a Document on the canvas
// opens it to read rather than expanding it; in the reader, Tab reaches Quick scan and a
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
  await page.route("**/v1/investigations/inv-1/links/e1/events/ev-1/candidates/c1/reject", (route) =>
    route.fulfill(json({})),
  );
}

/** The reader draws its scan buttons and the marking box only once the document has arrived, so a
 * walk waits for "Opening…" to go, as a person would (CI on a3ffb48 tabbed before it had). */
async function documentOpened(page: Page) {
  await expect(page.getByText("Opening…")).toHaveCount(0);
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

test("Quick scan and Accept are reached and pressed by keyboard in the reader", async ({ page }) => {
  await serveReader(page);
  await page.goto("/keyboard/reader-harness.html");
  await expect(page.getByRole("button", { name: "Close" })).toBeFocused();
  await documentOpened(page);
  await tabTo(page, /^Quick scan$/);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("list", { name: "Entities found" })).toBeVisible();
  await tabTo(page, /Accept Person · MERCER, Dana/);
  await page.keyboard.press("Enter");
  await expect(page.getByText("Accepted")).toBeVisible();
  await expect.poll(() => page.evaluate(() => window.__READER__?.deltas.length)).toBe(2);
  registerCovered(REGISTRY, "extract-and-accept-from-the-reader-by-keyboard");
});

test("Reject beside Accept is reached and pressed by keyboard, and draws nothing (owner, 6 October 2026)", async ({ page }) => {
  await serveReader(page);
  await page.goto("/keyboard/reader-harness.html");
  await expect(page.getByRole("button", { name: "Close" })).toBeFocused();
  await documentOpened(page);
  await tabTo(page, /^Quick scan$/);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("list", { name: "Entities found" })).toBeVisible();
  await tabTo(page, /Reject Person · MERCER, Dana/);
  await page.keyboard.press("Enter");
  await expect(page.getByText("Rejected")).toBeVisible();
  // The extraction's own delta only; a rejection writes nothing.
  await expect.poll(() => page.evaluate(() => window.__READER__?.deltas.length)).toBe(1);
  registerCovered(REGISTRY, "reject-a-finding-in-the-reader-by-keyboard");
});

test("Accept all pending accepts the enumerated findings as one decision by keyboard (ADR-108 Q1)", async ({ page }) => {
  // A held Document (not an email): the bulk surface is the Document route's own.
  const json = (body: unknown) => ({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  const candidate = (id: string, entityType: string, name: string) => ({
    id,
    document_id: "email:ev-1",
    entity_type: entityType,
    properties: { name },
    confidence: 1,
    status: "pending",
  });
  await serveReader(page);
  await page.route("**/v1/investigations/inv-1/documents/*/reader", (route) =>
    route.fulfill(json({ ...EMAIL, edge_id: undefined, event_id: undefined, has_file: true })),
  );
  await page.route("**/v1/investigations/inv-1/documents/*/extract", (route) =>
    route.fulfill(
      json({
        document_id: "email:ev-1",
        text: EMAIL.text,
        candidates: [candidate("c1", "Person", "Dana Mercer"), candidate("c2", "Location", "Dabhol")],
      }),
    ),
  );
  let sent: { candidate_ids?: string[] } | null = null;
  await page.route("**/v1/investigations/inv-1/documents/*/candidates/accept", async (route) => {
    sent = route.request().postDataJSON();
    await route.fulfill(
      json({
        accepted: [
          { node_id: "n1", delta: { seq: 2, op: "add", nodes: [], edges: [] } },
          { node_id: "n2", delta: { seq: 3, op: "add", nodes: [], edges: [] } },
        ],
        refusals: [],
      }),
    );
  });
  await page.goto("/keyboard/reader-harness.html");
  await expect(page.getByRole("button", { name: "Close" })).toBeFocused();
  await documentOpened(page);
  await tabTo(page, /^Quick scan$/);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("list", { name: "Entities found" })).toBeVisible();
  await tabTo(page, /^Accept all pending \(2\)$/);
  await page.keyboard.press("Enter");
  await expect.poll(() => sent?.candidate_ids).toEqual(["c1", "c2"]);
  await expect(page.getByText("Accepted").first()).toBeVisible();
  registerCovered(REGISTRY, "accept-all-pending-in-the-reader-by-keyboard");
});

test("words are marked as an entity by keyboard: typed, a type chosen, and Mark pressed (ADR-098)", async ({ page }) => {
  await serveReader(page);
  let sent: { entity_type: string; text: string; start: number; end: number } | null = null;
  await page.route("**/v1/investigations/inv-1/documents/*/designations", async (route) => {
    sent = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ node_id: "m1", delta: { seq: 4, op: "add", nodes: [], edges: [] } }),
    });
  });
  await page.goto("/keyboard/reader-harness.html");
  await expect(page.getByRole("button", { name: "Close" })).toBeFocused();
  await documentOpened(page);
  await tabTo(page, /^Words to mark$/, 20);
  await page.keyboard.type("MERCER");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("combobox", { name: "Mark as" })).toBeFocused();
  await page.keyboard.press("Tab");
  await page.keyboard.press("Enter");
  await expect.poll(() => sent?.text).toBe("MERCER");
  expect(sent!.entity_type).toBe("Person");
  await expect(page.getByText("Marked “MERCER” as a Person.")).toBeVisible();
  await expect.poll(() => page.evaluate(() => window.__READER__?.deltas.length)).toBe(1);
  registerCovered(REGISTRY, "mark-an-entity-in-the-reader-by-keyboard");
});

test("Deep read (model) is reached and pressed by keyboard in the reader (ADR-098)", async ({ page }) => {
  await serveReader(page);
  const usings: string[] = [];
  page.on("request", (request) => {
    if (request.url().endsWith("/extract")) usings.push((request.postDataJSON() as { using?: string }).using ?? "");
  });
  await page.goto("/keyboard/reader-harness.html");
  await expect(page.getByRole("button", { name: "Close" })).toBeFocused();
  await documentOpened(page);
  await tabTo(page, /^Deep read \(model\)$/, 20);
  await page.keyboard.press("Enter");
  await expect.poll(() => usings).toEqual(["model"]);
  registerCovered(REGISTRY, "ask-the-model-to-extract-in-the-reader-by-keyboard");
});

test("every registered reader action has its own proving test case above", () => {
  assertAllCovered("READER_ACTIONS", READER_ACTIONS);
});
