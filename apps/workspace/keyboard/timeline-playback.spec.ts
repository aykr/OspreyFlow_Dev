// A scripted, keyboard-only walkthrough of the timeline's own playback and cross-case-overlay
// controls (`02_GLASS_FRONTEND.md` §3.4) — Phase 8 Stage 4f, `CLAUDE.md` rule 13 applied to the
// seventh keyboard-driven surface (`keyboard/timeline-playback-harness.tsx`'s own docstring has
// the reasoning for a separate harness/spec pair). Like the other six, this file never calls
// `page.mouse`/`.click()`.
//
// The speed `Select` and the cross-case-scope `Input`'s own Tab-reachability get no case here —
// only an action with a real timed effect or a real network call does, the same exemption
// `export-panel.spec.ts` already establishes for its own artefact-kind `Select`.
import { expect, test, type Page } from "@playwright/test";

import {
  assertAllCovered,
  registerCovered,
  TIMELINE_PLAYBACK_ACTIONS,
} from "./actionRegistry";

const EMPTY_HISTOGRAM = { bucketing: "fixed_interval", buckets: [], total: 0 };

async function tabToElementNamed(
  page: Page,
  predicate: (active: { tag: string; text: string; ariaLabel: string }) => boolean,
  maxTabs = 40,
): Promise<void> {
  for (let i = 0; i < maxTabs; i++) {
    const active = await page.evaluate(() => ({
      tag: document.activeElement?.tagName ?? "",
      text: document.activeElement?.textContent ?? "",
      ariaLabel: document.activeElement?.getAttribute("aria-label") ?? "",
    }));
    if (predicate(active)) return;
    await page.keyboard.press("Tab");
  }
  throw new Error(`Tab never reached the target element within ${maxTabs} presses`);
}

test("pressing Play actually advances the playback clock forward, reachable by keyboard alone", async ({
  page,
}) => {
  await page.route("**/*/v1/analytics/histogram", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(EMPTY_HISTOGRAM),
    });
  });

  await page.goto("/keyboard/timeline-playback-harness.html");

  await tabToElementNamed(page, (active) => active.tag === "BUTTON" && active.text.includes("Play"));
  await page.keyboard.press("Enter");

  // The clock is a real `requestAnimationFrame` loop, not a state flip — poll for a genuine
  // advance rather than asserting immediately after the keypress.
  await page.waitForFunction(
    () => (window.__TIMELINE_PLAYBACK_HARNESS__?.fraction ?? 0) > 0,
    undefined,
    { timeout: 5000 },
  );
  const fraction = await page.evaluate(() => window.__TIMELINE_PLAYBACK_HARNESS__?.fraction);
  expect(fraction).toBeGreaterThan(0);

  registerCovered("TIMELINE_PLAYBACK_ACTIONS", "toggle-playback-advances-the-clock");
});

test("entering a second investigation's id loads its own cross-case track, reachable by keyboard alone", async ({
  page,
}) => {
  let crossCaseRequestSeen = false;
  await page.route("**/*/v1/analytics/histogram", async (route) => {
    const body = route.request().postDataJSON() as { filter?: { investigation_scope?: string } };
    if (body.filter?.investigation_scope === "case-2") crossCaseRequestSeen = true;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(EMPTY_HISTOGRAM),
    });
  });

  await page.goto("/keyboard/timeline-playback-harness.html");

  await tabToElementNamed(page, (active) => active.ariaLabel === "Cross-case overlay investigation id");
  await page.keyboard.type("case-2");
  await page.keyboard.press("Tab");

  await expect
    .poll(() => crossCaseRequestSeen, { timeout: 5000 })
    .toBe(true);

  registerCovered("TIMELINE_PLAYBACK_ACTIONS", "cross-case-overlay-loads-second-track");
});

test("every registered timeline-playback action has its own proving test case above", () => {
  assertAllCovered("TIMELINE_PLAYBACK_ACTIONS", TIMELINE_PLAYBACK_ACTIONS);
});
