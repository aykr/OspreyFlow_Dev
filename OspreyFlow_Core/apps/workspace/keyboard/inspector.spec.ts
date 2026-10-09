// The Inspector's parts by keyboard alone (ADR-096, rule 13): a part opens and folds by Enter on
// its header; opening *Change this link* lands in the form; a link-menu hand-over opens its part.
// No `page.mouse`, no `.click()`. The link's notes, events and history are answered at the
// transport, empty, as the server answers a link with none.
import { expect, test, type Page } from "@playwright/test";

import { INSPECTOR_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

const REGISTRY = "INSPECTOR_ACTIONS";

async function serve(page: Page) {
  const json = (body: unknown) => ({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  await page.route("**/v1/investigations/inv-1/links/e1/notes", (r) => r.fulfill(json({ notes: [] })));
  await page.route("**/v1/investigations/inv-1/links/e1/history", (r) => r.fulfill(json({ changes: [], truncated: false })));
  await page.route("**/v1/investigations/inv-1/links/e1/events**", (r) =>
    r.fulfill(json({ total: 0, offset: 0, limit: 50, events: [] })),
  );
}

const header = (page: Page, name: string) => page.getByRole("button", { name, exact: true });

test("a part opens and folds by Enter on its header", async ({ page }) => {
  await serve(page);
  await page.goto("/keyboard/inspector-harness.html");
  await expect(header(page, "Details")).toHaveAttribute("aria-expanded", "true");
  await header(page, "Notes").focus();
  await expect(header(page, "Notes")).toHaveAttribute("aria-expanded", "false");
  await page.keyboard.press("Enter");
  await expect(header(page, "Notes")).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByRole("region", { name: "Notes" })).toBeVisible();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("region", { name: "Notes" })).toHaveCount(0);
  registerCovered(REGISTRY, "a-part-opens-and-folds-by-keyboard");
});

test("opening Change this link by keyboard lands in the form, at the link type", async ({ page }) => {
  await serve(page);
  await page.goto("/keyboard/inspector-harness.html");
  await header(page, "Change this link").focus();
  await page.keyboard.press("Enter");
  await expect(page.getByLabel("Link type")).toBeFocused();
  registerCovered(REGISTRY, "opening-change-this-link-opens-the-form");
});

test("a link-menu hand-over opens its part", async ({ page }) => {
  await serve(page);
  await page.goto("/keyboard/inspector-harness.html");
  await expect(header(page, "Notes")).toHaveAttribute("aria-expanded", "false");
  await page.getByRole("button", { name: "Hand over: Add a note" }).focus();
  await page.keyboard.press("Enter");
  await expect(header(page, "Notes")).toHaveAttribute("aria-expanded", "true");
  registerCovered(REGISTRY, "a-menu-hand-over-opens-its-part");
});

test("who shares contacts with a node is asked, and a pair put on the canvas, by keyboard", async ({ page }) => {
  await page.route("**/*/v1/investigations/inv-1/nodes/a/shared-contacts**", async (route) => {
    const post = route.request().method() === "POST";
    const body = post
      ? { delta: { op: "add", seq: 5, nodes: [], edges: [] }, added_nodes: 3, added_links: 4 }
      : {
          contacts: [{ node: { id: "b", type: "Person", properties: { family_name: "Skilling" }, provenance: { state: "asserted", sources: [], first_seen: "2026-01-01T00:00:00Z" }, handling: { classification: "OFFICIAL", handling_code: "P", originator: "unit-1", owning_unit: "unit-1" }, audit: { created_at: "2026-01-01T00:00:00Z", created_by: "fixture" } }, shared: 7 }],
          total: 1,
        };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
  await page.goto("/keyboard/inspector-harness.html?view=node");
  const header = page.getByRole("button", { name: "Shares contacts" });
  await header.focus();
  await page.keyboard.press("Enter");
  await page.getByRole("button", { name: "Who shares two contacts by “Associate of”?" }).focus();
  await page.keyboard.press("Enter");
  await page.getByRole("button", { name: "Skilling · shares 7" }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => window.__INSPECTOR__?.deltas)).toEqual([5]);
  await expect(page.getByText("3 nodes and 4 links added.")).toBeVisible();
  registerCovered(REGISTRY, "ask-who-shares-contacts-and-add-a-pair-by-keyboard");
});

test("a link's handling is lowered by keyboard, and only once confirmed", async ({ page }) => {
  await serve(page);
  const sent: unknown[] = [];
  await page.route("**/v1/investigations/inv-1/links/e1/change", async (route) => {
    sent.push(route.request().postDataJSON());
    await route.fulfill({ status: 403, contentType: "application/json", body: JSON.stringify({ error: "lowering_needs_author" }) });
  });
  await page.goto("/keyboard/inspector-harness.html");
  await header(page, "Change this link").focus();
  await page.keyboard.press("Enter");
  await page.getByLabel("Classification").focus();
  await page.keyboard.press("p"); // type-ahead in the select: PUBLIC
  await expect(page.getByLabel("Classification")).toHaveValue("PUBLIC");
  // The harness's type is Direct, so what stands behind the link is asked first (ADR-081).
  await page.getByRole("radio", { name: /^Direct/ }).focus();
  await page.keyboard.press("Space");
  await page.getByLabel("Why is it being changed? (required)").focus();
  await page.keyboard.type("Released by the originator");
  await page.getByRole("button", { name: "Save change" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("This lowers the link's classification. Confirm that you mean to lower it.")).toBeVisible();
  expect(sent).toEqual([]);
  await page.getByLabel("I mean to lower this link's handling").focus();
  await page.keyboard.press("Space");
  await page.getByRole("button", { name: "Save change" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("Lowering a link's handling needs Author access.")).toBeVisible();
  expect(sent).toHaveLength(1);
  expect(sent[0]).toMatchObject({ handling: { classification: "PUBLIC" }, confirm_lower: true });
  registerCovered(REGISTRY, "lower-a-links-handling-with-a-confirmation-by-keyboard");
});

// ADR-105: a 1x1 PNG, so the picture is really read and drawn small in the browser.
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64",
);

async function servePictures(page: Page) {
  const sent: { method: string; query: Record<string, string> }[] = [];
  let held = false;
  const json = (body: unknown) => ({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  await page.route("**/v1/handling-scheme", (r) => r.fulfill(json({ classification: ["OFFICIAL", "SECRET"] })));
  await page.route("**/v1/investigations/inv-1/pictures", (r) =>
    r.fulfill(json(held ? [{ node_id: "car-1", document_id: "content:1" }] : [])),
  );
  await page.route("**/v1/investigations/inv-1/nodes/car-1/picture**", async (route) => {
    const request = route.request();
    const method = request.method();
    sent.push({ method, query: Object.fromEntries(new URL(request.url()).searchParams) });
    if (method === "PUT") {
      held = true;
      await route.fulfill(json({ document_id: "content:1", deltas: [{ op: "add", seq: 7, nodes: [], edges: [] }] }));
    } else if (method === "DELETE") {
      held = false;
      await route.fulfill(json({ op: "replace_edge", seq: 8 }));
    } else {
      await route.fulfill({ status: 200, contentType: "image/png", body: PNG });
    }
  });
  return sent;
}

async function setPictureByKeyboard(page: Page) {
  await page.getByRole("button", { name: "Picture", exact: true }).focus();
  await page.keyboard.press("Enter");
  await page.getByLabel("Picture file").setInputFiles({ name: "car.png", mimeType: "image/png", buffer: PNG });
  await page.getByLabel("Picture legal basis").focus();
  await page.keyboard.type("Seized under PACE s19");
  await page.getByRole("button", { name: "Set picture" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("img", { name: "This entity's own picture" })).toBeVisible();
}

test("an entity's own picture is set by keyboard, with its marking and legal basis", async ({ page }) => {
  const sent = await servePictures(page);
  await page.goto("/keyboard/inspector-harness.html?view=picture");
  await setPictureByKeyboard(page);
  expect(sent[0]).toEqual({
    method: "PUT",
    query: { name: "car.png", classification: "OFFICIAL", legal_basis: "Seized under PACE s19" },
  });
  await expect.poll(() => page.evaluate(() => window.__INSPECTOR__?.deltas)).toEqual([7]);
  registerCovered(REGISTRY, "set-an-entitys-own-picture-by-keyboard");
});

test("an entity's own picture is removed by keyboard, back to its type's", async ({ page }) => {
  const sent = await servePictures(page);
  await page.goto("/keyboard/inspector-harness.html?view=picture");
  await setPictureByKeyboard(page);
  await page.getByRole("button", { name: "Remove picture" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("No picture of its own: it is drawn with its type's.")).toBeVisible();
  expect(sent.map((s) => s.method)).toContain("DELETE");
  await expect.poll(() => page.evaluate(() => window.__INSPECTOR__?.deltas)).toEqual([7, 8]);
  registerCovered(REGISTRY, "remove-an-entitys-own-picture-by-keyboard");
});

test("every registered Inspector action has its own proving test case above", () => {
  assertAllCovered("INSPECTOR_ACTIONS", INSPECTOR_ACTIONS);
});
