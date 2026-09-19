// A scripted, keyboard-only walkthrough — `docs/02_GLASS_FRONTEND.md` §6's
// accessibility floor and `docs/07_BUILD_PLAN.md` Phase 4's exit
// criterion, "Keyboard navigation reaches every canvas action", taken
// literally: this test never calls `page.mouse` or `.click()`. It proves
// the four behaviours §6 actually specifies — "Tab moves between nodes in
// the current selection ring, arrow keys walk edges, Enter expands, `\`
// opens the radial menu as a list" — reach real effects (a focus change
// observable through `GlassCanvas`'s own `onFocusChange`/
// `onSelectionChange` props, a real `expand` network call, a real menu in
// the DOM), not just that the key handlers exist.
//
// Pan, zoom and lasso have no keyboard equivalent in §6's own text, and
// none is asserted here — inventing one would be filling a gap the spec
// left silent rather than reading what "every canvas action reachable by
// keyboard" is later grounded to: these four behaviours, applied to
// select/walk/expand/context-menu. "Select" is realised as focus (Tab to
// an entry point, arrows to move it) — the same reasoning the GlassCanvas
// implementation itself follows (`onFocusChange`'s own docstring).
import { expect, test } from "@playwright/test";

declare global {
  interface Window {
    __KEYBOARD__?: { focused: string | null; selection: string[] };
  }
}

test("Tab establishes a starting node when nothing is selected yet", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus();

  await page.keyboard.press("Tab");

  await expect
    .poll(() => page.evaluate(() => window.__KEYBOARD__?.focused))
    .toBe("n0");
  const selection = await page.evaluate(() => window.__KEYBOARD__?.selection);
  expect(selection).toEqual(["n0"]);
});

test("arrow keys walk from the focused node to a real neighbour", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus();
  await page.keyboard.press("Tab"); // focus n0

  await page.keyboard.press("ArrowRight");

  // The fixture graph is a chain n0—n1—n2—n3: n0's only neighbour is n1,
  // so this has exactly one correct answer, not just "changed to
  // something".
  await expect
    .poll(() => page.evaluate(() => window.__KEYBOARD__?.focused))
    .toBe("n1");
});

test("backslash opens the radial menu as a keyboard-navigable list", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus();
  await page.keyboard.press("Tab"); // focus n0

  await page.keyboard.press("\\");

  const menu = page.locator(".radial-menu__list[role='menu']");
  await expect(menu).toBeVisible();
  await expect(menu.getByRole("menuitem")).not.toHaveCount(0);

  await page.keyboard.press("Escape");
  await expect(menu).toBeHidden();
});

test("Enter expands the focused node — a real network call, not a stub", async ({ page }) => {
  await page.goto("/keyboard/harness.html");

  let expandRequestBody: unknown = null;
  await page.route("**/*/expand", async (route) => {
    expandRequestBody = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        delta: { seq: 2, op: "add", nodes: [], edges: [] },
        filtered_count: 0,
      }),
    });
  });

  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus();
  await page.keyboard.press("Tab"); // focus n0
  await page.keyboard.press("ArrowRight"); // focus n1 — see the arrow-walk test above

  await page.keyboard.press("Enter");

  await expect.poll(() => expandRequestBody !== null).toBe(true);
  expect(expandRequestBody).toMatchObject({
    request: { node_ids: ["n1"], depth: 1 },
  });
});

test("Space, then the radial list, reaches manual link — a real POST, not a stub", async ({
  page,
}) => {
  // `07_BUILD_PLAN.md` Phase 6a Stage 1 (B11): the same bar the "Enter
  // expands" test above already sets — the backslash test alone only
  // proves the menu opens as a keyboard-navigable list, never that an item
  // in it is reachable and activatable. This is the first test in this
  // file to select a *second* node by keyboard at all: `Space` is this
  // build's own proposed resolution of `02_GLASS_FRONTEND.md` §6's silence
  // on building a multi-node ring without a mouse (see `GlassCanvas.tsx`'s
  // own `onKeyDown` comment).
  await page.goto("/keyboard/harness.html");

  let linkRequestBody: unknown = null;
  await page.route("**/*/resolution/link", async (route) => {
    linkRequestBody = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ seq: 2, op: "reproject", merged: 1, split: 0, affected: 2 }),
    });
  });

  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus();
  await page.keyboard.press("Tab"); // focus n0 — Tab's own entry point already puts it in the
  // ring (`onKeyDown`'s "Tab && selected.size === 0" branch), so no Space needed for it here.
  await page.keyboard.press("ArrowRight"); // focus n1 (n0's only neighbour) — walking does not
  // itself change the ring, only `focused`, which is exactly why Space is needed at all.
  await page.keyboard.press("Space"); // add n1 — ring: {n0, n1}

  await expect
    .poll(() => page.evaluate(() => window.__KEYBOARD__?.selection.sort()))
    .toEqual(["n0", "n1"]);

  await page.keyboard.press("\\"); // opens the list menu on n1, the focused node
  const menu = page.locator(".radial-menu__list[role='menu']");
  await expect(menu).toBeVisible();

  // Item order: the one declared edge type first, then "Link to n0" —
  // `GlassCanvas.tsx`'s own `radialMenuItems` appends the manual-link/split
  // items after the edge-type ones. One native Tab reaches it; `RadialMenu`
  // itself focuses the first item on open, and nothing here calls
  // `preventDefault` on Tab while a menu is open (`onKeyDown`'s own guard).
  await page.keyboard.press("Tab");
  await expect(page.getByRole("menuitem", { name: /Link to n0/ })).toBeFocused();
  await page.keyboard.press("Enter");

  await expect.poll(() => linkRequestBody !== null).toBe(true);
  expect(linkRequestBody).toMatchObject({ node_a: "n1", node_b: "n0" });
  await expect(menu).toBeHidden(); // RadialMenu closes on select, same as a mouse click
});
