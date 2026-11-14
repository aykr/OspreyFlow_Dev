// Shared helpers for the live tier. Nothing here mocks anything — that is the whole point of
// the directory (`playwright.config.ts`'s own header has the reasoning).

import { type APIRequestContext, expect, type Page, test } from "@playwright/test";

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
 * `OSPREY_LIVE_INVESTIGATION_ID`, **reading the one dataset that seeded case reads.** Search and
 * expand were once not investigation-scoped, so any case reached the seeded graph; since ADR-099
 * a case reads only its own datasets, and Amendment 12 has `POST /v1/investigations` name exactly
 * one (`dataset_ids`) or make an empty one, refusing a body with neither (422). An empty dataset
 * would find nothing, so the fresh case names the seeded case's own: the same records reachable,
 * while the working set — the thing that leaks — starts empty and provably so. The seeded case is
 * read through the real route too (`GET …/datasets`), and one reading other than exactly one
 * dataset is refused in words, never guessed between. */
export async function freshInvestigation(
  request: APIRequestContext,
): Promise<string> {
  const headers = { Authorization: `Bearer ${required("OSPREY_LIVE_BEARER_TOKEN")}` };
  const seeded = await request.get(
    `${apiBaseUrl()}/v1/investigations/${encodeURIComponent(investigationId())}/datasets`,
    { headers },
  );
  if (!seeded.ok()) {
    throw new Error(
      `could not read the seeded case's datasets (${seeded.status()}): ${await seeded.text()}`,
    );
  }
  const datasets = (await seeded.json()) as { id: string }[];
  if (datasets.length !== 1) {
    throw new Error(
      `the seeded case (OSPREY_LIVE_INVESTIGATION_ID) reads ${datasets.length} datasets, not one: ` +
        "a fresh case names exactly one (ADR-099 Amendment 12), and the live tier will not guess " +
        "which. Seed the fixture into a case of its own (DEMO_GUIDE.md §3.4).",
    );
  }
  const response = await request.post(`${apiBaseUrl()}/v1/investigations`, {
    headers,
    data: { dataset_ids: [datasets[0]!.id] },
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

/** The working set's counts as the status bar shows them (`statusbar/StatusBar.tsx`: "12 nodes 30
 * edges …", each number en-GB, so "1,234"). Found by what it says, not as the page's first status:
 * other live regions come before it, and `getByRole("status").first()` read one of them, or waited
 * the whole test out where none was drawn yet (14 November 2026). Waits 30 seconds for it. */
export async function workingSetCounts(page: Page): Promise<{ nodes: number; edges: number }> {
  const bar = page.getByRole("status").filter({ hasText: /\bnodes\b/ }).first();
  const drawn = await bar.waitFor({ state: "visible", timeout: 30_000 }).then(() => true, () => false);
  if (!drawn) {
    throw new Error(`the status bar's counts were not drawn. The page: ${await page.locator("body").ariaSnapshot()}`);
  }
  const text = (await bar.textContent()) ?? "";
  const read = (words: string) => Number((new RegExp(`([\\d,]+)\\s*${words}`).exec(text)?.[1] ?? "0").replace(/,/g, ""));
  return { nodes: read("nodes"), edges: read("edges") };
}
