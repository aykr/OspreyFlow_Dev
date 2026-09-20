// A scripted, keyboard-only walkthrough of the metrics panel — Phase 7 Stage 3, `CLAUDE.md` rule
// 13 applied to a second keyboard-driven surface (`keyboard/metrics-panel-harness.tsx`'s own
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

  // Starting focus point is the panel's own metric selector, not the page's very first tabbable
  // element (`GlassCanvas`'s own container). Found necessary, not assumed: that container has its
  // own `onKeyDown` Tab handling (`GlassCanvas.tsx`'s "establish/cycle the selection ring"
  // branches) which calls `preventDefault()` on every Tab keydown once it holds focus, the same
  // way it is meant to while an analyst is actively using canvas keyboard navigation — it has no
  // reason to know a sibling panel exists to hand focus onward to, a real, pre-existing property
  // of that component this test works around rather than silently masks. This test's own scope is
  // the metrics panel's row activation, not cross-component Tab flow between two independent
  // keyboard-driven surfaces, which `actionRegistry.ts`'s own module docstring already treats as a
  // question "worth re-checking rather than assumed solved generally" the first time it matters.
  await page.getByRole("combobox", { name: "Primary metric" }).focus();

  // The ranked list sorts descending by value — n1 (5) is the top row, not fixture order's n0.
  // Waited for explicitly: the intercepted fetch above resolves asynchronously, and starting the
  // Tab loop before the list renders would just cycle through the panel's other controls forever.
  await page.getByRole("button", { name: /Person · n1/ }).waitFor();
  await tabToButtonNamed(page, "Person · n1");
  await page.keyboard.press("Enter");

  await expect
    .poll(() => page.evaluate(() => window.__METRICS_PANEL__?.focusedNodeId))
    .toBe("n1");
  registerCovered("row-select-and-centre");
});

test("every registered metrics-panel action has its own proving test case above", () => {
  assertAllCovered(METRICS_PANEL_ACTIONS);
});
