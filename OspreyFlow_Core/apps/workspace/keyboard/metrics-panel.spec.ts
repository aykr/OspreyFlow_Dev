// A scripted, keyboard-only walkthrough of the metrics panel — Phase 7 Stage 3, proving
// reachability end to end for a second keyboard-driven surface (`keyboard/metrics-panel-harness.tsx`'s own
// docstring has the full reasoning for why this is a separate harness/spec pair rather than an
// addition to `keyboard.spec.ts`). Like that file, this test never calls `page.mouse`/`.click()`.
//
// **What this proves, precisely.** Not "can Tab reach the row button" — a plain native `<button>`
// inside ordinary DOM flow is reachable by Tab for free, the browser's own guarantee, not this
// codebase's. What needs proving is `01_DOMAIN_MODEL.md`/`App.tsx`'s own composed wiring: does
// *activating* a row via a real keyboard `Enter` keypress reach `MetricsPanel`'s `onFocusNode` →
// `GlassCanvasHandle.focusOnNode` → `GlassCanvas`'s own `onFocusChange` — real application logic
// (a camera pan), not a browser default. `POST .../compute/degree` is intercepted so the ranked
// list's own top row is deterministic, the same "real network call, mocked at the transport"
// shape `keyboard.spec.ts`'s own Enter-expand test already uses.
import { expect, test } from "@playwright/test";

import { layoutSettled } from "./layoutSettled";
import { assertAllCovered, METRICS_PANEL_ACTIONS, registerCovered } from "./actionRegistry";

declare global {
  interface Window {
    __METRICS_PANEL__?: { focusedNodeId: string | null };
  }
}

async function tabToButtonNamed(
  page: import("@playwright/test").Page,
  name: string,
  maxTabs = 20,
): Promise<void> {
  for (let i = 0; i < maxTabs; i++) {
    await page.keyboard.press("Tab");
    const active = await page.evaluate(() => ({
      tag: document.activeElement?.tagName,
      text: document.activeElement?.textContent ?? "",
    }));
    if (active.tag === "BUTTON" && active.text.includes(name)) return;
  }
  throw new Error(`Tab never reached a button named ${JSON.stringify(name)} within ${maxTabs} presses`);
}

test("a keyboard-activated ranked row centres the canvas on the right node", async ({ page }) => {
  await page.route("**/*/compute/degree", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ mode: "sync", values: { n0: 1, n1: 5, n2: 3 } }),
    });
  });

  await page.goto("/keyboard/metrics-panel-harness.html");

  // Starting focus point is the canvas itself, not the panel's own first control — this is the
  // concrete proof of Phase 7 Stage 4's own Tab-trap fix (`GlassCanvas.tsx`'s own `onKeyDown`
  // comment has the full incident): before that fix, this container called `preventDefault()` on
  // every Tab keydown once it held focus, so a keyboard user could never Tab onward from the
  // canvas into a sibling panel at all — this exact test previously had to start from the panel's
  // own first control to work around it. It no longer does.
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus();

  // The ranked list sorts descending by value — n1 (5) is the top row, not fixture order's n0.
  // Waited for explicitly: the intercepted fetch above resolves asynchronously, and starting the
  // Tab loop before the list renders would just cycle through the panel's other controls forever.
  // ADR-096: the panel opens on its preview, the ranking, loaded at once; its header folds it and
  // opens it again by keyboard, like every part of the side panels.
  await page.getByRole("button", { name: /Person · n1/ }).waitFor();
  await tabToButtonNamed(page, "Ranking");
  expect(await page.evaluate(() => document.activeElement?.getAttribute("aria-expanded"))).toBe("true");
  await page.keyboard.press("Enter");
  expect(await page.evaluate(() => document.activeElement?.getAttribute("aria-expanded"))).toBe("false");
  await expect(page.getByRole("button", { name: /Person · n1/ })).toHaveCount(0);
  await page.keyboard.press("Enter");
  expect(await page.evaluate(() => document.activeElement?.getAttribute("aria-expanded"))).toBe("true");
  registerCovered("METRICS_PANEL_ACTIONS", "ranking-opens-loaded-and-folds-by-keyboard");
  await page.getByRole("button", { name: /Person · n1/ }).waitFor();
  await tabToButtonNamed(page, "Person · n1");
  await page.keyboard.press("Enter");

  await expect
    .poll(() => page.evaluate(() => window.__METRICS_PANEL__?.focusedNodeId))
    .toBe("n1");
  // Centred means drawn in the middle of the 800 by 600 canvas (8 October 2026: the camera was
  // given the node's layout position, not its camera position, and the canvas went blank). n1 is
  // laid out at the centre already, which is how the case above passed with the camera thrown
  // away; n2 starts at the left edge, so only a real centring brings it to the middle.
  const centred = (id: string) => async () => {
    const at = await page.evaluate((n) => window.__METRICS_PANEL__?.positionOf?.(n) ?? null, id);
    return at !== null && Math.abs(at.x - 400) < 40 && Math.abs(at.y - 300) < 40;
  };
  // The first layout ends by fitting the camera to the graph, so a centring made while it still
  // settles is undone by it; the analyst's view is the settled one.
  await layoutSettled(page, ["n0", "n1", "n2"]);
  expect(await centred("n2")()).toBe(false);
  await tabToButtonNamed(page, "Person · n2");
  await page.keyboard.press("Enter");
  await expect.poll(centred("n2")).toBe(true);
  registerCovered("METRICS_PANEL_ACTIONS", "row-select-and-centre");
});

const filterState = (page: import("@playwright/test").Page) =>
  page.evaluate(() => window.__METRICS_PANEL__?.filter ?? null);

test("the Filter section's strength slider sets a floor with the arrow keys alone (ADR-088)", async ({ page }) => {
  await page.goto("/keyboard/metrics-panel-harness.html");
  await page.getByRole("application", { name: "Network canvas" }).focus();
  await tabToButtonNamed(page, "Filter");
  await page.keyboard.press("Enter");
  const slider = page.getByRole("slider", { name: "Relationship strength at least" });
  await slider.focus();
  await expect(slider).toBeFocused();
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowRight");
  await expect.poll(async () => (await filterState(page))?.strengthFloor).toBeCloseTo(0.1, 5);
  await expect(page.getByText(/Relationship strength at least 0\.10/)).toBeVisible();
  registerCovered("METRICS_PANEL_ACTIONS", "filter-section-sets-a-strength-floor-by-keyboard");
});

test("choosing a metric fetches its values and the threshold slider dims below a value, by keyboard (ADR-088)", async ({
  page,
}) => {
  await page.route("**/*/compute/clique_metric", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ mode: "sync", values: { n0: 0.2, n1: 0.9, n2: 0.5 } }),
    });
  });
  await page.goto("/keyboard/metrics-panel-harness.html");
  await page.getByRole("application", { name: "Network canvas" }).focus();
  await tabToButtonNamed(page, "Filter");
  await page.keyboard.press("Enter");
  const metric = page.getByRole("combobox", { name: "Filter by metric" });
  await metric.focus();
  await page.keyboard.type("Cliq"); // typed, since an arrow on a closed select opens it on macOS
  await expect(metric).toHaveValue("clique_metric");
  await expect.poll(async () => (await filterState(page))?.values?.n1).toBe(0.9);
  const threshold = page.getByRole("slider", { name: "Metric value at least" });
  await threshold.focus();
  await expect(threshold).toBeFocused();
  // Forty steps of 0.007 from 0.2 reach about 0.48: n0 falls below, n1 and n2 stay.
  for (let i = 0; i < 40; i++) await page.keyboard.press("ArrowRight");
  await expect.poll(async () => (await filterState(page))?.threshold ?? 0).toBeGreaterThan(0.4);
  registerCovered("METRICS_PANEL_ACTIONS", "filter-section-dims-below-a-metric-value-by-keyboard");
});

test("every registered metrics-panel action has its own proving test case above", () => {
  assertAllCovered("METRICS_PANEL_ACTIONS", METRICS_PANEL_ACTIONS);
});
