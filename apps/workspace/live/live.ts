// Shared helpers for the live tier. Nothing here mocks anything — that is the whole point of
// the directory (`playwright.config.ts`'s own header has the reasoning).

import { test } from "@playwright/test";

/** The opt-in gate. Skipped rather than failed when it is absent: a developer running the whole
 * workspace test suite has no stack up, and that is not a defect. */
export const liveOnly = () =>
  test.skip(
    process.env.OSPREY_TEST_LIVE_GLASS !== "1",
    "needs a hand-brought-up demo stack (docs/DEMO_GUIDE.md §3) — opt in with " +
      "OSPREY_TEST_LIVE_GLASS=1 and set OSPREY_LIVE_API_BASE_URL, OSPREY_LIVE_BEARER_TOKEN " +
      "and OSPREY_LIVE_INVESTIGATION_ID.",
  );

/** No default, deliberately. A live spec that fell back to a plausible-looking value would
 * quietly test the wrong deployment, and report a pass for it. */
export function required(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(
      `${name} is not set. The live tier has no defaults: it must be pointed at the stack the ` +
        `operator actually brought up, never guess one. See docs/DEMO_GUIDE.md §3.`,
    );
  }
  return value;
}

export const apiBaseUrl = () => required("OSPREY_LIVE_API_BASE_URL");
export const investigationId = () => required("OSPREY_LIVE_INVESTIGATION_ID");

/** The Glass reads the investigation from `?investigation=<id>` once on load, and it takes
 * precedence over `sessionStorage` (`02_GLASS_FRONTEND.md` §2.1) — so every live spec opens this
 * URL rather than the bare root, which would create a fresh, empty investigation instead. */
export const workspaceUrl = () => `/?investigation=${investigationId()}`;
