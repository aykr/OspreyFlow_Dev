// Shared helpers for the live tier. Nothing here mocks anything — that is the whole point of
// the directory (`playwright.config.ts`'s own header has the reasoning).

import { type APIRequestContext, test } from "@playwright/test";

/** The opt-in gate. Skipped rather than failed when it is absent: a developer running the whole
 * workspace test suite has no stack up, and that is not a defect. */
export const liveOnly = () =>
  test.skip(
    process.env.OSPREY_TEST_LIVE_GLASS !== "1",
    "needs a hand-brought-up demo stack (DEMO_GUIDE.md §3) — opt in with " +
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
        `operator actually brought up, never guess one. See DEMO_GUIDE.md §3.`,
    );
  }
  return value;
}

export const apiBaseUrl = () => required("OSPREY_LIVE_API_BASE_URL");
export const investigationId = () => required("OSPREY_LIVE_INVESTIGATION_ID");

/** The Glass reads the investigation from `?investigation=<id>` once on load, and it takes
 * precedence over `sessionStorage` (`02_GLASS_FRONTEND.md` §2.1) — so every live spec opens a URL
 * of this shape rather than the bare root, which would create its own investigation silently. */
export const workspaceUrl = () => `/?investigation=${investigationId()}`;

/** **A fresh investigation per test, and it is not tidiness — it is the fix for a false green.**
 *
 * Round 12c's diagnosis: the working set is *server-side* and keyed by investigation, and the
 * Glass loads it on open. Measured directly — opening a bare URL against an investigation another
 * process had expanded in showed "19 nodes 18 edges" before the spec touched anything. So every
 * live test sharing one investigation inherits whatever any earlier test, any earlier *run*, or
 * any manual poke left behind.
 *
 * That is what made A12 green in round 12 and red in 12b. Nothing about the product changed
 * between them: round 12 ran the tier repeatedly against one long-lived investigation until
 * earlier attempts had populated it, at which point A12's `edgeCount > 0` was satisfied without
 * its own expansion contributing anything; 12b used a fresh investigation and the same assertion
 * correctly failed. `CLAUDE.md` rule 15's "a gate's first green is not a result, it is an
 * untested state" — here the green was a *later* run's artefact, which is worse, because it looks
 * like a confirmation.
 *
 * Creating the investigation through the real route rather than reusing
 * `OSPREY_LIVE_INVESTIGATION_ID`: search and expand are not investigation-scoped (checked
 * directly against the routes), so the seeded fixture graph is reachable from any investigation,
 * while the working set — the thing that leaks — starts empty and provably so. */
export async function freshInvestigation(
  request: APIRequestContext,
): Promise<string> {
  const response = await request.post(`${apiBaseUrl()}/v1/investigations`, {
    headers: {
      Authorization: `Bearer ${required("OSPREY_LIVE_BEARER_TOKEN")}`,
    },
  });
  if (!response.ok()) {
    throw new Error(
      `could not create a fresh investigation (${response.status()}): ${await response.text()}`,
    );
  }
  return ((await response.json()) as { id: string }).id;
}

/** The URL for one, ready to `page.goto`. */
export async function freshWorkspaceUrl(
  request: APIRequestContext,
): Promise<string> {
  return `/?investigation=${await freshInvestigation(request)}`;
}
