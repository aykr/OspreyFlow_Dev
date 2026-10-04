// Selecting several nodes with the mouse (ADR-084 Amendment 1). Unlike the keyboard specs this one
// uses the mouse on purpose: the thing under test is what a modifier key does to a click. The
// keyboard route to a multi-node selection (Space on a focused node) is proved in `keyboard.spec.ts`.
import { expect, test, type Page } from "@playwright/test";

const URL = "/keyboard/harness.html";
// n2 and n3 are one resolution cluster in the fixture and may be drawn as one, and the disconnected n5
// settles under the Layout control that floats over the canvas, so neither is clicked here.
const NODES = ["n0", "n1", "n4"];

const positionOf = (page: Page, id: string) =>
  page.evaluate((nodeId) => window.__CANVAS__?.viewportPositionOf(nodeId), id);

/** Waits until the three nodes stop moving: the layout settles after load, and selecting a node
 * moves the camera, so a position read before either has finished points at empty space. */
async function settled(page: Page) {
  let last = "";
  await expect
    .poll(
      async () => {
        const now = JSON.stringify(await Promise.all(NODES.map((id) => positionOf(page, id))));
        const still = now === last;
        last = now;
        return still;
      },
      { intervals: [300], timeout: 20_000 },
    )
    .toBe(true);
}

async function clickNode(page: Page, id: string, held: ("Shift" | "ControlOrMeta")[] = []) {
  await settled(page);
  const p = await positionOf(page, id);
  if (!p) throw new Error(`no position for ${id}`);
  // The modifier is held through the keyboard, as a person holds it. (Playwright's `modifiers`
  // option on a click was measured to reach the page with neither a keydown nor a flagged click
  // here, so it proves nothing about the canvas.)
  for (const key of held) await page.keyboard.down(key);
  // `viewportPositionOf` answers in page coordinates (the pixel-reading `link-style.spec.ts` relies on it).
  await page.mouse.click(p.x, p.y);
  for (const key of held) await page.keyboard.up(key);
}

const selection = (page: Page) => page.evaluate(() => [...(window.__KEYBOARD__?.selection ?? [])].sort());

test("Shift+click adds a node to the selection and Shift+click again removes it; a plain click replaces", async ({
  page,
}) => {
  await page.goto(URL);
  await clickNode(page, "n0");
  expect(await selection(page)).toEqual(["n0"]);
  await clickNode(page, "n4", ["Shift"]);
  expect(await selection(page)).toEqual(["n0", "n4"]);
  await clickNode(page, "n4", ["Shift"]);
  expect(await selection(page)).toEqual(["n0"]);
  await clickNode(page, "n4", ["ControlOrMeta"]); // the modifier that already worked still does
  expect(await selection(page)).toEqual(["n0", "n4"]);
  await clickNode(page, "n1");
  expect(await selection(page)).toEqual(["n1"]);
});
