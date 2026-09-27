// **Stage 3a's second residual — Fixture Corp walked through a real browser.**
//
// `07_BUILD_PLAN.md`'s Stage 3a disclosure asks for Fixture Corp's "interactive verification
// through the Glass — moving the resolution threshold live, `explain` on a merged cluster, the
// pathfinder, comparing path lengths". All four are in this file.
//
// **Three of them were impossible until owner ruling R4 (26 September 2026), and the reason is
// worth keeping.** The working set has one entry point, the search box, and
// `services/api/search.py`'s own scope note says what it does: "exact identifier match against
// the graph, not full text". `search_nodes` matches only the identifier fields the ontology
// declares — for `Person`, `nino`/`pnc_id`/`prison_number` — and the Fixture Corp seed set none
// of them. Measured directly against the real store: 0 of 65 Persons, against 400 of 400 for
// HMP, which is exactly why the HMP walkthrough (`scenario-a-a12-a15.spec.ts`) could seed itself
// from search and this one could not. The visual query builder is not a second entry point
// either: it finds them by entity type but, per ADR-032, reports the matched set and its count
// rather than drawing anything — specified behaviour, not a defect in it.
//
// R4 chose to give the fixture identifiers rather than reopen ADR-032. Every Person now carries a
// synthetic `nino` and every Organisation an `org_ref`, both deterministic from the node id, so
// the values below are stable and a presenter can type them from `DEMO_GUIDE.md`. ADR-035 §C5's
// five resolution scores were re-measured either side of that change and are bit-for-bit
// identical — the identifiers take no part in resolution, which blocks and compares on
// `family_name`/`given_names`/`date_of_birth` only.
import { expect, type Page, test } from "@playwright/test";

import { liveOnly, workspaceUrl } from "./live";

test.beforeEach(liveOnly);

/** Deterministic, from `tests/scenarios/fixtures/fixture_corp.py`'s own `_synthetic_nino`.
 * `QQ` is a prefix HMRC never issues, so these cannot collide with a real person's NINO. */
const NINO_IDENTICAL_PAIR_A = "QQ118439C"; // corp-res-identical-1 — merges with -2 at every detent

/** Seeds the working set by typing an identifier into the search box, exactly as
 * `DEMO_GUIDE.md` §6 now tells a presenter to. */
async function seedFromSearch(page: Page, identifier: string): Promise<void> {
  const search = page
    .getByRole("combobox", { name: "Search entities, identifiers, documents" })
    .first();
  await search.fill(identifier);
  const option = page.getByRole("option", { name: /^Person: corp-/ }).first();
  await expect(
    option,
    `no search result for ${identifier} — before R4 this returned nothing for every Fixture ` +
      "Corp entity, because the fixture carried no identifier search could match",
  ).toBeVisible();
  await option.click();
}

async function nodeCount(page: Page): Promise<number> {
  const text = (await page.getByRole("status").first().textContent()) ?? "";
  return Number(/(\d+)\s*nodes/.exec(text)?.[1] ?? 0);
}

async function addPersonVariable(page: Page): Promise<void> {
  await page.getByRole("combobox", { name: "Entity type" }).selectOption("Person");
  await page.getByRole("button", { name: "Add variable" }).click();
  await expect(
    page.getByRole("list", { name: "Pattern nodes" }).getByRole("listitem"),
  ).not.toHaveCount(0);
}

test("the query builder finds Fixture Corp entities and reports how many matched", async ({
  page,
}) => {
  // ADR-032's own assertion for this control, in its words: "the intersection set is returned,
  // with the estimated count shown before running". Also the user-visible face of round 12's
  // `select`-vs-`project` fix — this exact pattern (one variable, no edges) answered
  // `500 Internal Server Error` before it, so "reports a count" was previously unreachable too.
  await page.goto(workspaceUrl());
  await addPersonVariable(page);
  await page.getByRole("button", { name: "Run", exact: true }).click();

  await expect(page.getByText(/\d+ node\(s\) matched\./)).toBeVisible();
});

test("moving the resolution threshold live reports what merged and what split", async ({
  page,
}) => {
  // ADR-035 §C5's first property, and the one item of the four the disclosure names that needs
  // no working set: the control reads and writes the investigation's own threshold, and the
  // delta it reports is computed server-side over everything in scope, not over the canvas.
  //
  // The control commits one of three named constants — Strict 0.99, Balanced 0.95, Broad 0.80 —
  // never an interpolated value, and reports the delta each move produced.
  await page.goto(workspaceUrl());

  const slider = page.getByRole("slider", { name: "Resolution threshold" });
  await expect(slider).toBeVisible();

  await slider.focus();
  await slider.press("End"); // Broad — the loosest, so the one most likely to merge something

  // The commit's own summary, in the words `ThresholdControl.tsx` emits. Asserting the three
  // counts are present rather than asserting particular numbers: the exact merge count is a
  // property of the fixture and of the threshold moved from, so pinning it here would make this
  // fail for a fixture change rather than for a regression in the control.
  await expect(
    page.getByText(/Resolution threshold: .* — \d+ merged, \d+ split, \d+ affected/),
  ).toBeVisible();

  // And the control names the detent it committed rather than a raw number — the "never an
  // interpolated value" half of the same behaviour.
  await expect(page.getByText(/^(Strict|Balanced|Broad)$/)).toBeVisible();
});

test("a Fixture Corp entity is reachable from the search box by its nino", async ({ page }) => {
  // The check that was impossible before R4, and the one the other two below depend on.
  await page.goto(workspaceUrl());
  expect(await nodeCount(page)).toBe(0);

  await seedFromSearch(page, NINO_IDENTICAL_PAIR_A);

  await expect
    .poll(() => nodeCount(page), {
      message: "searching a Fixture Corp nino loaded nothing into the working set",
      timeout: 30_000,
    })
    .toBeGreaterThan(0);
});

// **`explain` on a merged cluster and the pathfinder are NOT in this file, and the reason is a
// second finding rather than a shortage of effort.** Both radial-menu items are conditional on a
// *two-node* selection (`GlassCanvas.tsx`: `selected.size === 2` gates "Find paths to {other}";
// "Explain cluster" needs two working-set nodes sharing a `resolution.cluster_id`). R4 has made
// both nodes reachable — `corp-res-identical-1`/`-2` load by nino and the test above proves it —
// but building the selection itself defeated this round:
//
//   - By keyboard there is no path at all. Arrow-walk moves along `graph.neighbors`, and these
//     two nodes have no edge between them in the working set; Ctrl/Cmd+Arrow cycles within the
//     *existing* selection, so it cannot reach an unselected node. Space toggles only the focused
//     node. So a keyboard user cannot build a two-node selection over disconnected nodes —
//     worth weighing against `CLAUDE.md` rule 13, since "Find paths to" and "Explain cluster" are
//     canvas actions reachable only with a mouse.
//   - By mouse it needs either ctrl/cmd-click on two specific rendered nodes (whose canvas
//     coordinates a spec does not know) or the lasso, which did not drive cleanly here in the
//     time available.
//
// Recorded in `docs/07_BUILD_PLAN.md` and `REPORT-12b.md` rather than papered over with a test
// that asserts something weaker while appearing to cover these two steps.
