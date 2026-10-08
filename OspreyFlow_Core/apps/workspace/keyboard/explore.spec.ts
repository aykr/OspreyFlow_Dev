// A keyboard-only walkthrough of the Explore panel (ADR-100, rule 13): put a node from the most
// connected on the canvas, open an entity type and put one of its own on the canvas, and page a
// ranking. No `page.mouse`, no `.click()`. The routes are intercepted at the transport, so the
// requests that went out can be read back.
import { expect, test, type Page } from "@playwright/test";

import { EXPLORE_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

const REGISTRY = "EXPLORE_ACTIONS";

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
    if (url.pathname.endsWith("/busiest-days")) {
      return json({ days: [{ start: "2001-05-02T00:00:00Z", end: "2001-05-03T00:00:00Z", count: 40 }], total: 1, offset: 0 });
    }
    asked.push(url.search);
    const type = url.searchParams.get("entity_type");
    const offset = Number(url.searchParams.get("offset"));
    const limit = Number(url.searchParams.get("limit"));
    if (type === "Organisation") return json({ nodes: [{ node: node("Acme", "Organisation"), degree: 3 }], total: 1, offset });
    const all = Array.from({ length: 12 }, (_, i) => ({ node: node(`hub${i}`, "Person"), degree: 20 - i }));
    return json({ nodes: all.slice(offset, offset + limit), total: 12, offset });
  });
  await page.goto("/keyboard/explore-harness.html");
  return asked;
}

test("a node from the most connected goes on the canvas by keyboard", async ({ page }) => {
  await serve(page);
  const top = page.getByRole("region", { name: "Most connected" });
  await top.getByRole("button", { name: "hub0 · Person · 20 links" }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => window.__EXPLORE__?.picked)).toEqual(["hub0"]);
  registerCovered(REGISTRY, "put-a-most-connected-node-on-the-canvas-by-keyboard");
});

test("an entity type opens by keyboard, and one of its own goes on the canvas", async ({ page }) => {
  await serve(page);
  const byType = page.getByRole("region", { name: "By entity type" });
  const organisation = byType.getByRole("button", { name: "Organisation · 1" });
  await organisation.focus();
  await page.keyboard.press("Enter");
  await expect(organisation).toHaveAttribute("aria-expanded", "true");
  // Its ranking arrives from the server; Tab before it is drawn would land past it.
  await expect(byType.getByText("All 1 shown.")).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(byType.getByRole("button", { name: "Acme · Organisation · 3 links" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => window.__EXPLORE__?.picked)).toEqual(["Acme"]);
  registerCovered(REGISTRY, "open-an-entity-type-and-put-one-on-the-canvas-by-keyboard");
});

test("Show more pages a ranking by keyboard, and it says when all are shown", async ({ page }) => {
  const asked = await serve(page);
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
  const busy = page.getByRole("region", { name: "Busiest links" });
  await busy.getByRole("button", { name: "hub0 → hub1 · Associate of · 9 records" }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => window.__EXPLORE__?.links)).toEqual(["l1"]);
  registerCovered(REGISTRY, "put-a-busiest-link-on-the-canvas-by-keyboard");
});

test("a busiest day becomes the timeline's window by keyboard", async ({ page }) => {
  await serve(page);
  const days = page.getByRole("region", { name: "Busiest days" });
  await days.getByRole("button", { name: "Wed 2 May 2001 · 40 events" }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => window.__EXPLORE__?.days)).toEqual(["2001-05-02T00:00:00Z"]);
  registerCovered(REGISTRY, "set-the-timeline-to-a-busiest-day-by-keyboard");
});

test("a group's centre goes on the canvas by keyboard", async ({ page }) => {
  await serve(page);
  const groups = page.getByRole("region", { name: "Groups and bridges" });
  await groups.getByRole("button", { name: "Group of 4 · mostly Person · around hub0" }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => window.__EXPLORE__?.picked)).toEqual(["hub0"]);
  registerCovered(REGISTRY, "put-a-groups-centre-on-the-canvas-by-keyboard");
});

test("a bridge goes on the canvas by keyboard", async ({ page }) => {
  await serve(page);
  const groups = page.getByRole("region", { name: "Groups and bridges" });
  await groups.getByRole("button", { name: "hub1 · reaches 2 other groups · 5 links" }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => window.__EXPLORE__?.picked)).toEqual(["hub1"]);
  registerCovered(REGISTRY, "put-a-bridge-on-the-canvas-by-keyboard");
});

test("every registered explore action has its own proving test case above", () => {
  assertAllCovered("EXPLORE_ACTIONS", EXPLORE_ACTIONS);
});
