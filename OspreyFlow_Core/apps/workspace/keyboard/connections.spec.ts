// Find connections (ADR-116) by keyboard alone (rule 13): From and To by search and from the canvas's
// selection, the search, widening by one degree, a route put on the canvas and its marks cleared.
import { expect, test, type Page } from "@playwright/test";

import { CONNECTIONS_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

const REGISTRY = "CONNECTIONS_ACTIONS";

function node(id: string, name: string) {
  return {
    id,
    type: "Person",
    properties: { name },
    provenance: { state: "asserted", sources: [], first_seen: "2026-01-01T00:00:00Z" },
    handling: { classification: "OFFICIAL", handling_code: "P", originator: "u", owning_unit: "u" },
    audit: { created_at: "2026-01-01T00:00:00Z", created_by: "seed", revision: 1 },
  };
}

const NAMES: Record<string, string> = { a: "Ada", b: "Ben", c: "Cy", d: "Dee", x: "Xan" };

function route(...ids: string[]) {
  return {
    nodes: ids.map((id) => node(id, NAMES[id]!)),
    edges: ids.slice(1).map((id, i) => ({ id: `${ids[i]}-${id}`, type: "ASSOCIATE_OF", source: ids[i], target: id })),
    length: ids.length - 1,
  };
}

/** Ada and Dee are two degrees apart through Xan, and three through Ben and Cy. */
async function serve(page: Page) {
  const asked = { connections: [] as unknown[], seeded: [] as unknown[] };
  const json = (body: unknown) => ({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  await page.route("**/v1/investigations/inv-1/suggest", async (r) => {
    const query = String(r.request().postDataJSON().query);
    const nodes = query.startsWith("Ad") ? [node("a", "Ada")] : query.startsWith("De") ? [node("d", "Dee")] : [];
    await r.fulfill(json({ nodes, more: false }));
  });
  await page.route("**/v1/investigations/inv-1/connections", async (r) => {
    const body = r.request().postDataJSON() as { degree?: number };
    asked.connections.push(body);
    const degree = body.degree ?? 2;
    const paths = degree === 2 ? [route("a", "x", "d")] : degree === 3 ? [route("a", "b", "c", "d")] : [];
    await r.fulfill(json({ degree, paths, more: false, searched_to: degree }));
  });
  await page.route("**/v1/investigations/inv-1/seed", async (r) => {
    asked.seeded.push(r.request().postDataJSON());
    await r.fulfill(json({ delta: { op: "add", seq: 1, nodes: [], edges: [] } }));
  });
  return asked;
}

async function focused(page: Page): Promise<string> {
  return page.evaluate(
    () => document.activeElement?.getAttribute("aria-label") ?? document.activeElement?.textContent ?? "",
  );
}

async function tabTo(page: Page, name: RegExp, max = 20) {
  for (let i = 0; i < max; i++) {
    await page.keyboard.press("Tab");
    if (name.test(await focused(page))) return;
  }
  throw new Error(`Tab never reached ${String(name)}`);
}

/** Types into an end's search box and takes the first suggestion with Enter. */
async function chooseBySearch(page: Page, end: "From" | "To", typed: string) {
  await tabTo(page, new RegExp(`^Search for ${end}$`));
  await page.keyboard.type(typed);
  await expect(page.getByRole("option").first()).toBeVisible();
  await page.keyboard.press("Enter");
}

test("From and To are chosen by search, and Find connections gives the fewest degrees", async ({ page }) => {
  const asked = await serve(page);
  await page.goto("/keyboard/connections-harness.html");
  await chooseBySearch(page, "From", "Ad");
  await expect(page.getByText("From: Ada")).toBeVisible();
  await chooseBySearch(page, "To", "De");
  await expect(page.getByText("To: Dee")).toBeVisible();
  registerCovered(REGISTRY, "choose-from-and-to-by-search-by-keyboard");

  await tabTo(page, /^Find connections$/);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status").filter({ hasText: "degrees apart" })).toHaveText("Ada and Dee are 2 degrees apart.");
  await expect(page.getByRole("region", { name: "1 route at 2 degrees" })).toContainText("Ada → Xan → Dee");
  expect(asked.connections).toEqual([{ source: "a", target: "d" }]);
  registerCovered(REGISTRY, "find-connections-by-keyboard");

  await tabTo(page, /^Show routes at 3 degrees$/);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("region", { name: "1 route at 3 degrees" })).toContainText("Ada → Ben → Cy → Dee");
  await expect(page.getByRole("region", { name: "1 route at 2 degrees" })).toBeVisible();
  expect(asked.connections).toEqual([{ source: "a", target: "d" }, { source: "a", target: "d", degree: 3 }]);
  registerCovered(REGISTRY, "widen-by-one-degree-by-keyboard");
});

test("an end is taken from the node selected on the canvas", async ({ page }) => {
  await serve(page);
  await page.goto("/keyboard/connections-harness.html");
  await page.evaluate((n) => window.__CONNECTIONS__?.select(n as never), node("a", "Ada"));
  await tabTo(page, /^Use the selected node as From$/);
  await page.keyboard.press("Enter");
  await expect(page.getByText("From: Ada")).toBeVisible();
  await page.evaluate((n) => window.__CONNECTIONS__?.select(n as never), node("d", "Dee"));
  await tabTo(page, /^Use the selected node as To$/);
  await page.keyboard.press("Enter");
  await expect(page.getByText("To: Dee")).toBeVisible();
  registerCovered(REGISTRY, "use-the-selected-node-by-keyboard");
});

test("a route is put on the canvas, its nodes marked by degree, and the marks cleared", async ({ page }) => {
  const asked = await serve(page);
  await page.goto("/keyboard/connections-harness.html");
  await chooseBySearch(page, "From", "Ad");
  await chooseBySearch(page, "To", "De");
  await tabTo(page, /^Find connections$/);
  await page.keyboard.press("Enter");
  await tabTo(page, /^Add route 1 at 2 degrees to the canvas$/);
  await page.keyboard.press("Enter");
  await expect(page.getByText("On the canvas")).toBeVisible();
  expect((asked.seeded[0] as { nodes: { id: string }[] }).nodes.map((n) => n.id)).toEqual(["a", "x", "d"]);
  expect(await page.evaluate(() => window.__CONNECTIONS__?.marks)).toEqual([["a", 0], ["x", 1], ["d", 2]]);
  expect(await page.evaluate(() => window.__CONNECTIONS__?.deltas.length)).toBe(1);
  registerCovered(REGISTRY, "add-a-route-to-the-canvas-by-keyboard");

  // Focus went with the Add button when it became "On the canvas"; Tab on from the top.
  await page.locator("body").focus();
  await tabTo(page, /^Clear the degree marks$/, 30);
  await page.keyboard.press("Enter");
  expect(await page.evaluate(() => window.__CONNECTIONS__?.cleared)).toBe(1);
  await expect(page.getByRole("button", { name: "Clear the degree marks" })).toHaveCount(0);
  registerCovered(REGISTRY, "clear-the-degree-marks-by-keyboard");
});

test("every registered Find connections action has its own proving test case above", () => {
  assertAllCovered("CONNECTIONS_ACTIONS", CONNECTIONS_ACTIONS);
});
