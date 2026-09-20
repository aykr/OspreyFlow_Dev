// A scripted, keyboard-only walkthrough — `docs/02_GLASS_FRONTEND.md` §6's
// accessibility floor and `docs/07_BUILD_PLAN.md` Phase 4's exit
// criterion, "Keyboard navigation reaches every canvas action", taken
// literally: this test never calls `page.mouse` or `.click()`. It proves
// the behaviours §6 actually specifies — arrow keys walk edges, Enter
// expands, `\` opens the radial menu as a list — reach real effects (a
// focus change observable through `GlassCanvas`'s own `onFocusChange`/
// `onSelectionChange` props, a real `expand` network call, a real menu in
// the DOM), not just that the key handlers exist.
//
// **Tab's own role, corrected in Phase 7 Stage 4** (`06_DECISIONS.md`'s Stage 4 write-up has the
// full incident): Tab/Shift+Tab are never intercepted by the canvas any more — they behave
// exactly like every other control on the page, which is what lets a keyboard user reach a
// sibling panel beside the canvas at all. Focusing the canvas (by Tab, by click, by
// `.focus()`) establishes a one-node ring immediately, with no keypress needed after arriving.
// Cycling an already-built ring (needed for a lasso-selected set of non-adjacent nodes arrow-walk
// cannot reach) moved to `Ctrl`/`Cmd`+`ArrowRight`/`Left`, the key Tab's release freed up for it.
//
// Pan, zoom and lasso have no keyboard equivalent in §6's own text, and
// none is asserted here — inventing one would be filling a gap the spec
// left silent rather than reading what "every canvas action reachable by
// keyboard" is later grounded to: these behaviours, applied to
// select/walk/expand/context-menu. "Select" is realised as focus (focusing
// the canvas establishes an entry point, arrows move it) — the same
// reasoning the GlassCanvas implementation itself follows (`onFocusChange`'s
// own docstring).
//
// Phase 6a Stage 4: every `test()` below that proves a `CANVAS_ACTIONS` entry calls
// `registerCovered(id)` at the point it does so; the final test asserts none were missed —
// `actionRegistry.ts`'s own docstring has the full reasoning for why this exists now.
import { expect, test } from "@playwright/test";

import { assertAllCovered, CANVAS_ACTIONS, registerCovered } from "./actionRegistry";

declare global {
  interface Window {
    __KEYBOARD__?: {
      focused: string | null;
      selection: string[];
      viewMessagesNodeId: string | null;
    };
  }
}

test("focusing the canvas establishes a starting node when nothing is selected yet", async ({
  page,
}) => {
  await page.goto("/keyboard/harness.html");
  const canvas = page.getByRole("application", { name: "Network canvas" });

  await canvas.focus();

  await expect
    .poll(() => page.evaluate(() => window.__KEYBOARD__?.focused))
    .toBe("n0");
  const selection = await page.evaluate(() => window.__KEYBOARD__?.selection);
  expect(selection).toEqual(["n0"]);
  registerCovered("focus-establishes-ring");
});

test("Tab leaves the canvas and reaches the next real focusable element on the page", async ({
  page,
}) => {
  // The actual fix, proven end to end per rule 12 — the assertion that fails if the canvas's own
  // `onKeyDown` ever goes back to calling `preventDefault()` on Tab. `#after-canvas`
  // (`keyboard/harness.tsx`'s own sentinel) is the real next tab-stop on the page; a keyboard
  // user must be able to reach it from the canvas without a mouse. Two Tabs, not one: the lasso
  // toggle button (`GlassCanvas`'s own first child, always rendered) is itself a real, separate
  // tab-stop inside the canvas region — checked directly, not assumed, when the first Tab landed
  // there instead of on `#after-canvas`.
  await page.goto("/keyboard/harness.html");
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus();
  await expect
    .poll(() => page.evaluate(() => window.__KEYBOARD__?.focused))
    .toBe("n0"); // the canvas's own focus handler already ran — see the test above

  await page.keyboard.press("Tab");
  await expect(page.getByTitle("Lasso select")).toBeFocused();
  await page.keyboard.press("Tab");

  await expect(page.locator("#after-canvas")).toBeFocused();
  registerCovered("tab-leaves-the-canvas");
});

test("arrow keys walk from the focused node to a real neighbour", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus();

  await page.keyboard.press("ArrowRight");

  // The fixture graph is a chain n0—n1—n2—n3: n0's only neighbour is n1,
  // so this has exactly one correct answer, not just "changed to
  // something".
  await expect
    .poll(() => page.evaluate(() => window.__KEYBOARD__?.focused))
    .toBe("n1");
  registerCovered("arrow-walk-forward");
});

test("backslash opens the radial menu as a keyboard-navigable list", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus(); // establishes n0 immediately — see the focus-establishes-ring test above

  await page.keyboard.press("\\");

  const menu = page.locator(".radial-menu__list[role='menu']");
  await expect(menu).toBeVisible();
  await expect(menu.getByRole("menuitem")).not.toHaveCount(0);

  await page.keyboard.press("Escape");
  await expect(menu).toBeHidden();
  registerCovered("backslash-open-menu");
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
  await canvas.focus(); // establishes n0 immediately
  await page.keyboard.press("ArrowRight"); // focus n1 — see the arrow-walk test above

  await page.keyboard.press("Enter");

  await expect.poll(() => expandRequestBody !== null).toBe(true);
  expect(expandRequestBody).toMatchObject({
    request: { node_ids: ["n1"], depth: 1 },
  });
  registerCovered("enter-expand");
});

test("Ctrl+ArrowRight cycles the focused node forward through an existing ring", async ({
  page,
}) => {
  // This is the ring-cycling branch itself (`onKeyDown`'s "ctrlKey/metaKey + ArrowRight/Left &&
  // selected.size > 0"), moved off Tab in Phase 7 Stage 4 once Tab itself was freed to leave the
  // canvas natively (see this file's own header comment).
  await page.goto("/keyboard/harness.html");
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus(); // establishes n0, ring: {n0}
  await page.keyboard.press("ArrowRight"); // focus n1 — walking does not touch the ring
  await page.keyboard.press("Space"); // add n1 — ring: {n0, n1}, focus still n1

  await page.keyboard.press("Control+ArrowRight"); // cycle forward through the ring

  // The ring is a `Set`, insertion order {n0, n1} — cycling forward from n1 wraps to n0.
  await expect
    .poll(() => page.evaluate(() => window.__KEYBOARD__?.focused))
    .toBe("n0");
  registerCovered("ctrl-arrow-cycles-ring");
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
  await canvas.focus(); // establishes n0 in the ring immediately, so no Space needed for it here.
  await page.keyboard.press("ArrowRight"); // focus n1 (n0's only neighbour) — walking does not
  // itself change the ring, only `focused`, which is exactly why Space is needed at all.
  await page.keyboard.press("Space"); // add n1 — ring: {n0, n1}
  registerCovered("space-toggle-ring-membership");

  await expect
    .poll(() => page.evaluate(() => window.__KEYBOARD__?.selection.sort()))
    .toEqual(["n0", "n1"]);

  await page.keyboard.press("\\"); // opens the list menu on n1, the focused node
  const menu = page.locator(".radial-menu__list[role='menu']");
  await expect(menu).toBeVisible();

  // Item order on a `Person` node: `radialMenuItems`' `valid` filter matches an edge type on
  // either its `from` *or* `to` list, so `USES` (from: Person) qualifies here too, alongside
  // `ASSOCIATE_OF` — two edge-type items, not one, both ahead of the manual-link/split pair
  // `radialMenuItems` appends after them. `RadialMenu` focuses the first item (`ASSOCIATE_OF`) on
  // open; two native Tabs (past `USES`) reach "Link to n0". Nothing here calls `preventDefault`
  // on Tab while a menu is open (`onKeyDown`'s own guard).
  await page.keyboard.press("Tab");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("menuitem", { name: /Link to n0/ })).toBeFocused();
  await page.keyboard.press("Enter");

  await expect.poll(() => linkRequestBody !== null).toBe(true);
  expect(linkRequestBody).toMatchObject({ node_a: "n1", node_b: "n0" });
  await expect(menu).toBeHidden(); // RadialMenu closes on select, same as a mouse click
  registerCovered("menu-item-manual-link");
});

test("the radial list also reaches Split, not only Link", async ({ page }) => {
  // Untested before Phase 6a Stage 4: the manual-link test above only ever reaches "Link to n0",
  // never "Split from n0" — a different item, a different route, a different request body.
  await page.goto("/keyboard/harness.html");

  let splitRequestBody: unknown = null;
  await page.route("**/*/resolution/split", async (route) => {
    splitRequestBody = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ seq: 2, op: "reproject", merged: 0, split: 1, affected: 2 }),
    });
  });

  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus(); // establishes n0, ring: {n0}
  await page.keyboard.press("ArrowRight"); // focus n1
  await page.keyboard.press("Space"); // add n1 — ring: {n0, n1}

  await page.keyboard.press("\\");
  const menu = page.locator(".radial-menu__list[role='menu']");
  await expect(menu).toBeVisible();

  // Item order on n1: `ASSOCIATE_OF`, `USES` (see the manual-link test above for why there are two
  // edge-type items on a `Person` node), then "Link to n0", then "Split from n0" —
  // `radialMenuItems`' own push order. Three Tabs past the auto-focused first item reaches it.
  await page.keyboard.press("Tab");
  await page.keyboard.press("Tab");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("menuitem", { name: /Split from n0/ })).toBeFocused();
  await page.keyboard.press("Enter");

  await expect.poll(() => splitRequestBody !== null).toBe(true);
  expect(splitRequestBody).toMatchObject({ node_a: "n1", node_b: "n0" });
  await expect(menu).toBeHidden();
  registerCovered("menu-item-manual-split");
});

test("the radial list's own auto-focused first item is itself reachable and activatable", async ({
  page,
}) => {
  // Untested before Phase 6a Stage 4: "Enter expands" above proves the direct `Enter`
  // key-handler shortcut, never the equivalent edge-type item reached *through* the menu itself
  // — a different code path (`radialMenuItems`' own `expandNode` call), not merely the same
  // behaviour reached two ways.
  await page.goto("/keyboard/harness.html");

  let expandRequestBody: unknown = null;
  await page.route("**/*/expand", async (route) => {
    expandRequestBody = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ delta: { seq: 2, op: "add", nodes: [], edges: [] }, filtered_count: 0 }),
    });
  });

  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus(); // establishes n0, ring: {n0} — no second selected node, so no
  // manual-link/split items compete for the auto-focused first slot.

  await page.keyboard.press("\\");
  const menu = page.locator(".radial-menu__list[role='menu']");
  await expect(menu).toBeVisible();
  await expect(page.getByRole("menuitem", { name: /^ASSOCIATE_OF/ })).toBeFocused();

  await page.keyboard.press("Enter");

  await expect.poll(() => expandRequestBody !== null).toBe(true);
  expect(expandRequestBody).toMatchObject({ request: { node_ids: ["n0"], depth: 1 } });
  await expect(menu).toBeHidden();
  registerCovered("menu-item-expand-by-edge-type");
});

test("the radial list reaches Explain cluster, and the explanation actually renders — CLAUDE.md rule 13", async ({
  page,
}) => {
  // `07_BUILD_PLAN.md` Phase 6a Stage 3 (B10): the same bar the two tests above already set for
  // a canvas action — reachable *and* activatable, not merely present in the DOM. `n2`/`n3` are
  // the harness's own cluster pair (`harness.tsx`'s own `resolution.cluster_id` fixture data);
  // this is a single-node trigger, unlike B11's pair requirement above, since `explain` takes one
  // `cluster_id`, not two node ids.
  await page.goto("/keyboard/harness.html");

  let explainRequestUrl: string | null = null;
  await page.route("**/*/resolution/explain/*", async (route) => {
    explainRequestUrl = route.request().url();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        cluster_id: "n2",
        member_node_ids: ["n2", "n3"],
        pairs: [
          {
            node_a: "n2",
            node_b: "n3",
            edge_type: "SAME_AS",
            score: 0.95,
            model_version: "splink-3.9.9-config-1",
            comparison_vector: null,
            manually_asserted: false,
            meets_threshold: true,
          },
        ],
      }),
    });
  });

  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus(); // establishes n0
  await page.keyboard.press("ArrowRight"); // focus n1
  await page.keyboard.press("ArrowLeft"); // focus n2 — n1's *last* neighbour
  // (`onKeyDown`'s `ArrowLeft`/`ArrowUp` branch picks `neighbours[neighbours.length - 1]`; n1's
  // own neighbour order is `[n0, n2]`, edge-insertion order, so `ArrowRight`'s `neighbours[0]`
  // would walk back to n0 instead).
  await expect
    .poll(() => page.evaluate(() => window.__KEYBOARD__?.focused))
    .toBe("n2");
  registerCovered("arrow-walk-backward"); // the `ArrowLeft`/`ArrowUp` branch itself, distinct from
  // `arrow-walk-forward`'s own `ArrowRight`/`ArrowDown` branch above

  await page.keyboard.press("\\"); // opens the list menu on n2, the focused node
  const menu = page.locator(".radial-menu__list[role='menu']");
  await expect(menu).toBeVisible();

  // Item order: `ASSOCIATE_OF`, `USES` (`radialMenuItems`' own edge-type items — see the
  // manual-link test above for why a `Person` node gets two of them — come before the cluster
  // item), then "Explain cluster". Two native Tabs past the auto-focused first item reaches it,
  // the same navigation shape the manual-link test above already proves.
  await page.keyboard.press("Tab");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("menuitem", { name: "Explain cluster" })).toBeFocused();
  await page.keyboard.press("Enter");

  await expect.poll(() => explainRequestUrl !== null).toBe(true);
  expect(explainRequestUrl).toContain("/resolution/explain/n2");
  await expect(menu).toBeHidden(); // RadialMenu closes on select, same as a mouse click
  registerCovered("menu-item-explain-cluster");

  // Reached the network call; now prove it actually rendered, not just fired — the same bar
  // `explainView.test.ts` sets for the leak-defense filter this overlay's own `Table` is built on.
  await expect(page.getByText("Cluster explanation")).toBeVisible();
  await expect(page.getByRole("cell", { name: "n3" })).toBeVisible();
});

test("Escape dismisses the cluster-explanation overlay, reachable by keyboard alone", async ({
  page,
}) => {
  // Phase 6a Stage 4: found while building the action registry, and fixed rather than left
  // disclosed-only — before this stage, this container's own `onKeyDown` had no exemption for
  // `clusterExplain`, so a keyboard-only analyst who reached this overlay (the same all-keyboard
  // path the test above proves) had no way to close it: `Tab`/arrow presses fought the overlay's
  // own close button for the same reason `radialMenu` needed its own exemption first.
  await page.goto("/keyboard/harness.html");
  await page.route("**/*/resolution/explain/*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ cluster_id: "n2", member_node_ids: ["n2", "n3"], pairs: [] }),
    });
  });

  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus(); // establishes n0
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowLeft"); // focus n2 — see the Explain-cluster test above
  await page.keyboard.press("\\");
  await page.keyboard.press("Tab");
  await page.keyboard.press("Tab"); // past ASSOCIATE_OF, then USES — see the explain-cluster test above
  await expect(page.getByRole("menuitem", { name: "Explain cluster" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByText("Cluster explanation")).toBeVisible();

  await page.keyboard.press("Escape");

  await expect(page.getByText("Cluster explanation")).toBeHidden();
  registerCovered("overlay-dismiss-cluster-explain");
});

test("the radial list reaches View messages on an Endpoint node", async ({ page }) => {
  // `08_ACCEPTANCE_SCENARIOS.md` B6 / Phase 6a Stage 4: single-node trigger, `Endpoint`-type
  // only — `n4` is the harness's own `Endpoint` fixture, one `USES` hop past `n3`.
  await page.goto("/keyboard/harness.html");

  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus(); // establishes n0
  await page.keyboard.press("ArrowRight"); // focus n1
  await page.keyboard.press("ArrowLeft"); // focus n2
  await page.keyboard.press("ArrowLeft"); // focus n3 — n2's own last neighbour
  await expect
    .poll(() => page.evaluate(() => window.__KEYBOARD__?.focused))
    .toBe("n3");
  await page.keyboard.press("ArrowLeft"); // focus n4 — n3's only neighbour
  await expect
    .poll(() => page.evaluate(() => window.__KEYBOARD__?.focused))
    .toBe("n4");

  await page.keyboard.press("\\");
  const menu = page.locator(".radial-menu__list[role='menu']");
  await expect(menu).toBeVisible();
  // `n4` (`Endpoint`) has no cluster and is never a `selected` pair member here, but `USES`
  // (`from: Person, to: Endpoint`) still qualifies as one of its own edge types — `radialMenuItems`'
  // `valid` filter matches on `to` as well as `from`, the same reason a `Person` node gets two
  // edge-type items in the tests above. `USES` is auto-focused first; one Tab reaches "View
  // messages", the only item after it (no other edge type, no cluster, no selected pair).
  await expect(page.getByRole("menuitem", { name: "USES" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("menuitem", { name: "View messages" })).toBeFocused();
  await page.keyboard.press("Enter");

  await expect
    .poll(() => page.evaluate(() => window.__KEYBOARD__?.viewMessagesNodeId))
    .toBe("n4");
  registerCovered("menu-item-view-messages");
});

test("every registered keyboard action has its own proving test case above", () => {
  assertAllCovered(CANVAS_ACTIONS);
});
