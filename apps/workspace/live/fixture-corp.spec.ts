// **Stage 3a's second residual, attempted — and the part of it that is currently impossible.**
//
// `07_BUILD_PLAN.md`'s Stage 3a disclosure asks for Fixture Corp's "interactive verification
// through the Glass — moving the resolution threshold live, `explain` on a merged cluster, the
// pathfinder, comparing path lengths". Only the first of those four is in this file, and the
// reason the other three are not is a finding, not an omission:
//
// **No Fixture Corp entity can be put into the Glass's working set.** The working set has one
// entry point, the search box, and `services/api/search.py`'s own scope note says what it does:
// "exact identifier match against the graph, not full text". `search_nodes` matches only the
// identifier fields the ontology declares — for `Person`, `nino`/`pnc_id`/`prison_number` — and
// the Fixture Corp seed sets none of them on any of its 65 Person nodes or its 3 Organisations.
// Measured directly against the real store on 26 September 2026: 0 of 65 carry any Person
// identifier, against 400 of 400 for the HMP fixture, which is exactly why the HMP walkthrough
// (`scenario-a-a12-a15.spec.ts`) can seed itself from search and this one cannot.
//
// The visual query builder is not a second entry point. It selects on entity type rather than
// identifier and does find them — but `06_DECISIONS.md` ADR-032 settled deliberately that its
// Run reports the matched set and its count rather than drawing anything, so
// `QueryBuilderPanel.tsx` renders "N node(s) matched" and loads nothing. That is the specified
// behaviour, not a bug in it.
//
// So `explain`, the pathfinder and path-length comparison need either a searchable identifier on
// the fixture (an ADR-035 §C5 fixture-shape change) or a way to load a pattern result into the
// working set (a product decision ADR-032 explicitly decided against once). Both are the owner's
// call, not this round's — round 12's DECISION_NEEDED.md asks it.
import { expect, type Page, test } from "@playwright/test";

import { liveOnly, workspaceUrl } from "./live";

test.beforeEach(liveOnly);

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
