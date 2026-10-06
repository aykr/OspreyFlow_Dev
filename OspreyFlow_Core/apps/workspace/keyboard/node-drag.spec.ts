// Moving a node with the pointer (owner, 6 October 2026: "When I select a node I need the ability to
// move it around, it seems fixed at the moment"). A pointer test, outside the keyboard registry; the
// keyboard route is Shift with an arrow key (`keyboard.spec.ts`).
import { expect, test, type Page } from "@playwright/test";

import { layoutSettled } from "./layoutSettled";

declare global {
  interface Window {
    __KEYBOARD__?: { selection: string[] };
  }
}

const at = (page: Page, id: string) => page.evaluate((n) => window.__CANVAS__?.viewportPositionOf(n) ?? null, id);

async function drag(page: Page, id: string, dx: number, dy: number) {
  const box = (await page.getByRole("application", { name: "Network canvas" }).boundingBox())!;
  const from = (await at(page, id))!;
  await page.mouse.move(box.x + from.x, box.y + from.y);
  await page.mouse.down();
  await page.mouse.move(box.x + from.x + dx / 2, box.y + from.y + dy / 2, { steps: 4 });
  await page.mouse.move(box.x + from.x + dx, box.y + from.y + dy, { steps: 4 });
  await page.mouse.up();
}

test("dragging a node moves it, and the camera stays where it was", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  await layoutSettled(page, ["n3", "n0"]);
  const before = (await at(page, "n3"))!;
  const other = (await at(page, "n0"))!;
  await drag(page, "n3", 60, -40);
  const after = (await at(page, "n3"))!;
  expect(after.x - before.x).toBeGreaterThan(50);
  expect(before.y - after.y).toBeGreaterThan(30);
  // A pan would have moved every node; only the dragged one moved.
  const otherAfter = (await at(page, "n0"))!;
  expect(Math.abs(otherAfter.x - other.x)).toBeLessThan(2);
  expect(Math.abs(otherAfter.y - other.y)).toBeLessThan(2);
});

test("dragging a selected node moves the whole selection together", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  await page.getByRole("application", { name: "Network canvas" }).focus();
  await expect.poll(() => page.evaluate(() => window.__KEYBOARD__?.selection)).toEqual(["n0"]);
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press(" ");
  await expect.poll(() => page.evaluate(() => window.__KEYBOARD__?.selection.length)).toBe(2);
  const [first, second] = (await page.evaluate(() => window.__KEYBOARD__!.selection)) as [string, string];
  const outside = ["n0", "n1", "n2", "n3"].find((id) => id !== first && id !== second)!;
  await layoutSettled(page, [first, second, outside]);
  const a = (await at(page, first))!;
  const b = (await at(page, second))!;
  const c = (await at(page, outside))!;
  await drag(page, first, 50, 30);
  const a2 = (await at(page, first))!;
  const b2 = (await at(page, second))!;
  const c2 = (await at(page, outside))!;
  // A node outside the selection stays put: this is not a pan of the whole view.
  expect(Math.abs(c2.x - c.x)).toBeLessThan(2);
  expect(a2.x - a.x).toBeGreaterThan(40);
  expect(b2.x - b.x).toBeGreaterThan(40);
  expect(Math.abs(a2.x - a.x - (b2.x - b.x))).toBeLessThan(3); // moved together
  // The drag is not also a click that changes the selection.
  expect(await page.evaluate(() => window.__KEYBOARD__?.selection.length)).toBe(2);
});

test("a node moved by hand stays where it was put when an expansion re-arranges the rest", async ({ page }) => {
  const meta = {
    provenance: { state: "asserted", sources: [], first_seen: "2026-01-01T00:00:00Z" },
    handling: { classification: "OFFICIAL", handling_code: "P", originator: "unit-1", owning_unit: "unit-1" },
    audit: { created_at: "2026-01-01T00:00:00Z", created_by: "fixture" },
  };
  await page.route("**/*/expand", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        delta: {
          seq: 2,
          op: "add",
          nodes: ["x1", "x2"].map((id) => ({ id, type: "Person", properties: { family_name: id }, ...meta })),
          edges: ["x1", "x2"].map((id) => ({ id: `e-${id}`, type: "ASSOCIATE_OF", source: "n1", target: id, ...meta })),
        },
        filtered_count: 0,
      }),
    }),
  );
  await page.route("**/*/expand/preview", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ candidate_node_count: 2, candidate_edge_count: 2 }),
    }),
  );
  await page.goto("/keyboard/harness.html");
  // Circular arranges every node again when nodes arrive; a placed one must not move.
  await page.getByRole("combobox", { name: "Layout" }).selectOption("circular");
  await layoutSettled(page, ["n3", "n0"]);
  await drag(page, "n3", -70, -50);
  const placed = (await at(page, "n3"))!;
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus();
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("Enter"); // expand n1: two nodes arrive and the circle is re-arranged
  await expect.poll(() => page.evaluate(() => window.__CANVAS__?.viewportPositionOf("x2") !== null)).toBe(true);
  await layoutSettled(page, ["n3", "x2"]);
  const after = (await at(page, "n3"))!;
  expect(Math.abs(after.x - placed.x)).toBeLessThan(2);
  expect(Math.abs(after.y - placed.y)).toBeLessThan(2);
});

test("a right-click on a selection opens its menu without dragging, and the menu can be used (owner, 6 October 2026)", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  await page.getByRole("application", { name: "Network canvas" }).focus();
  await expect.poll(() => page.evaluate(() => window.__KEYBOARD__?.selection)).toEqual(["n0"]);
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press(" ");
  await expect.poll(() => page.evaluate(() => window.__KEYBOARD__?.selection.length)).toBe(2);
  const [first, second] = (await page.evaluate(() => window.__KEYBOARD__!.selection)) as [string, string];
  await layoutSettled(page, [first, second]);
  const a = (await at(page, first))!;
  const b = (await at(page, second))!;
  const box = (await page.getByRole("application", { name: "Network canvas" }).boundingBox())!;
  await page.mouse.click(box.x + a.x, box.y + a.y, { button: "right" });
  const item = page.getByRole("menuitem").first();
  await expect(item).toBeVisible();
  // Travel to the menu: nothing on the canvas follows the pointer.
  const target = (await item.boundingBox())!;
  await page.mouse.move(target.x + target.width / 2, target.y + target.height / 2, { steps: 8 });
  const a2 = (await at(page, first))!;
  const b2 = (await at(page, second))!;
  expect(Math.abs(a2.x - a.x) + Math.abs(a2.y - a.y)).toBeLessThan(2);
  expect(Math.abs(b2.x - b.x) + Math.abs(b2.y - b.y)).toBeLessThan(2);
  // And the item takes the click.
  await expect(item).toBeEnabled();
  await page.mouse.click(target.x + target.width / 2, target.y + target.height / 2);
  await expect(page.getByRole("menuitem")).toHaveCount(0);
});
