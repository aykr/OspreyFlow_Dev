// A scripted, keyboard-only walkthrough — `spec/02_GLASS_FRONTEND.md` §6's
// accessibility floor and this phase's exit
// criterion, "Keyboard navigation reaches every canvas action", taken
// literally: this test never calls `page.mouse` or `.click()`. It proves
// the behaviours §6 actually specifies — arrow keys walk edges, Enter
// expands, `\` opens the radial menu as a list — reach real effects (a
// focus change observable through `GlassCanvas`'s own `onFocusChange`/
// `onSelectionChange` props, a real `expand` network call, a real menu in
// the DOM), not just that the key handlers exist.
//
// **Tab's own role, corrected here** (see the surrounding fix for the
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
import { expect, test, type Locator, type Page } from "@playwright/test";

import { assertAllCovered, CANVAS_ACTIONS, registerCovered } from "./actionRegistry";

/** Tabs until `target` is focused — never a counted number of Tabs, which breaks whenever the
 * menu gains an item (seen 9 October 2026: *Set picture…* and the Depicts link row joined the
 * node menu and every counted walk in this file went red at once). */
async function tabUntilFocused(page: Page, target: Locator, max = 12): Promise<void> {
  await expect(target).toBeVisible();
  for (let i = 0; i < max && !(await target.evaluate((el) => el === document.activeElement)); i++) {
    await page.keyboard.press("Tab");
  }
  await expect(target).toBeFocused();
}
import { layoutSettled } from "./layoutSettled";
import { readPng } from "./pngPixels";

// An expansion now asks the Conduit how big it would be before it goes ahead
// (`canvas/expansionGate.ts`, ADR-060 Amendment 1). The harness has no Conduit, so a test that
// proves an expand reaches the network answers that question first. Small, so it proceeds.
async function stubSmallExpansionPreview(page: Page): Promise<void> {
  await page.route("**/*/expand/preview", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ candidate_node_count: 3, candidate_edge_count: 0 }),
    });
  });
}

declare global {
  interface Window {
    __KEYBOARD__?: {
      focused: string | null;
      selection: string[];
      viewMessagesNodeId: string | null;
      selectedEdge: string | null;
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
  registerCovered("CANVAS_ACTIONS", "focus-establishes-ring");
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
  // The canvas region holds several real tab-stops of its own (the lasso toggle, the Layout menu
  // and its Arrange button, the selection bar, Clear view, the zoom cluster and the legend), so the way out is "keep pressing Tab and
  // arrive", not an exact count that every new control would break. Bounded, so a real trap fails.
  for (let presses = 0; presses < 24; presses++) {
    if (await page.locator("#after-canvas").evaluate((el) => el === document.activeElement)) break;
    await page.keyboard.press("Tab");
  }

  await expect(page.locator("#after-canvas")).toBeFocused();
  registerCovered("CANVAS_ACTIONS", "tab-leaves-the-canvas");
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
  registerCovered("CANVAS_ACTIONS", "arrow-walk-forward");
});

test("Ctrl+Shift+Arrow reaches a node arrow-walk cannot, and Space pairs the two", async ({
  page,
}) => {
  // **The `CLAUDE.md` rule 13 gap round 12b found, and its closure.** `Explain cluster` and
  // `Find paths to` are both gated on `selected.size === 2`. Until round 12d there was no
  // keyboard route to a two-node selection over two *non-adjacent* nodes: arrow-walk follows
  // `graph.neighbors`, Ctrl/Cmd+Arrow cycles within the selection, and Space toggles only what is
  // focused. Two entities found by identifier — how an analyst reaches Fixture Corp's resolution
  // pair — are exactly that case, so both actions were mouse-only in practice while this registry
  // recorded them as covered.
  //
  // `n5` is the fixture's own disconnected node (`harness.tsx`), which is what makes the first
  // half of this test a real negative rather than a formality.
  await page.goto("/keyboard/harness.html");
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus(); // establishes n0

  // 1. Arrow-walk genuinely cannot get there. Generously more presses than the graph has nodes,
  //    so this fails if a future change ever *does* make arrow-walk leave the component.
  for (let i = 0; i < 12; i++) await page.keyboard.press("ArrowRight");
  expect(
    await page.evaluate(() => window.__KEYBOARD__?.focused),
    "arrow-walk reached the disconnected node — it follows edges, so it should not be able to",
  ).not.toBe("n5");

  // 2. One pass, no re-focusing: the canvas's own `onFocus` re-establishes the ring, so calling
  //    `focus()` again mid-test would silently discard the selection being built — found exactly
  //    that way. Focus once, select here, walk, select there.
  await canvas.focus();
  expect(await page.evaluate(() => window.__KEYBOARD__?.focused)).toBe("n0");
  // No Space here: focusing the canvas *already* establishes a ring containing n0 (the
  // `focus-establishes-ring` case above asserts exactly that), so a Space at this point would
  // toggle it back *out* — which is what the first version of this test did, leaving a
  // one-element selection and a confusing failure. n0 is already selected; walk and add n5.
  let reached = false;
  for (let i = 0; i < 12 && !reached; i++) {
    await page.keyboard.press("Control+Shift+ArrowRight");
    reached = (await page.evaluate(() => window.__KEYBOARD__?.focused)) === "n5";
  }
  expect(
    reached,
    "Ctrl+Shift+Arrow never reached the disconnected node, so the working-set walk is not working",
  ).toBe(true);
  await page.keyboard.press(" ");

  // 3. A two-node selection over two nodes that share no edge — the thing that had no keyboard
  //    route at all before this branch existed.
  const selection = await page.evaluate(() => window.__KEYBOARD__?.selection);
  expect(new Set(selection)).toEqual(new Set(["n0", "n5"]));

  // 4. Which is the whole point: the two-node-only menu items are now keyboard-reachable for a
  //    pair that shares no edge.
  await page.keyboard.press("\\");
  const menu = page.locator(".radial-menu__list[role='menu']");
  await expect(menu).toBeVisible();
  await expect(menu.getByRole("menuitem", { name: /Find paths to/ })).toBeVisible();

  registerCovered("CANVAS_ACTIONS", "ctrl-shift-arrow-walks-every-node");
});

// 9 October 2026: the pair's actions read "Link to 01M46CSD…", the other node's id. Every fixture
// person but n5 is labelled by its id, so this asks the menu on n0 about n5 ("n5, Zed").
test("a pair's actions name the other node as the canvas labels it, not by its id", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus(); // n0, in the ring
  for (let i = 0; i < 12; i++) {
    await page.keyboard.press("Control+Shift+ArrowRight");
    if ((await page.evaluate(() => window.__KEYBOARD__?.focused)) === "n5") break;
  }
  await page.keyboard.press(" "); // ring: {n0, n5}
  for (let i = 0; i < 12; i++) {
    await page.keyboard.press("Control+Shift+ArrowRight");
    if ((await page.evaluate(() => window.__KEYBOARD__?.focused)) === "n0") break;
  }
  expect(await page.evaluate(() => window.__KEYBOARD__?.focused)).toBe("n0");
  await page.keyboard.press("\\");
  const menu = page.locator(".radial-menu__list[role='menu']");
  for (const verb of ["Link to", "Split from", "Find paths to"]) {
    await expect(menu.getByRole("menuitem", { name: `${verb} n5, Zed` })).toBeVisible();
  }
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
  registerCovered("CANVAS_ACTIONS", "backslash-open-menu");
});

// Seen on the owner's deployment, 8 October 2026: every entry read `(…)` for ever and no preview
// was asked for, because the deployed image's address is `""` (this origin, through nginx) and
// the canvas took an empty address for no Conduit. The harness's own address had never been empty.
for (const [shape, query, origin] of [
  ["the deployed same-origin address", "?api=same-origin", "http://localhost:5185/v1/"],
  ["an explicit address", "", "http://keyboard-test.invalid/v1/"],
] as const) {
  test(`the menu shows each link type's count, asked of the Conduit at ${shape}`, async ({ page }) => {
    const asked: string[] = [];
    await page.route("**/v1/investigations/keyboard-fixture/expand/preview", async (route) => {
      asked.push(route.request().url());
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ candidate_node_count: 500, candidate_edge_count: 0 }),
      });
    });
    await page.goto(`/keyboard/harness.html${query}`);
    const canvas = page.getByRole("application", { name: "Network canvas" });
    await canvas.focus();
    await page.keyboard.press("\\");

    const counts = page.locator(".radial-menu__list[role='menu'] .radial-menu__count");
    await expect(counts.first()).toHaveText(/^\s*\(\d+\)$/);
    expect(asked.length).toBeGreaterThan(0);
    expect(asked.every((url) => url.startsWith(origin))).toBe(true);
  });
}

test("Enter expands the focused node — a real network call, not a stub", async ({ page }) => {
  await page.goto("/keyboard/harness.html");

  await stubSmallExpansionPreview(page);
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
  registerCovered("CANVAS_ACTIONS", "enter-expand");
});

test("an expansion leaves the view and the settled nodes where they were (ADR-060 Amendment 2)", async ({
  page,
}) => {
  await page.goto("/keyboard/harness.html");
  await stubSmallExpansionPreview(page);
  const person = (id: string) => ({
    id,
    type: "Person",
    properties: { family_name: id },
    provenance: { state: "asserted", sources: [], first_seen: "2026-01-01T00:00:00Z" },
    handling: { classification: "OFFICIAL", handling_code: "P", originator: "unit-1", owning_unit: "unit-1" },
    audit: { created_at: "2026-01-01T00:00:00Z", created_by: "fixture" },
  });
  const link = (id: string, source: string, target: string) => ({
    id,
    type: "ASSOCIATE_OF",
    source,
    target,
    provenance: { state: "asserted", sources: [], first_seen: "2026-01-01T00:00:00Z" },
    handling: { classification: "OFFICIAL", handling_code: "P", originator: "unit-1", owning_unit: "unit-1" },
    audit: { created_at: "2026-01-01T00:00:00Z", created_by: "fixture" },
  });
  await page.route("**/*/expand", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        delta: {
          seq: 2,
          op: "add",
          nodes: [person("x1"), person("x2")],
          edges: [link("ex1", "n1", "x1"), link("ex2", "n1", "x2")],
        },
        filtered_count: 0,
      }),
    });
  });
  const positions = () =>
    page.evaluate((ids) => ids.map((id) => window.__CANVAS__?.viewportPositionOf(id)), ["n0", "n1", "n2", "n3", "n4"]);
  const camera = () => page.evaluate(() => window.__CANVAS__?.cameraState());

  // Let the first layout settle, then move the camera as an analyst would, by zooming in.
  let last = "";
  await expect
    .poll(async () => {
      const now = JSON.stringify(await positions());
      const still = now === last;
      last = now;
      return still;
    }, { intervals: [300], timeout: 20_000 })
    .toBe(true);
  const canvas = page.getByRole("application", { name: "Network canvas" });
  const box = (await canvas.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.wheel(0, -300);
  await page.waitForTimeout(600);
  const cameraBefore = await camera();
  expect(cameraBefore!.ratio).toBeLessThan(1);
  const before = await positions();

  await canvas.focus();
  await page.keyboard.press("ArrowRight"); // focus n1
  await page.keyboard.press("Enter"); // expand it: x1 and x2 arrive beside it
  await expect.poll(() => page.evaluate(() => window.__CANVAS__?.viewportPositionOf("x2") !== null)).toBe(true);
  await page.waitForTimeout(1200); // past the layout's delay and its animation

  // The camera did not move or re-zoom by itself, and the nodes that were already settled stayed put.
  expect(await camera()).toEqual(cameraBefore);
  const after = await positions();
  for (let i = 0; i < before.length; i++) {
    expect(Math.abs(after[i]!.x - before[i]!.x), `node ${i} x`).toBeLessThan(1);
    expect(Math.abs(after[i]!.y - before[i]!.y), `node ${i} y`).toBeLessThan(1);
  }
  registerCovered("CANVAS_ACTIONS", "an-expansion-leaves-the-view-and-the-settled-nodes-where-they-were");
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
  registerCovered("CANVAS_ACTIONS", "ctrl-arrow-cycles-ring");
});

test("Space, then the radial list, reaches manual link — a real POST, not a stub", async ({
  page,
}) => {
  // B11: the same bar the "Enter
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
  registerCovered("CANVAS_ACTIONS", "space-toggle-ring-membership");

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
  await tabUntilFocused(page, page.getByRole("menuitem", { name: /Link to n0/ }));
  await page.keyboard.press("Enter");

  await expect.poll(() => linkRequestBody !== null).toBe(true);
  expect(linkRequestBody).toMatchObject({ node_a: "n1", node_b: "n0" });
  await expect(menu).toBeHidden(); // RadialMenu closes on select, same as a mouse click
  registerCovered("CANVAS_ACTIONS", "menu-item-manual-link");
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
  await tabUntilFocused(page, page.getByRole("menuitem", { name: /Split from n0/ }));
  await page.keyboard.press("Enter");

  await expect.poll(() => splitRequestBody !== null).toBe(true);
  expect(splitRequestBody).toMatchObject({ node_a: "n1", node_b: "n0" });
  await expect(menu).toBeHidden();
  registerCovered("CANVAS_ACTIONS", "menu-item-manual-split");
});

test("the radial list's own auto-focused first item is itself reachable and activatable", async ({
  page,
}) => {
  // Untested before Phase 6a Stage 4: "Enter expands" above proves the direct `Enter`
  // key-handler shortcut, never the equivalent edge-type item reached *through* the menu itself
  // — a different code path (`radialMenuItems`' own `expandNode` call), not merely the same
  // behaviour reached two ways.
  await page.goto("/keyboard/harness.html");

  await stubSmallExpansionPreview(page);
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
  await expect(page.getByRole("menuitem", { name: /^Associate of/ })).toBeFocused();

  await page.keyboard.press("Enter");

  await expect.poll(() => expandRequestBody !== null).toBe(true);
  expect(expandRequestBody).toMatchObject({ request: { node_ids: ["n0"], depth: 1 } });
  await expect(menu).toBeHidden();
  registerCovered("CANVAS_ACTIONS", "menu-item-expand-by-edge-type");
});

test("the radial list reaches Explain cluster, and the explanation actually renders end to end", async ({
  page,
}) => {
  // B10: the same bar the two tests above already set for
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
  registerCovered("CANVAS_ACTIONS", "arrow-walk-backward"); // the `ArrowLeft`/`ArrowUp` branch itself, distinct from
  // `arrow-walk-forward`'s own `ArrowRight`/`ArrowDown` branch above

  await page.keyboard.press("\\"); // opens the list menu on n2, the focused node
  const menu = page.locator(".radial-menu__list[role='menu']");
  await expect(menu).toBeVisible();

  // Item order: `ASSOCIATE_OF`, `USES` (`radialMenuItems`' own edge-type items — see the
  // manual-link test above for why a `Person` node gets two of them — come before the cluster
  // item), then "Explain cluster". Two native Tabs past the auto-focused first item reaches it,
  // the same navigation shape the manual-link test above already proves.
  await tabUntilFocused(page, page.getByRole("menuitem", { name: "Explain cluster" }));
  await page.keyboard.press("Enter");

  await expect.poll(() => explainRequestUrl !== null).toBe(true);
  expect(explainRequestUrl).toContain("/resolution/explain/n2");
  await expect(menu).toBeHidden(); // RadialMenu closes on select, same as a mouse click
  registerCovered("CANVAS_ACTIONS", "menu-item-explain-cluster");

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
  await tabUntilFocused(page, page.getByRole("menuitem", { name: "Explain cluster" }));
  await page.keyboard.press("Enter");
  await expect(page.getByText("Cluster explanation")).toBeVisible();

  await page.keyboard.press("Escape");

  await expect(page.getByText("Cluster explanation")).toBeHidden();
  registerCovered("CANVAS_ACTIONS", "overlay-dismiss-cluster-explain");
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
  registerCovered("CANVAS_ACTIONS", "menu-item-view-messages");
});

test("the radial list reaches Mark for suppression, and the mark toggles", async ({ page }) => {
  // **Owner ruling R7 (TENTATIVE, 27 September 2026) — step one of two-step retraction, proven
  // reachable by keyboard.** `CLAUDE.md` rule 13: a canvas action is not reachable-by-keyboard
  // until this file has a case proving it end to end, and its own author owns adding that case in
  // the same change rather than as a follow-up.
  //
  // Both directions are asserted, because "reversible" is R7's own word for it and a mark that
  // cannot be taken off is a different feature from the one that was ruled.
  const calls: { method: string; body: unknown }[] = [];
  await page.route("**/v1/investigations/*/nodes/*/suppression-mark", async (route) => {
    calls.push({
      method: route.request().method(),
      body: route.request().postDataJSON?.() ?? null,
    });
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        node_id: "n4",
        investigation_id: "inv-1",
        marked_by: "analyst-1",
        marked_at: "2026-09-27T00:00:00Z",
        reason: "Marked from the canvas",
      }),
    });
  });

  await page.goto("/keyboard/harness.html");
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus();
  await page.keyboard.press("\\");
  const menu = page.locator(".radial-menu__list[role='menu']");
  await expect(menu).toBeVisible();

  // Offered on every node, so it is always the last item — reached with `End` rather than by
  // counting Tabs, which would otherwise need changing whenever the fixture gains an edge type.
  const item = page.getByRole("menuitem", { name: "Mark for suppression" });
  await expect(item).toBeVisible();
  await item.focus();
  await page.keyboard.press("Enter");

  await expect.poll(() => calls.length).toBe(1);
  expect(calls[0].method).toBe("POST");
  expect(calls[0].body).toMatchObject({ reason: "Marked from the canvas" });

  // Reversible: the same item now offers to take the mark off, and uses DELETE.
  // Re-focusing the canvas first: RadialMenu moves focus onto itself when it opens and does not
  // hand it back on select, so a bare second backslash would land nowhere.
  await canvas.focus();
  await page.keyboard.press("\\");
  await expect(menu).toBeVisible();
  const remove = page.getByRole("menuitem", { name: "Remove suppression mark" });
  await expect(
    remove,
    "the item did not flip after marking, so an analyst has no keyboard route back",
  ).toBeVisible();
  await remove.focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => calls.length).toBe(2);
  expect(calls[1].method).toBe("DELETE");

  registerCovered("CANVAS_ACTIONS", "menu-item-mark-for-suppression");
});

// ADR-105 Amendment 1: Set picture… on a node whose type a picture may depict selects the node
// and hands over to the Inspector's Picture part — proven end to end, since the walkthrough is
// hardcoded and cannot discover a new action on its own (rule 13).
test("Set picture… on a node's menu, by keyboard, selects it and asks for the Picture part", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus();
  const focused = await page.evaluate(() => window.__KEYBOARD__?.focused ?? null);
  await page.keyboard.press("\\");
  const menu = page.locator(".radial-menu__list[role='menu']");
  await expect(menu).toBeVisible();
  const item = page.getByRole("menuitem", { name: "Set picture…" });
  await expect(item).toBeVisible();
  await item.focus();
  await page.keyboard.press("Enter");
  await expect
    .poll(() => page.evaluate(() => window.__KEYBOARD__?.pictureRequested ?? null))
    .toBe(focused);
  expect(await page.evaluate(() => window.__KEYBOARD__?.selection ?? [])).toEqual([focused]);
  registerCovered("CANVAS_ACTIONS", "menu-item-set-picture");
});

// Phase 7 Stage 5 (the pathfinder) — `06_DECISIONS.md` ADR-033. `POST /v1/paths` is intercepted,
// the same "real network call, mocked at the transport" shape every test above already uses; the
// mocked `Path[]` bodies reference only ids already in this file's own fixture (`n0`..`n3`,
// `e0`..`e2`) so `GlassCanvas`'s own seed-if-new step never fires a second network call these
// tests would also need to intercept.
function pathNode(id: string): unknown {
  return {
    id,
    type: "Person",
    properties: { family_name: id },
    provenance: {
      state: "asserted",
      sources: [{ document_id: "fixture-doc", locator: "p.1", excerpt_hash: "a".repeat(64) }],
      first_seen: "2026-01-01T00:00:00Z",
    },
    handling: { classification: "OFFICIAL", handling_code: "P", originator: "unit-1", owning_unit: "unit-1" },
    audit: { created_at: "2026-01-01T00:00:00Z", created_by: "fixture" },
  };
}

function pathEdge(id: string, source: string, target: string): unknown {
  return {
    id,
    type: "ASSOCIATE_OF",
    source,
    target,
    provenance: {
      state: "asserted",
      sources: [{ document_id: "fixture-doc", locator: "p.1", excerpt_hash: "a".repeat(64) }],
      first_seen: "2026-01-01T00:00:00Z",
    },
    handling: { classification: "OFFICIAL", handling_code: "P", originator: "unit-1", owning_unit: "unit-1" },
    audit: { created_at: "2026-01-01T00:00:00Z", created_by: "fixture" },
  };
}

// Shared by all three pathfinder tests below: builds the ring `{n0, n3}` (three hops apart in
// this file's own `n0`—`n1`—`n2`—`n3` chain) and opens the radial menu on `n3`, the focused node.
async function selectN0AndN3ThenOpenMenu(page: import("@playwright/test").Page): Promise<void> {
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus(); // ring: {n0}
  await page.keyboard.press("ArrowRight"); // focus n1
  await page.keyboard.press("ArrowLeft"); // focus n2 (see the View-messages test above)
  await page.keyboard.press("ArrowLeft"); // focus n3
  await page.keyboard.press("Space"); // ring: {n0, n3}
  await expect
    .poll(() => page.evaluate(() => window.__KEYBOARD__?.selection.sort()))
    .toEqual(["n0", "n3"]);

  await page.keyboard.press("\\");
  await expect(page.locator(".radial-menu__list[role='menu']")).toBeVisible();
  // Item order on `n3` (a `Person`): `ASSOCIATE_OF`, `USES` (both qualify, same reasoning the
  // manual-link test above already gives), "Link to n0", "Split from n0", "Find paths to n0" —
  // `radialMenuItems`' own push order. Auto-focused first item; four Tabs reach the last one.
  await tabUntilFocused(page, page.getByRole("menuitem", { name: /Find paths to n0/ }));
}

test("the radial list reaches Find paths, and a real found path renders in its own overlay", async ({
  page,
}) => {
  await page.goto("/keyboard/harness.html");

  let pathsRequestBody: unknown = null;
  await page.route("**/*/v1/investigations/*/paths", async (route) => {
    pathsRequestBody = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          nodes: [pathNode("n3"), pathNode("n2"), pathNode("n1"), pathNode("n0")],
          edges: [pathEdge("e2", "n2", "n3"), pathEdge("e1", "n1", "n2"), pathEdge("e0", "n0", "n1")],
          length: 3,
        },
      ]),
    });
  });

  await selectN0AndN3ThenOpenMenu(page);
  await page.keyboard.press("Enter");

  await expect.poll(() => pathsRequestBody !== null).toBe(true);
  expect(pathsRequestBody).toMatchObject({ source: "n3", target: "n0" });
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByText("Path 1 of 1 (3 hops)")).toBeVisible();
  registerCovered("CANVAS_ACTIONS", "menu-item-find-paths");
});

test("the pathfinder result's own selector cycles which of several found paths is on-path", async ({
  page,
}) => {
  await page.goto("/keyboard/harness.html");

  await page.route("**/*/v1/investigations/*/paths", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          nodes: [pathNode("n3"), pathNode("n2"), pathNode("n1"), pathNode("n0")],
          edges: [pathEdge("e2", "n2", "n3"), pathEdge("e1", "n1", "n2"), pathEdge("e0", "n0", "n1")],
          length: 3,
        },
        { nodes: [pathNode("n1"), pathNode("n0")], edges: [pathEdge("e0", "n0", "n1")], length: 1 },
      ]),
    });
  });

  await selectN0AndN3ThenOpenMenu(page);
  await page.keyboard.press("Enter");
  await expect(page.getByText("Path 1 of 2 (3 hops)")).toBeVisible();

  // `Popover` auto-focuses its own first focusable element (the close button) on open — two Tabs
  // reach "Next path", past "Previous path".
  await page.keyboard.press("Tab");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Next path" })).toBeFocused();
  await page.keyboard.press("Enter");

  await expect(page.getByText("Path 2 of 2 (1 hop)")).toBeVisible();
  registerCovered("CANVAS_ACTIONS", "path-selector-cycles-highlighted-path");
});

test("Escape dismisses the pathfinder result overlay, reachable by keyboard alone", async ({
  page,
}) => {
  await page.goto("/keyboard/harness.html");

  await page.route("**/*/v1/investigations/*/paths", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          nodes: [pathNode("n3"), pathNode("n2"), pathNode("n1"), pathNode("n0")],
          edges: [pathEdge("e2", "n2", "n3"), pathEdge("e1", "n1", "n2"), pathEdge("e0", "n0", "n1")],
          length: 3,
        },
      ]),
    });
  });

  await selectN0AndN3ThenOpenMenu(page);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog")).toBeVisible();

  await page.keyboard.press("Escape");

  await expect(page.getByRole("dialog")).toBeHidden();
  registerCovered("CANVAS_ACTIONS", "overlay-dismiss-pathfinder-result");
});

test("a failed path search announces an error, distinguishable from 'No path found', and Escape dismisses it by keyboard alone", async ({
  page,
}) => {
  await page.goto("/keyboard/harness.html");

  await page.route("**/*/v1/investigations/*/paths", async (route) => {
    await route.fulfill({ status: 500, contentType: "text/plain", body: "internal error" });
  });

  await selectN0AndN3ThenOpenMenu(page);
  await page.keyboard.press("Enter");

  await expect(page.getByRole("alert")).toHaveText("Path search failed (500). Try again.");
  // Not `pathResult`'s own "No path found" — the search did not complete, a different finding.
  await expect(page.getByText("No path found")).not.toBeVisible();

  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toBeHidden();
  registerCovered("CANVAS_ACTIONS", "overlay-dismiss-pathfinder-error");
});

test("a failed manual link announces an error and does not silently leave the analyst believing it was recorded — the priority fix", async ({
  page,
}) => {
  // manualAssertion is a failed *write*, not a failed *read* like expand/explain-cluster below —
  // fixed first, and proven first here, for the same reason: a silently-dropped link leaves the
  // analyst believing it is recorded in the case when it is not.
  await page.goto("/keyboard/harness.html");

  await page.route("**/*/resolution/link", async (route) => {
    await route.fulfill({ status: 500, contentType: "text/plain", body: "internal error" });
  });

  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus();
  await page.keyboard.press("ArrowRight"); // focus n1
  await page.keyboard.press("Space"); // ring: {n0, n1}

  await page.keyboard.press("\\");
  await tabUntilFocused(page, page.getByRole("menuitem", { name: /Link to n0/ }));
  await page.keyboard.press("Enter");

  await expect(page.getByRole("alert")).toHaveText("Link failed (500). Not recorded — try again.");

  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toBeHidden();
  registerCovered("CANVAS_ACTIONS", "overlay-dismiss-action-error");
});

test("a failed expand announces an error instead of leaving the analyst to wonder why nothing happened", async ({
  page,
}) => {
  await page.goto("/keyboard/harness.html");

  await stubSmallExpansionPreview(page);
  await page.route("**/*/expand", async (route) => {
    await route.fulfill({ status: 500, contentType: "text/plain", body: "internal error" });
  });

  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus();
  await page.keyboard.press("Enter"); // direct Enter-expand, no menu open — the fallback anchor path

  await expect(page.getByRole("alert")).toHaveText("Expand failed (500). Try again.");

  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toBeHidden();
  registerCovered("CANVAS_ACTIONS", "overlay-dismiss-action-error");
});

test("a failed explain-cluster announces an error rather than leaving the analyst to wonder why nothing happened", async ({
  page,
}) => {
  await page.goto("/keyboard/harness.html");

  await page.route("**/*/resolution/explain/*", async (route) => {
    await route.fulfill({ status: 500, contentType: "text/plain", body: "internal error" });
  });

  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus(); // n0
  await page.keyboard.press("ArrowRight"); // n1
  await page.keyboard.press("ArrowLeft"); // n2 — the harness's own cluster pair with n3

  await page.keyboard.press("\\");
  // Tab until the item, never a counted number of Tabs: a new menu item (Set picture…, ADR-105
  // Amendment 1) broke the two-Tab version of this walk, exactly the fragility the action
  // registry's own comment warns about.
  await tabUntilFocused(page, page.getByRole("menuitem", { name: "Explain cluster" }));
  await page.keyboard.press("Enter");

  await expect(page.getByRole("alert")).toHaveText("Explain cluster failed (500). Try again.");

  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toBeHidden();
  registerCovered("CANVAS_ACTIONS", "overlay-dismiss-action-error");
});

// Presses Tab until the control is focused, at most `limit` times. The canvas region holds several
// real tab-stops of its own, so a test reaches a control the way a keyboard user does: by tabbing
// to it, never by calling `.focus()` on it.
/** Chooses an option of a focused `<select>` by typing the start of its label. A closed select takes
 * an arrow key differently by platform (macOS opens the menu instead of moving the choice, which is
 * why ArrowDown worked on the Linux build machines and never on the owner's Mac); typing letters
 * selects the first matching option everywhere. `chars` is how much of the label to type: enough to
 * tell it from its neighbours. */
async function chooseOption(
  page: Page,
  select: ReturnType<Page["getByRole"]>,
  value: string,
  chars = 4,
): Promise<void> {
  await expect(select).toBeFocused();
  const label = ((await select.locator(`option[value="${value}"]`).textContent()) ?? "").trim();
  if (label === "") throw new Error(`no option with value ${value}`);
  // The browser joins letters typed within about a second into one search, so a second choice on
  // the same select must not run on from the first.
  await page.waitForTimeout(1100);
  await page.keyboard.type(label.slice(0, chars));
  await expect(select).toHaveValue(value);
}

async function tabTo(page: Page, control: ReturnType<Page["getByRole"]>, limit = 24): Promise<void> {
  for (let presses = 0; presses < limit; presses++) {
    if (await control.evaluate((el) => el === document.activeElement).catch(() => false)) return;
    await page.keyboard.press("Tab");
  }
  await expect(control).toBeFocused();
}

test("Delete takes the selected nodes out of the view, through a real DELETE", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  let body: unknown = null;
  await page.route("**/*/investigations/*/nodes", async (route) => {
    body = route.request().postDataJSON();
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ seq: 5 }) });
  });
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus(); // n0 selected
  await page.keyboard.press("Delete");

  await expect.poll(() => body).toEqual({ node_ids: ["n0"] });
  await expect.poll(() => page.evaluate(() => window.__KEYBOARD__?.selection)).toEqual([]);
  registerCovered("CANVAS_ACTIONS", "delete-removes-selected-nodes");
});

test("Clear view asks first, and clears only after Enter on the confirmation", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  let body: { node_ids: string[] } | null = null;
  await page.route("**/*/investigations/*/nodes", async (route) => {
    body = route.request().postDataJSON();
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ seq: 6 }) });
  });
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus();
  await tabTo(page, page.getByRole("button", { name: "Clear view" }));
  await page.keyboard.press("Enter");
  await expect(page.getByRole("alertdialog", { name: "Clear the view" })).toBeVisible();
  expect(body).toBeNull();

  await tabTo(page, page.getByRole("button", { name: /^Clear all/ }));
  await page.keyboard.press("Enter");

  await expect.poll(() => body?.node_ids.slice().sort()).toEqual(["n0", "n1", "n2", "n3", "n4", "n5"]);
  registerCovered("CANVAS_ACTIONS", "clear-view-by-keyboard");
});

test("Branch selected sends the selected nodes to a new case, by keyboard, and says which", async ({
  page,
}) => {
  await page.goto("/keyboard/harness.html");
  let body: unknown = null;
  await page.route("**/*/investigations/*/branch", async (route) => {
    body = route.request().postDataJSON();
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({ id: "branch-1", name: "Keyboard fixture · 1 selected" }),
    });
  });
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus(); // n0 selected
  await tabTo(page, page.getByRole("button", { name: "Branch to a new case" }));
  await page.keyboard.press("Enter");

  await expect.poll(() => body).toEqual({ node_ids: ["n0"] });
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          (window as unknown as { __KEYBOARD__?: { branchedTo?: string | null } }).__KEYBOARD__
            ?.branchedTo,
      ),
    )
    .toBe("branch-1");
  registerCovered("CANVAS_ACTIONS", "branch-selected-opens-a-new-tab");
});

test("a selected node's own menu offers Branch selected for the whole selection (ADR-084 Amendment 1)", async ({
  page,
}) => {
  await page.goto("/keyboard/harness.html");
  let body: unknown = null;
  await page.route("**/*/investigations/*/branch", async (route) => {
    body = route.request().postDataJSON();
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({ id: "branch-2", name: "Keyboard fixture · 2 selected" }),
    });
  });
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus(); // n0 selected and focused
  await page.keyboard.press("Control+Shift+ArrowRight"); // focus the next node in the working set
  await page.keyboard.press("Space"); // add it to the selection: two selected, the focused one among them
  await expect.poll(() => page.evaluate(() => window.__KEYBOARD__?.selection?.length)).toBe(2);
  await page.keyboard.press("\\");
  const item = page.getByRole("menuitem", { name: /^Branch selected \(2\)/ });
  await expect(item).toBeVisible();
  await item.focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => body).toEqual({ node_ids: expect.arrayContaining(["n0"]) });
  expect((body as { node_ids: string[] }).node_ids).toHaveLength(2);
  registerCovered("CANVAS_ACTIONS", "branch-selected-from-a-selected-nodes-menu");
});

test("Branch selected says so when nothing could be branched, and opens no tab", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  await page.route("**/*/investigations/*/branch", async (route) => {
    await route.fulfill({
      status: 422,
      contentType: "application/json",
      body: JSON.stringify({ error: "nothing_to_branch" }),
    });
  });
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus();
  await tabTo(page, page.getByRole("button", { name: "Branch to a new case" }));
  await page.keyboard.press("Enter");

  await expect(page.getByRole("dialog")).toContainText("None of the selected nodes could be branched.");
  expect(
    await page.evaluate(
      () =>
        (window as unknown as { __KEYBOARD__?: { branchedTo?: string | null } }).__KEYBOARD__
          ?.branchedTo,
    ),
  ).toBeNull();
});

test("the Layout menu is reached by Tab and changed by the arrow keys", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus();
  const layout = page.getByRole("combobox", { name: "Layout" });
  await tabTo(page, layout);
  await expect(layout).toHaveValue("organic");
  await chooseOption(page, layout, "radial");
  registerCovered("CANVAS_ACTIONS", "layout-menu-chooses-layout");
});

test("the Layout menu reaches the Force-directed tree by the arrow keys, and it spreads the nodes out", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus();
  const layout = page.getByRole("combobox", { name: "Layout" });
  await tabTo(page, layout);
  await chooseOption(page, layout, "tree");
  // n3 shares a place with n2 (they are one resolution cluster), so the others are what is checked:
  // every one of them has a place of its own.
  const ids = ["n0", "n1", "n2", "n4", "n5"];
  await expect
    .poll(async () => {
      const at = await page.evaluate((nodes) => nodes.map((id) => window.__CANVAS__?.viewportPositionOf(id) ?? null), ids);
      if (at.some((p) => p === null)) return false;
      for (let i = 0; i < at.length; i++)
        for (let j = i + 1; j < at.length; j++)
          if (Math.hypot(at[i]!.x - at[j]!.x, at[i]!.y - at[j]!.y) < 5) return false;
      return true;
    })
    .toBe(true);
  registerCovered("CANVAS_ACTIONS", "layout-menu-chooses-force-directed-tree");
});

test("the Layout menu reaches Clustered bubbles, draws a bubble for each group, and Bubbles by changes the groups", async ({
  page,
}) => {
  await page.goto("/keyboard/harness.html");
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus();
  const layout = page.getByRole("combobox", { name: "Layout" });
  await tabTo(page, layout);
  await chooseOption(page, layout, "bubbles");
  // By entity type: five people and one endpoint.
  const overlay = page.getByTestId("bubble-overlay");
  await expect(overlay).toContainText("Person (5)");
  await expect(overlay).toContainText("Endpoint (1)");
  const by = page.getByRole("combobox", { name: "Bubbles by" });
  await by.focus();
  await chooseOption(page, by, "community");
  await expect(overlay).toContainText("Community 1");
  await expect(overlay).not.toContainText("Endpoint (1)");
  registerCovered("CANVAS_ACTIONS", "layout-menu-chooses-clustered-bubbles-and-what-they-group-by");
});

test("L steps through the focused node's links and Shift+L goes back, without a mouse", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus(); // n0
  await page.keyboard.press("ArrowRight"); // n1: links e0 and e1
  await page.keyboard.press("l");
  await expect.poll(() => page.evaluate(() => window.__KEYBOARD__?.selectedEdge)).toBe("e0");
  await page.keyboard.press("l");
  await expect.poll(() => page.evaluate(() => window.__KEYBOARD__?.selectedEdge)).toBe("e1");
  await page.keyboard.press("Shift+L");
  await expect.poll(() => page.evaluate(() => window.__KEYBOARD__?.selectedEdge)).toBe("e0");
  // Selecting a link leaves no node selected, so the Inspector shows one thing.
  expect(await page.evaluate(() => window.__KEYBOARD__?.selection)).toEqual([]);
  // Choosing a node ends the link selection, so the Inspector never shows both.
  await page.keyboard.press("Space");
  await expect.poll(() => page.evaluate(() => window.__KEYBOARD__?.selection)).toEqual(["n1"]);
  await expect.poll(() => page.evaluate(() => window.__KEYBOARD__?.selectedEdge)).toBeNull();
  registerCovered("CANVAS_ACTIONS", "l-steps-through-the-focused-nodes-links");
});

test("Delete hides a selected link, and the Show hidden links button brings it back", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus();
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("l");
  await expect.poll(() => page.evaluate(() => window.__KEYBOARD__?.selectedEdge)).toBe("e0");

  await page.keyboard.press("Delete");
  await expect(page.getByRole("button", { name: "Show hidden links (1)" })).toBeVisible();
  await expect.poll(() => page.evaluate(() => window.__KEYBOARD__?.selectedEdge)).toBeNull();
  registerCovered("CANVAS_ACTIONS", "delete-hides-selected-link");

  await tabTo(page, page.getByRole("button", { name: "Show hidden links (1)" }));
  await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: /Show hidden links/ })).toHaveCount(0);
  registerCovered("CANVAS_ACTIONS", "show-hidden-links-by-keyboard");
});

test("a very large expansion asks first; Escape cancels it and nothing is added", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  let expandRequested = false;
  await page.route("**/*/expand/preview", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ candidate_node_count: 1200, candidate_edge_count: 0 }),
    });
  });
  await page.route("**/*/expand", async (route) => {
    expandRequested = true;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ delta: { seq: 2, op: "add", nodes: [], edges: [] }, filtered_count: 0 }),
    });
  });
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus();
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("Enter");

  await expect(page.getByRole("alertdialog", { name: "Large expansion" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("alertdialog", { name: "Large expansion" })).toBeHidden();
  expect(expandRequested).toBe(false);
  registerCovered("CANVAS_ACTIONS", "overlay-dismiss-large-expansion");
});

test("a very large expansion can be accepted by keyboard, and only then does it go ahead", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  let expandBody: unknown = null;
  await page.route("**/*/expand/preview", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ candidate_node_count: 1200, candidate_edge_count: 0 }),
    });
  });
  await page.route("**/*/expand", async (route) => {
    expandBody = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ delta: { seq: 2, op: "add", nodes: [], edges: [] }, filtered_count: 0 }),
    });
  });
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus();
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("alertdialog", { name: "Large expansion" })).toBeVisible();
  expect(expandBody).toBeNull();

  await tabTo(page, page.getByRole("button", { name: /^Add all/ }));
  await page.keyboard.press("Enter");
  await expect.poll(() => expandBody).toMatchObject({ request: { node_ids: ["n1"], depth: 1 } });
  registerCovered("CANVAS_ACTIONS", "large-expansion-add-all-by-keyboard");
});

// Seen 3 October 2026 while testing Communities: with a node focused on the canvas, pressing Enter on
// a button inside the canvas (Communities, Arrange, Collapse all, any other toolbar button)
// also reached the canvas's own key handler, which read it as "expand the focused node" and asked
// the Conduit. A key pressed on a control belongs to that control. Not a registry action: it proves
// that keys on a button do *not* act on the canvas.
test("Enter on a button inside the canvas presses that button and does not expand the focused node", async ({ page }) => {
  await page.goto("/keyboard/harness.html?fixture=communities");
  await settle(page, "a0");
  let asked = 0;
  await page.route("**/*/expand/**", async (route) => {
    asked += 1;
    await route.fulfill({ status: 500, body: "{}" });
  });
  await page.route("**/*/expand", async (route) => {
    asked += 1;
    await route.fulfill({ status: 500, body: "{}" });
  });
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus();
  await expect.poll(() => page.evaluate(() => window.__KEYBOARD__?.focused)).toBe("a0");
  const button = page.getByRole("button", { name: "Communities" });
  await tabTo(page, button);
  await page.keyboard.press("Enter");
  await expect(button).toHaveAttribute("aria-pressed", "true");
  await page.waitForTimeout(600);
  expect(asked).toBe(0);
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

// --- Labels (ADR-076) ------------------------------------------------------------------------
// Six people of one family were each drawn as "Volkov". The analyst chooses, per type, which
// property names its nodes; the choice is kept in this browser only.
test("the Labels control is reached by Tab, and a property chosen with the arrow keys becomes the label", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  // Let the layout stop moving first: while it runs the renderer redraws every frame, which would
  // update a label whether or not the choice told the canvas to draw again.
  await settle(page, "n0");
  await page.waitForTimeout(500);
  // n5 has given names, so its default label is "family, given"; the others have a family name only.
  await expect.poll(() => page.evaluate(() => window.__CANVAS__?.labelOf("n5"))).toBe("n5, Zed");
  await expect.poll(() => page.evaluate(() => window.__CANVAS__?.labelOf("n0"))).toBe("n0");

  await page.getByRole("application", { name: "Network canvas" }).focus();
  const button = page.getByRole("button", { name: "Labels" });
  await tabTo(page, button);
  await page.keyboard.press("Enter");
  await expect(button).toHaveAttribute("aria-expanded", "true");

  const picker = page.getByRole("combobox", { name: "Label for Person" });
  await tabTo(page, picker);
  await chooseOption(page, picker, "given_names", 5);
  await expect.poll(() => page.evaluate(() => window.__CANVAS__?.labelOf("n5"))).toBe("Zed");
  // A person with no given names keeps a name rather than going blank.
  await expect.poll(() => page.evaluate(() => window.__CANVAS__?.labelOf("n0"))).toBe("n0");

  await page.keyboard.press("Escape");
  await expect(picker).toHaveCount(0);
  await expect(button).toBeFocused();
  registerCovered("CANVAS_ACTIONS", "labels-menu-by-keyboard");
});

test("a chosen label is still there after the page is reloaded, and Default puts it back", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  await settle(page, "n0");
  await page.waitForTimeout(500);
  await page.getByRole("button", { name: "Labels" }).click();
  await page.getByRole("combobox", { name: "Label for Person" }).selectOption("given_names");
  await expect.poll(() => page.evaluate(() => window.__CANVAS__?.labelOf("n5"))).toBe("Zed");

  await page.reload();
  await expect.poll(() => page.evaluate(() => window.__CANVAS__?.labelOf("n5"))).toBe("Zed");

  await page.getByRole("button", { name: "Labels" }).click();
  await page.getByRole("combobox", { name: "Label for Person" }).selectOption("Default");
  await expect.poll(() => page.evaluate(() => window.__CANVAS__?.labelOf("n5"))).toBe("n5, Zed");
});

// --- Icons (ADR-079) --------------------------------------------------------------------------

const svgOf = (uri: string | null | undefined) => decodeURIComponent((uri ?? "").replace(/^data:image\/svg\+xml;utf8,/, ""));
const nodeImage = (page: Page, id: string) => page.evaluate((n) => window.__CANVAS__?.nodeImage(n), id);

test("the Icons control is reached by Tab, and a drawing chosen with the arrow keys is drawn in the node", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  await settle(page, "n0");
  // The ontology's own icon is drawn in every person before anything is chosen.
  expect(svgOf(await nodeImage(page, "n0"))).toContain("<g ");
  const first = await nodeImage(page, "n0");

  await page.getByRole("application", { name: "Network canvas" }).focus();
  const button = page.getByRole("button", { name: "Icons" });
  await tabTo(page, button);
  await page.keyboard.press("Enter");
  await expect(button).toHaveAttribute("aria-expanded", "true");

  const picker = page.getByRole("combobox", { name: "Icon for Person" });
  await tabTo(page, picker);
  await chooseOption(page, picker, "glyph:people", 4);
  await expect.poll(() => nodeImage(page, "n0")).not.toBe(first);
  expect(svgOf(await nodeImage(page, "n0"))).toContain("<g ");
  // Only the type chosen for changes: an Endpoint keeps the ontology's.
  expect(svgOf(await nodeImage(page, "n4"))).toContain("<g ");

  await chooseOption(page, picker, "none", 2); // "No…": None
  await expect.poll(async () => svgOf(await nodeImage(page, "n0"))).not.toContain("<g ");

  await page.keyboard.press("Escape");
  await expect(picker).toHaveCount(0);
  await expect(button).toBeFocused();
  registerCovered("CANVAS_ACTIONS", "icons-menu-by-keyboard");
});

test("a picture given from a file is drawn in the shape, and is still there after a reload", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  await settle(page, "n0");
  // ADR-115 Amendment 1: pictures are drawn from the neighbourhood band in (a camera ratio of 0.3),
  // closed in on the node so it stays in view.
  const closeIn = async () => {
    await page.evaluate(() => window.__CANVAS__?.centreOn("n0"));
    await page.waitForTimeout(600);
    await page.evaluate(() => window.__CANVAS__?.zoomTo(0.3));
    await page.waitForTimeout(500);
  };
  await closeIn();
  const box = (await page.getByRole("application", { name: "Network canvas" }).boundingBox())!;
  // The position is read at each check, not once: the view is fitted a moment after the layout
  // settles, and a position kept from before that points beside the node under load.
  const centreOf = async () => {
    const position = await settle(page, "n0");
    const pixels = readPng(await page.screenshot());
    return pixels.at(Math.round(box.x + position!.x), Math.round(box.y + position!.y));
  };
  const isRed = ([r, g, b]: [number, number, number]) => r > 170 && g < 90 && b < 90;
  expect(isRed(await centreOf())).toBe(false);

  const png = await page.evaluate(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 16;
    canvas.height = 16;
    const context = canvas.getContext("2d")!;
    context.fillStyle = "#ff0000";
    context.fillRect(0, 0, 16, 16);
    return canvas.toDataURL("image/png").split(",")[1]!;
  });
  await page.getByRole("button", { name: "Icons" }).click();
  await page.getByLabel("Picture for Person").setInputFiles({
    name: "red.png",
    mimeType: "image/png",
    buffer: Buffer.from(png, "base64"),
  });
  await expect(page.getByRole("combobox", { name: "Icon for Person" })).toHaveValue("image");
  await expect.poll(async () => isRed(await centreOf())).toBe(true);
  // At 100% the node is too small for it: drawn plain, the picture back on closing in.
  await page.evaluate(() => window.__CANVAS__?.zoomTo(1));
  await page.waitForTimeout(500);
  await expect.poll(async () => isRed(await centreOf())).toBe(false);
  await closeIn();

  await page.reload();
  await settle(page, "n0");
  await closeIn();
  const again = await settle(page, "n0");
  await page.waitForTimeout(800);
  const pixels = readPng(await page.screenshot());
  expect(isRed(pixels.at(Math.round(box.x + again!.x), Math.round(box.y + again!.y)))).toBe(true);
  registerCovered("CANVAS_ACTIONS", "icon-picture-from-file");
});

// --- Communities (ADR-066) -------------------------------------------------------------------
// Two groups of five (a0–a4, b0–b4), each a hub with four round it, joined by one link a0—b0.

async function settle(page: Page, id: string) {
  return (await layoutSettled(page, [id]))[id]!;
}

const settleOnce = (page: Page, id: string) => page.evaluate((n) => window.__CANVAS__?.viewportPositionOf(n), id);

const grouped = (page: Page) => page.evaluate(() => (window as unknown as { __GROUPED__?: number }).__GROUPED__);

async function communitiesOn(page: Page) {
  await page.goto("/keyboard/harness.html?fixture=communities");
  // A circle puts every node at a known, separate place; the organic layout draws a group this
  // small too close together for a test of where things are drawn to mean anything.
  await page.getByRole("combobox", { name: "Layout" }).selectOption("circular");
  await expect
    .poll(async () => {
      const [a, b] = await Promise.all([settleOnce(page, "a0"), settleOnce(page, "a3")]);
      return a && b ? Math.hypot(a.x - b.x, a.y - b.y) : 0;
    })
    .toBeGreaterThan(20);
  await settle(page, "a0");
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus();
  await tabTo(page, page.getByRole("button", { name: "Communities" }));
  await page.keyboard.press("Enter");
}

test("the Communities button is reached by Tab, and Enter draws a box round each group", async ({ page }) => {
  await communitiesOn(page);
  await expect(page.getByRole("button", { name: "Communities" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText("2 groups, 0 folded")).toBeVisible();
  await expect(page.getByRole("button", { name: "Fold group of 5 nodes" })).toHaveCount(2);
  registerCovered("CANVAS_ACTIONS", "communities-button-by-keyboard");
});

test("G on a focused node folds its group into one node, and G on that node opens it again", async ({ page }) => {
  await communitiesOn(page);
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus();
  await page.keyboard.press("Home").catch(() => undefined);
  await expect.poll(() => page.evaluate(() => window.__KEYBOARD__?.focused)).toBe("a0");

  await page.keyboard.press("g");
  await expect.poll(() => grouped(page)).toBe(5);
  await expect(page.getByText("2 groups, 1 folded")).toBeVisible();

  await page.keyboard.press("g");
  await expect.poll(() => grouped(page)).toBe(0);
  registerCovered("CANVAS_ACTIONS", "g-folds-and-opens-the-focused-nodes-group");
});

test("a box's own button folds that group, reached by Tab", async ({ page }) => {
  await communitiesOn(page);
  const fold = page.getByRole("button", { name: "Fold group of 5 nodes" }).first();
  await tabTo(page, fold, 24);
  await page.keyboard.press("Enter");
  await expect.poll(() => grouped(page)).toBe(5);
  registerCovered("CANVAS_ACTIONS", "box-fold-button-by-keyboard");
});

test("Collapse all and Expand all fold and open every group, by keyboard", async ({ page }) => {
  await communitiesOn(page);
  await tabTo(page, page.getByRole("button", { name: "Collapse all" }), 24);
  await page.keyboard.press("Enter");
  await expect.poll(() => grouped(page)).toBe(10);
  await expect(page.getByText("2 groups, 2 folded")).toBeVisible();
  await tabTo(page, page.getByRole("button", { name: "Expand all" }), 24);
  await page.keyboard.press("Enter");
  await expect.poll(() => grouped(page)).toBe(0);
  registerCovered("CANVAS_ACTIONS", "collapse-all-and-expand-all-by-keyboard");
});

// The next cases are about what is drawn, not about a key, so they sit outside the registry.

test("a folded group is drawn as one node: its members are drawn where the group is, and come back when it opens", async ({ page }) => {
  await communitiesOn(page);
  const before = { a0: await settle(page, "a0"), a3: await settle(page, "a3"), b2: await settle(page, "b2") };
  expect(Math.hypot(before.a0!.x - before.a3!.x, before.a0!.y - before.a3!.y)).toBeGreaterThan(5);

  await page.getByRole("button", { name: "Collapse all" }).click();
  await expect.poll(() => grouped(page)).toBe(10);
  await page.waitForTimeout(400);
  const folded = { a0: await settle(page, "a0"), a3: await settle(page, "a3"), b2: await settle(page, "b2") };
  expect(folded.a3).toEqual(folded.a0);
  expect(folded.b2).not.toEqual(folded.a0);

  await page.getByRole("button", { name: "Expand all" }).click();
  await expect.poll(() => grouped(page)).toBe(0);
  await page.waitForTimeout(400);
  const after = await settle(page, "a3");
  expect(Math.hypot(after.x - before.a3!.x, after.y - before.a3!.y)).toBeLessThan(2);
});

test("a double-click inside a box folds the group, and a double-click on the Group Node opens it", async ({ page }) => {
  await communitiesOn(page);
  // The buttons over the canvas are right-aligned in a strip along its top, and every button added
  // to it pushes the rest left. A folded group can sit right under the strip, and the double-click
  // then lands on a button instead of on the Group Node. This case is about the gesture on the
  // canvas, not about the strip, so the strip is made to pass the pointer through for its length.
  await page.getByRole("button", { name: "Clear view" }).evaluate((button) => {
    const strip = button.parentElement?.parentElement;
    if (strip) strip.style.pointerEvents = "none";
  });
  const members = await Promise.all(["a0", "a1", "a2", "a3", "a4"].map((id) => settle(page, id)));
  const centre = {
    x: members.reduce((n, p) => n + p!.x, 0) / members.length,
    y: members.reduce((n, p) => n + p!.y, 0) / members.length,
  };
  const box = await page.getByRole("application", { name: "Network canvas" }).boundingBox();
  await page.mouse.dblclick(box!.x + centre.x, box!.y + centre.y);
  await expect.poll(() => grouped(page)).toBe(5);

  await page.waitForTimeout(400);
  const standIn = await settle(page, "a0");
  await page.mouse.dblclick(box!.x + standIn.x, box!.y + standIn.y);
  await expect.poll(() => grouped(page)).toBe(0);
});

test("keyboard walks skip the nodes a folded group hides", async ({ page }) => {
  await communitiesOn(page);
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus();
  await expect.poll(() => page.evaluate(() => window.__KEYBOARD__?.focused)).toBe("a0");
  await page.keyboard.press("g");
  await expect.poll(() => grouped(page)).toBe(5);
  await page.keyboard.press("Control+Shift+ArrowRight");
  await expect.poll(() => page.evaluate(() => window.__KEYBOARD__?.focused)).toBe("b0");
});

test("switching Communities off puts everything back and forgets what was folded", async ({ page }) => {
  await communitiesOn(page);
  await page.getByRole("button", { name: "Collapse all" }).click();
  await expect.poll(() => grouped(page)).toBe(10);
  await page.getByRole("button", { name: "Communities" }).click();
  await expect.poll(() => grouped(page)).toBe(0);
  await expect(page.getByRole("button", { name: "Fold group of 5 nodes" })).toHaveCount(0);
});

test("a count of judgements is drawn beside the node they rest on, and only there", async ({ page }) => {
  await page.goto("/keyboard/harness.html?judged=n1:2,n3:1");
  const two = page.getByLabel("2 judgements");
  const one = page.getByLabel("1 judgement");
  await expect(two).toBeVisible();
  await expect(one).toBeVisible();
  await expect(page.getByRole("img", { name: /judgement/ })).toHaveCount(2);

  const node = await settle(page, "n1");
  const box = await two.boundingBox();
  const canvasBox = await page.getByRole("application", { name: "Network canvas" }).boundingBox();
  expect(box).not.toBeNull();
  expect(canvasBox).not.toBeNull();
  // Up and to the right of the node, close to it, in the page's own coordinates.
  const nodeX = (canvasBox?.x ?? 0) + (node?.x ?? 0);
  const nodeY = (canvasBox?.y ?? 0) + (node?.y ?? 0);
  expect(Math.abs((box?.x ?? 0) - (nodeX + 8))).toBeLessThan(6);
  expect(Math.abs((box?.y ?? 0) - (nodeY - 18))).toBeLessThan(6);

  // A picture only: it takes no clicks (the node under it is still pressed) and no focus.
  await page.mouse.click(nodeX + 1, nodeY + 1);
  await expect.poll(() => page.evaluate(() => window.__KEYBOARD__?.selection)).toEqual(["n1"]);
});

test("choosing a search result draws three steps out from it, counted first, in one request", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  const bodies: { preview?: unknown; expand?: unknown } = {};
  await page.route("**/*/expand/preview", async (route) => {
    bodies.preview = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ candidate_node_count: 20, candidate_edge_count: 0 }),
    });
  });
  await page.route("**/*/expand", async (route) => {
    bodies.expand = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ delta: { seq: 2, op: "add", nodes: [], edges: [] }, filtered_count: 0 }),
    });
  });
  await page.evaluate(() => (window as unknown as { __CANVAS__: { expandFrom: (id: string, depth: number) => void } }).__CANVAS__.expandFrom("n5", 3));
  await expect.poll(() => bodies.expand !== undefined).toBe(true);
  expect(bodies.preview).toMatchObject({ request: { node_ids: ["n5"], depth: 3 } });
  expect(bodies.expand).toMatchObject({ request: { node_ids: ["n5"], depth: 3 } });
});

test("a three-step draw that is very large asks first, and the answer keeps its three steps", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  let expandBody: unknown = null;
  await page.route("**/*/expand/preview", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ candidate_node_count: 1200, candidate_edge_count: 0 }),
    });
  });
  await page.route("**/*/expand", async (route) => {
    expandBody = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ delta: { seq: 2, op: "add", nodes: [], edges: [] }, filtered_count: 0 }),
    });
  });
  await page.evaluate(() => (window as unknown as { __CANVAS__: { expandFrom: (id: string, depth: number) => void } }).__CANVAS__.expandFrom("n5", 3));
  await expect(page.getByRole("alertdialog", { name: "Large expansion" })).toBeVisible();
  expect(expandBody).toBeNull();
  await tabTo(page, page.getByRole("button", { name: /^Add all/ }));
  await page.keyboard.press("Enter");
  await expect.poll(() => expandBody).toMatchObject({ request: { node_ids: ["n5"], depth: 3 } });
});

test("switching to the light theme repaints the graph's nodes in the light palette, and back", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  const colour = () => page.evaluate(() => window.__CANVAS__?.nodeColour("n1"));
  await expect.poll(colour).toBe("#677bd6"); // indigo, dark
  await page.evaluate(() => window.__CANVAS__?.setTheme("light"));
  await expect.poll(colour).toBe("#5367cb"); // indigo, light
  await page.evaluate(() => window.__CANVAS__?.setTheme("dark"));
  await expect.poll(colour).toBe("#677bd6");
});

test("an expansion that adds nothing says so, and Escape dismisses the message", async ({ page }) => {
  // The owner's right-click comment: every relationship chosen seemed to do nothing. The neighbours
  // were already drawn, and an expansion that adds nothing used to say nothing (ADR-077).
  await page.goto("/keyboard/harness.html");
  await stubSmallExpansionPreview(page);
  await page.route("**/*/expand", async (route) => {
    const body = route.request().postDataJSON() as { request: { edge_types: string[] | null } };
    const alreadyDrawn = body.request.edge_types !== null;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        delta: alreadyDrawn
          ? { seq: 2, op: "add", nodes: [{ id: "n0" }, { id: "n1" }], edges: [{ id: "e0" }] }
          : { seq: 2, op: "add", nodes: [], edges: [] },
        filtered_count: 0,
      }),
    });
  });
  // The server returns everything it found, drawn or not, so the n0 and n1 and e0 here are already on screen.
  await page.evaluate(() => (window as unknown as { __CANVAS__: { expandFrom: (id: string, depth: number) => void } }).__CANVAS__.expandFrom("n0", 1));
  const notice = page.getByRole("status").filter({ hasText: "No links from this node." });
  await expect(notice).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(notice).toBeHidden();

  // A relationship chosen from the menu, whose neighbours are all drawn, says so by name.
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus(); // n0
  await page.keyboard.press("\\");
  await page.keyboard.press("Tab");
  await page.keyboard.press("Enter");
  // The type by its display name (ADR-091), and the message found by its words: the canvas's
  // selection chip is a status region too (ADR-093).
  const nothingNew = page.getByRole("status").filter({ hasText: /^Nothing new:/ });
  await expect(nothingNew).toContainText(/^Nothing new: everything linked by \u2018[A-Z][a-z ]+\u2019 is already in view\.$/);
  await page.keyboard.press("Escape");
  await expect(nothingNew).toBeHidden();
  registerCovered("CANVAS_ACTIONS", "expand-with-nothing-new-says-so");
});

// --- The zoom cluster, Fit and the legend (ADR-097 step 2) ---------------------------------------

// ADR-115 E4: the canvas handle's expandNode — what the Inspector's Expand calls — asks for the
// expansion's preview, as the canvas's own menus do (counted in the store before anything is drawn).
test("the canvas handle's expandNode asks for the node's expansion preview", async ({ page }) => {
  const asked: string[] = [];
  await page.route("**/*/expand/preview", async (route) => {
    asked.push(JSON.stringify(route.request().postDataJSON()));
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ counts: {}, total: 0, cap: 2000, working_set_size: 6 }) });
  });
  await page.goto("/keyboard/harness.html");
  await layoutSettled(page, ["n0"]);
  await page.evaluate(() => window.__CANVAS__?.expandNode("n0"));
  await expect.poll(() => asked.length).toBeGreaterThan(0);
  expect(asked[0]).toContain("n0");
});

test("Zoom in and Zoom out move the camera by keyboard alone", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  await layoutSettled(page, ["n0"]);
  const ratio = async () => (await page.evaluate(() => window.__CANVAS__?.cameraState()))!.ratio;
  const before = await ratio();
  const zoomIn = page.getByRole("button", { name: "Zoom in" });
  await zoomIn.focus();
  await expect(zoomIn).toBeFocused();
  await page.keyboard.press("Enter");
  await expect.poll(ratio).toBeLessThan(before);
  const zoomed = await ratio();
  // ADR-115 E4: the zoom group's readout says the camera's zoom, as a percentage.
  await expect(page.getByRole("group", { name: "Zoom" }).locator(".canvas-zoom__readout")).toHaveAttribute(
    "aria-label",
    `Zoom ${Math.round(100 / zoomed)}%`,
  );
  const zoomOut = page.getByRole("button", { name: "Zoom out" });
  await zoomOut.focus();
  await page.keyboard.press("Enter");
  await expect.poll(ratio).toBeGreaterThan(zoomed);
  registerCovered("CANVAS_ACTIONS", "zoom-in-and-out-by-keyboard");
});

test("F on the canvas, and Fit to view by Enter, bring the whole graph back into view", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  await layoutSettled(page, ["n0"]);
  const ratio = async () => (await page.evaluate(() => window.__CANVAS__?.cameraState()))!.ratio;
  await page.evaluate(() => window.__CANVAS__?.zoomTo(0.1));
  await expect.poll(ratio).toBeCloseTo(0.1);
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus();
  await page.keyboard.press("f");
  await expect.poll(ratio).toBeCloseTo(1);
  await page.evaluate(() => window.__CANVAS__?.zoomTo(0.1));
  const fit = page.getByRole("button", { name: "Fit to view" });
  await fit.focus();
  await page.keyboard.press("Enter");
  await expect.poll(ratio).toBeCloseTo(1);
  registerCovered("CANVAS_ACTIONS", "fit-to-view-by-keyboard");
});

test("the legend folds and opens by keyboard, and names the types in view", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  const list = page.locator('ul[aria-label="Types in view"]');
  await expect(list).toBeVisible();
  await expect(list.locator("li").first()).toContainText(/\d/);
  const toggle = page.getByRole("button", { name: "Legend" });
  await toggle.focus();
  await page.keyboard.press("Enter");
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await expect(list).toBeHidden();
  await page.keyboard.press("Enter");
  await expect(list).toBeVisible();
  registerCovered("CANVAS_ACTIONS", "legend-folds-by-keyboard");
});

// --- Reduced motion (02_GLASS_FRONTEND.md §3.4, ADR-097 step 3) ----------------------------------

test("under reduced motion a new layout moves the nodes at once, and Show previous positions marks where they were", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/keyboard/harness.html");
  const before = await layoutSettled(page, ["n0", "n1", "n2", "n3"]);
  // No control until something has moved.
  await expect(page.getByRole("button", { name: "Show previous positions" })).toHaveCount(0);
  const layout = page.getByRole("combobox", { name: "Layout" });
  await tabTo(page, layout);
  await chooseOption(page, layout, "circular");
  // An instant move: the nodes are at their new places within one frame or two, not 420ms later.
  await page.waitForTimeout(80);
  const soon = await page.evaluate((ids) => ids.map((id) => window.__CANVAS__?.viewportPositionOf(id)), ["n0", "n1", "n2", "n3"]);
  const settled = await layoutSettled(page, ["n0", "n1", "n2", "n3"]);
  expect(soon).toEqual(["n0", "n1", "n2", "n3"].map((id) => settled[id]));
  expect(JSON.stringify(settled)).not.toEqual(JSON.stringify(before));

  const show = page.getByRole("button", { name: "Show previous positions" });
  await show.focus();
  await expect(show).toBeFocused();
  await expect(show).toHaveAttribute("aria-pressed", "false");
  await page.keyboard.press("Enter");
  await expect(show).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("img", { name: /^Where n0 was/ })).toHaveCount(1);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("img", { name: /^Where n0 was/ })).toHaveCount(0);
  registerCovered("CANVAS_ACTIONS", "show-previous-positions-by-keyboard");
});

test("without reduced motion there is no Show previous positions control: the move itself shows what moved", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  await layoutSettled(page, ["n0"]);
  const layout = page.getByRole("combobox", { name: "Layout" });
  await tabTo(page, layout);
  await chooseOption(page, layout, "circular");
  await layoutSettled(page, ["n0"]);
  await expect(page.getByRole("button", { name: "Show previous positions" })).toHaveCount(0);
});

// --- The grid switch (owner, 6 October 2026: "I need the ability to turn the grid lines off") -----

test("Grid in the Show group turns the canvas grid off and on by keyboard, and the choice survives a reload", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  const canvas = page.getByRole("application", { name: "Network canvas" });
  const gridImage = () => canvas.evaluate((el) => getComputedStyle(el).backgroundImage);
  const grid = page.getByRole("button", { name: "Grid" });
  await expect(grid).toHaveAttribute("aria-pressed", "true");
  expect(await gridImage()).toContain("linear-gradient");
  await tabTo(page, grid);
  await page.keyboard.press("Enter");
  await expect(grid).toHaveAttribute("aria-pressed", "false");
  expect(await gridImage()).toBe("none");
  await page.reload();
  await expect(page.getByRole("button", { name: "Grid" })).toHaveAttribute("aria-pressed", "false");
  expect(await gridImage()).toBe("none");
  await tabTo(page, page.getByRole("button", { name: "Grid" }));
  await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: "Grid" })).toHaveAttribute("aria-pressed", "true");
  expect(await gridImage()).toContain("linear-gradient");
  registerCovered("CANVAS_ACTIONS", "grid-toggles-by-keyboard");
});

test("Show links among all, in the canvas toolbar, asks for the links among every node in the view (ADR-098)", async ({ page }) => {
  let body: { node_ids: string[] | null } | undefined;
  await page.route("**/*/investigations/*/links-among", async (route) => {
    body = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ added: 1, delta: { seq: 8, op: "add", nodes: [], edges: [] } }),
    });
  });
  await page.goto("/keyboard/harness.html");
  const button = page.getByRole("button", { name: "Show links among all" });
  await button.focus();
  await expect(button).toBeFocused();
  await page.keyboard.press("Enter");
  await expect.poll(() => body).toEqual({ node_ids: null });
  await expect(page.getByText("1 link added among these.")).toBeVisible();
  registerCovered("CANVAS_ACTIONS", "show-links-among-all-by-keyboard");
});

test("Shift with an arrow key moves the selected node by keyboard, further with Alt (owner, 6 October 2026)", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus();
  await expect.poll(() => page.evaluate(() => window.__KEYBOARD__?.selection)).toEqual(["n0"]);
  const before = (await layoutSettled(page, ["n0"]))["n0"]!;
  await page.keyboard.press("Shift+ArrowRight");
  await page.keyboard.press("Shift+ArrowRight");
  const moved = (await page.evaluate(() => window.__CANVAS__?.viewportPositionOf("n0")))!;
  expect(moved.x - before.x).toBeGreaterThan(12);
  expect(Math.abs(moved.y - before.y)).toBeLessThan(2);
  await page.keyboard.press("Shift+Alt+ArrowDown");
  const down = (await page.evaluate(() => window.__CANVAS__?.viewportPositionOf("n0")))!;
  expect(down.y - moved.y).toBeGreaterThan(24);
  // Focus and selection are unchanged: the nudge moved the node, it did not walk to a neighbour.
  expect(await page.evaluate(() => window.__KEYBOARD__?.focused)).toBe("n0");
  registerCovered("CANVAS_ACTIONS", "move-the-selection-with-shift-and-arrows");
});

test("every registered keyboard action has its own proving test case above", () => {
  assertAllCovered("CANVAS_ACTIONS", CANVAS_ACTIONS);
});

// --- Telling nodes apart (ADR-071) -----------------------------------------------------------
// Seen on the Enron case: two searched addresses drawn as two unlabelled squares, and a right-click
// menu that stayed open whatever was clicked and never said whose it was.

test("in a small view every node is named, even one zoomed out with few links", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  await expect.poll(() => page.evaluate(() => window.__CANVAS__?.labelOf("n0"))).not.toBe("");
  await expect.poll(() => page.evaluate(() => window.__CANVAS__?.labelOf("n3"))).not.toBe("");
});

test("a right-click menu names its node, and a click elsewhere closes it", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  const canvas = page.getByRole("application", { name: "Network canvas" });
  const box = await canvas.boundingBox();
  const at = await settle(page, "n1");
  const x = (box?.x ?? 0) + (at?.x ?? 0);
  const y = (box?.y ?? 0) + (at?.y ?? 0);
  await page.mouse.click(x, y, { button: "right" });
  const menu = page.getByRole("menu");
  await expect(menu).toBeVisible();
  await expect(menu).toHaveAttribute("aria-label", /^Person: /);
  // Elsewhere in the canvas, well away from every node and from the menu. The bottom-left corner:
  // the grouped list (ADR-078) is wider and taller than the old one and, opened low on the right as
  // here, reached the bottom-right corner this used to click.
  await page.mouse.click((box?.x ?? 0) + 12, (box?.y ?? 0) + (box?.height ?? 0) - 12);
  await expect(menu).toHaveCount(0);
});
