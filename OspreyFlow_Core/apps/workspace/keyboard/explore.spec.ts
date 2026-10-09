// A keyboard-only walkthrough of the Explore panel (ADR-100, rule 13): put a node from the most
// connected on the canvas, open an entity type and put one of its own on the canvas, and page a
// ranking. No `page.mouse`, no `.click()`. The routes are intercepted at the transport, so the
// requests that went out can be read back.
import { expect, test, type Page } from "@playwright/test";

import { EXPLORE_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

const REGISTRY = "EXPLORE_ACTIONS";

/** ADR-100 Amendment 9: the blocks fold, so each walkthrough opens its fold by keyboard first. */
async function openFold(page: Page, name: string) {
  const header = page.getByRole("button", { name, exact: true });
  await header.focus();
  await page.keyboard.press("Enter");
}

function node(id: string, type: string) {
  return {
    id,
    type,
    properties: { name: id },
    provenance: { state: "asserted", sources: [], first_seen: "2026-01-01T00:00:00Z" },
    handling: { classification: "OFFICIAL", handling_code: "P", originator: "u", owning_unit: "u" },
    audit: { created_at: "2026-01-01T00:00:00Z", created_by: "seed", revision: 1 },
  };
}

async function serve(page: Page) {
  const asked: string[] = [];
  await page.route("**/*/v1/investigations/c1/explore/**", async (route) => {
    const url = new URL(route.request().url());
    const json = (body: unknown) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    if (url.pathname.endsWith("/counts")) {
      return json({ nodes: { Person: 3, Organisation: 1 }, edges: { ASSOCIATE_OF: 4 } });
    }
    if (url.pathname.endsWith("/busiest-links")) {
      const edge = { id: "l1", type: "ASSOCIATE_OF", source: "hub0", target: "hub1", occurrences: 9, properties: {} };
      return json({ links: [{ edge, source: node("hub0", "Person"), target: node("hub1", "Person") }], total: 1, offset: 0 });
    }
    if (url.pathname.endsWith("/groups")) {
      return json({
        groups: [{ id: "g1", size: 4, dominant_type: "Person", central: node("hub0", "Person"), central_links: 3 }],
        total_groups: 1,
        not_shown_groups: 0,
        bridges: [{ node: node("hub1", "Person"), groups_reached: 2, links: 5 }],
        total_bridges: 1,
      });
    }
    if (url.pathname.endsWith("/starter-questions")) {
      return json({
        questions: [{ id: "chain:A", question: "Person → Person → Person, by “Associate of” then “Associate of”", pattern: { nodes: [], edges: [] } }],
        total: 1,
      });
    }
    if (url.pathname.endsWith("/run")) {
      return json({ delta: { op: "add", seq: 9, nodes: [node("hub0", "Person")], edges: [] }, added_nodes: 1, added_links: 0 });
    }
    if (url.pathname.endsWith("/whats-new")) {
      return json({
        loads: [{ load_id: "load-1", nodes: 4, links: 4, latest: "2026-10-08T09:00:00Z" }],
        loads_total: 1,
        confirmed: [{ node: node("hub2", "Person"), confirmed_at: "2026-10-08T10:00:00Z", confirmed_by: "analyst-2" }],
        confirmed_total: 1,
        marked: [{ node: node("hub3", "Person"), marked_at: "2026-10-08T11:00:00Z", marked_by: "analyst-3", reason: "a duplicate" }],
        marked_total: 1,
      });
    }
    if (url.pathname.endsWith("/busiest-days")) {
      return json({ days: [{ start: "2001-05-02T00:00:00Z", end: "2001-05-03T00:00:00Z", count: 40 }], total: 1, offset: 0 });
    }
    asked.push(url.search);
    const type = url.searchParams.get("entity_type");
    const offset = Number(url.searchParams.get("offset"));
    const limit = Number(url.searchParams.get("limit"));
    if (type === "Organisation") return json({ nodes: [{ node: node("Acme", "Organisation"), degree: 3 }], total: 1, offset });
    const all = Array.from({ length: 12 }, (_, i) => ({ node: node(`hub${i}`, "Person"), degree: 60 - i }));
    return json({ nodes: all.slice(offset, offset + limit), total: 12, offset });
  });
  await page.goto("/keyboard/explore-harness.html");
  return asked;
}

test("a node from the most connected goes on the canvas by keyboard", async ({ page }) => {
  await serve(page);
  await openFold(page, "Most connected");
  const top = page.getByRole("region", { name: "Most connected" });
  await top.getByRole("button", { name: "Add hub0 to the graph" }).focus();
  await page.keyboard.press("Enter");
  await top.getByRole("button", { name: "Just this entity" }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => window.__EXPLORE__?.picked)).toEqual(["hub0"]);
  registerCovered(REGISTRY, "put-a-most-connected-node-on-the-canvas-by-keyboard");
});

test("an entity type opens by keyboard, and one of its own goes on the canvas", async ({ page }) => {
  await serve(page);
  await openFold(page, "By entity type");
  const byType = page.getByRole("region", { name: "By entity type" });
  const organisation = byType.getByRole("button", { name: "Organisation · 1" });
  await organisation.focus();
  await page.keyboard.press("Enter");
  await expect(organisation).toHaveAttribute("aria-expanded", "true");
  // Its ranking arrives from the server; Tab before it is drawn would land past it.
  await expect(byType.getByText("All 1 shown.")).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(byType.getByRole("button", { name: "Add Acme to the graph" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => window.__EXPLORE__?.picked)).toEqual(["Acme"]);
  registerCovered(REGISTRY, "open-an-entity-type-and-put-one-on-the-canvas-by-keyboard");
});

test("Show more pages a ranking by keyboard, and it says when all are shown", async ({ page }) => {
  const asked = await serve(page);
  await openFold(page, "Most connected");
  const top = page.getByRole("region", { name: "Most connected" });
  await expect(top.getByText("The 10 most connected of 12.")).toBeVisible();
  await top.getByRole("button", { name: "Show 2 more" }).focus();
  await page.keyboard.press("Enter");
  await expect(top.getByText("All 12 shown.")).toBeVisible();
  expect(asked).toContain("?limit=2&offset=10");
  registerCovered(REGISTRY, "show-more-of-a-ranking-by-keyboard");
});

test("a busiest link goes on the canvas by keyboard", async ({ page }) => {
  await serve(page);
  await openFold(page, "Busiest links");
  const busy = page.getByRole("region", { name: "Busiest links" });
  await busy.getByRole("button", { name: "Show: hub0 → hub1 · Associate of · 9 records" }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => window.__EXPLORE__?.links)).toEqual(["l1"]);
  registerCovered(REGISTRY, "put-a-busiest-link-on-the-canvas-by-keyboard");
});

test("a busiest day becomes the timeline's window by keyboard", async ({ page }) => {
  await serve(page);
  await openFold(page, "Busiest days");
  const days = page.getByRole("region", { name: "Busiest days" });
  await days.getByRole("button", { name: "Set window: Wed 2 May 2001 · 40 events" }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => window.__EXPLORE__?.days)).toEqual(["2001-05-02T00:00:00Z"]);
  registerCovered(REGISTRY, "set-the-timeline-to-a-busiest-day-by-keyboard");
});

test("a group's centre goes on the canvas by keyboard", async ({ page }) => {
  await serve(page);
  await openFold(page, "Groups and bridges");
  const groups = page.getByRole("region", { name: "Groups and bridges" });
  await groups.getByRole("button", { name: "Add: Group of 4 · mostly Person · around hub0" }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => window.__EXPLORE__?.picked)).toEqual(["hub0"]);
  registerCovered(REGISTRY, "put-a-groups-centre-on-the-canvas-by-keyboard");
});

test("a bridge goes on the canvas by keyboard", async ({ page }) => {
  await serve(page);
  await openFold(page, "Groups and bridges");
  const groups = page.getByRole("region", { name: "Groups and bridges" });
  await groups.getByRole("button", { name: "Add: hub1 · reaches 2 other groups · 5 links" }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => window.__EXPLORE__?.picked)).toEqual(["hub1"]);
  registerCovered(REGISTRY, "put-a-bridge-on-the-canvas-by-keyboard");
});

test("a node a colleague confirmed goes on the canvas by keyboard", async ({ page }) => {
  await serve(page);
  await openFold(page, "What's new");
  const news = page.getByRole("region", { name: "What's new" });
  await news.getByRole("button", { name: /^Add: hub2 · Person · confirmed by analyst-2/ }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => window.__EXPLORE__?.picked)).toEqual(["hub2"]);
  registerCovered(REGISTRY, "put-a-confirmed-node-on-the-canvas-by-keyboard");
});

test("a node a colleague marked goes on the canvas by keyboard", async ({ page }) => {
  await serve(page);
  await openFold(page, "What's new");
  const news = page.getByRole("region", { name: "What's new" });
  await news.getByRole("button", { name: /^Add: hub3 · Person · marked for suppression by analyst-3/ }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => window.__EXPLORE__?.picked)).toEqual(["hub3"]);
  registerCovered(REGISTRY, "put-a-marked-node-on-the-canvas-by-keyboard");
});

test("a starter question runs onto the canvas by keyboard", async ({ page }) => {
  await serve(page);
  await openFold(page, "Starter questions");
  const starters = page.getByRole("region", { name: "Starter questions" });
  await starters.getByRole("button", { name: /^Run: Person → Person → Person/ }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => window.__EXPLORE__?.deltas)).toEqual([9]);
  await expect(starters.getByText("1 node and 0 links added.")).toBeVisible();
  registerCovered(REGISTRY, "run-a-starter-question-by-keyboard");
});

test("the drawer scrolls, so its last section can be reached and seen", async ({ page }) => {
  await serve(page);
  await openFold(page, "Starter questions");
  const last = page.getByRole("region", { name: "Starter questions" });
  await last.getByRole("button", { name: /^Run: Person → Person → Person/ }).focus();
  await expect(last.getByRole("button", { name: /^Run: Person → Person → Person/ })).toBeInViewport();
  await page.mouse.move(1000, 400);
  await page.mouse.wheel(0, -100_000);
  await expect(page.getByRole("heading", { name: "What this case holds" })).toBeInViewport();
});

test("a node goes on the canvas with a budget of its busiest links, by keyboard", async ({ page }) => {
  await serve(page);
  await openFold(page, "Most connected");
  const top = page.getByRole("region", { name: "Most connected" });
  await top.getByRole("button", { name: "Add hub0 to the graph" }).focus();
  await page.keyboard.press("Enter");
  await top.getByRole("button", { name: "With its 25 busiest links" }).focus();
  await page.keyboard.press("Enter");
  // The node and its one served link reach the caller; which request went out (node_id, limit)
  // is the panel unit test's assertion.
  await expect.poll(() => page.evaluate(() => window.__EXPLORE__?.budget)).toEqual([["hub0", 1]]);
  registerCovered(REGISTRY, "add-a-node-with-its-busiest-links-by-keyboard");
});

test("a node with all its links hands over to the canvas's expand, by keyboard", async ({ page }) => {
  await serve(page);
  await openFold(page, "Most connected");
  const top = page.getByRole("region", { name: "Most connected" });
  await top.getByRole("button", { name: "Add hub0 to the graph" }).focus();
  await page.keyboard.press("Enter");
  await top.getByRole("button", { name: "With all 60 links…" }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => window.__EXPLORE__?.expandedAll)).toEqual(["hub0"]);
  registerCovered(REGISTRY, "add-a-node-with-all-its-links-by-keyboard");
});

test("every registered explore action has its own proving test case above", () => {
  assertAllCovered("EXPLORE_ACTIONS", EXPLORE_ACTIONS);
});
