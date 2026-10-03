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
  // The panel starts as a strip of section names (ADR-070): the ranking is not loaded until its
  // section is opened, by keyboard like everything else.
  await expect(page.getByRole("button", { name: /Person · n1/ })).toHaveCount(0);
  await tabToButtonNamed(page, "Ranking");
  expect(await page.evaluate(() => document.activeElement?.getAttribute("aria-expanded"))).toBe("false");
  await page.keyboard.press("Enter");
  expect(await page.evaluate(() => document.activeElement?.getAttribute("aria-expanded"))).toBe("true");
  registerCovered("METRICS_PANEL_ACTIONS", "ranking-section-opens-by-keyboard-and-loads-the-list");
  await page.getByRole("button", { name: /Person · n1/ }).waitFor();
  await tabToButtonNamed(page, "Person · n1");
  await page.keyboard.press("Enter");

  await expect
    .poll(() => page.evaluate(() => window.__METRICS_PANEL__?.focusedNodeId))
    .toBe("n1");
  registerCovered("METRICS_PANEL_ACTIONS", "row-select-and-centre");
});

test("every registered metrics-panel action has its own proving test case above", () => {
  assertAllCovered("METRICS_PANEL_ACTIONS", METRICS_PANEL_ACTIONS);
});
