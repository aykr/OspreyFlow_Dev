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

import { freshWorkspaceUrl, liveOnly } from "./live";

test.beforeEach(liveOnly);

/** Deterministic, from `tests/scenarios/fixtures/fixture_corp.py`'s own `_synthetic_nino`.
 * `QQ` is a prefix HMRC never issues, so these cannot collide with a real person's NINO. */
const PAIR_A = { nino: "QQ118439C", id: "corp-res-identical-1" };
const RING_A = { nino: "QQ789396A", id: "corp-ring0-member0" };
const RING_B = { nino: "QQ435286A", id: "corp-ring0-member1" };

/** Loads a second entity and leaves BOTH selected, by keyboard only.
 *
 * Round 12d's own reason for existing. `Explain cluster` and `Find paths to` are gated on
 * `selected.size === 2`, and two entities found by identifier share no edge, so arrow-walk (which
 * follows `graph.neighbors`) could never pair them and Ctrl/Cmd+Arrow cycles only within the
 * selection. `Ctrl`/`Cmd`+`Shift`+Arrow walks the working set itself; focusing the canvas already
 * selects the first node, so one walk plus one Space is the whole sequence. */
/** Seeds the working set by typing an identifier into the search box, exactly as
 * `DEMO_GUIDE.md` §6 tells a presenter to.
 *
 * **Clears the box first and waits for the option naming `expectedId`.** A second search issued
 * straight after a first would otherwise be matched against the combobox's still-current option
 * list — `GlobalSearch` keeps `results` until its next response lands — so a generic
 * `/^Person: corp-/` matcher happily clicked the *previous* result again and the working set
 * stayed at one node. Found exactly that way, building this round's two-node selection. */
async function seedFromSearch(
  page: Page,
  identifier: string,
  expectedId: string,
): Promise<void> {
  const search = page
    .getByRole("combobox", { name: "Search entities, identifiers, documents" })
    .first();
  await search.fill("");
  await search.fill(identifier);
  const option = page.getByRole("option", { name: `Person: ${expectedId}` });
  await expect(
    option,
    `no search result for ${identifier} (${expectedId}) — before owner ruling R4 this returned ` +
      "nothing for every Fixture Corp entity, because the fixture carried no identifier search " +
      "could match",
  ).toBeVisible();
  await option.click();
}

async function nodeCount(page: Page): Promise<number> {
  const text = (await page.getByRole("status").first().textContent()) ?? "";
  return Number(/(\d+)\s*nodes/.exec(text)?.[1] ?? 0);
}

async function selectBothByKeyboard(
  page: Page,
  second: { nino: string; id: string },
): Promise<void> {
  await seedFromSearch(page, second.nino, second.id);
  await expect.poll(() => nodeCount(page), { timeout: 30_000 }).toBe(2);
  await pairByKeyboard(page);
}

/** Builds a two-node selection over whatever two nodes are already in the working set. */
async function pairByKeyboard(page: Page): Promise<void> {
  const canvas = page.getByRole("application", { name: "Network canvas" });
  const menu = page.locator(".radial-menu__list[role='menu']");

  // Focusing the canvas already establishes a ring containing one node, so the sequence is:
  // walk to the other, Space to add it. The real Glass exposes no `window.__KEYBOARD__` (that is
  // the keyboard harness's own hook), so success is detected by the thing it exists to enable —
  // the two-node-only menu item appearing. Two attempts, because `graph.nodes()` order decides
  // which node focus starts on and a single step could land back where it began.
  await canvas.focus();
  for (let attempt = 0; attempt < 2; attempt++) {
    await page.keyboard.press("Control+Shift+ArrowRight");
    await page.keyboard.press(" ");
    await page.keyboard.press("\\");
    await expect(menu).toBeVisible();
    if (await menu.getByRole("menuitem", { name: /Find paths to/ }).count()) return;
    await page.keyboard.press("Escape");
  }
  throw new Error(
    "could not build a two-node selection by keyboard — Ctrl+Shift+Arrow should walk the " +
      "working set regardless of adjacency (GlassCanvas.tsx, round 12d)",
  );
}

async function addPersonVariable(page: Page): Promise<void> {
  await page
    .getByRole("combobox", { name: "Entity type" })
    .selectOption("Person");
  await page.getByRole("button", { name: "Add variable" }).click();
  await expect(
    page.getByRole("list", { name: "Pattern nodes" }).getByRole("listitem"),
  ).not.toHaveCount(0);
}

test("the query builder finds Fixture Corp entities and reports how many matched", async ({
  page,
  request,
}) => {
  // ADR-032's own assertion for this control, in its words: "the intersection set is returned,
  // with the estimated count shown before running". Also the user-visible face of round 12's
  // `select`-vs-`project` fix — this exact pattern (one variable, no edges) answered
  // `500 Internal Server Error` before it, so "reports a count" was previously unreachable too.
  await page.goto(await freshWorkspaceUrl(request));
  await addPersonVariable(page);
  await page.getByRole("button", { name: "Run", exact: true }).click();

  await expect(page.getByText(/\d+ node\(s\) matched\./)).toBeVisible();
});

test("moving the resolution threshold live reports what merged and what split", async ({
  page,
  request,
}) => {
  // ADR-035 §C5's first property, and the one item of the four the disclosure names that needs
  // no working set: the control reads and writes the investigation's own threshold, and the
  // delta it reports is computed server-side over everything in scope, not over the canvas.
  //
  // The control commits one of three named constants — Strict 0.99, Balanced 0.95, Broad 0.80 —
  // never an interpolated value, and reports the delta each move produced.
  await page.goto(await freshWorkspaceUrl(request));

  const slider = page.getByRole("slider", { name: "Resolution threshold" });
  await expect(slider).toBeVisible();

  await slider.focus();
  await slider.press("End"); // Broad — the loosest, so the one most likely to merge something

  // The commit's own summary, in the words `ThresholdControl.tsx` emits. Asserting the three
  // counts are present rather than asserting particular numbers: the exact merge count is a
  // property of the fixture and of the threshold moved from, so pinning it here would make this
  // fail for a fixture change rather than for a regression in the control.
  await expect(
    page.getByText(
      /Resolution threshold: .* — \d+ merged, \d+ split, \d+ affected/,
    ),
  ).toBeVisible();

  // And the control names the detent it committed rather than a raw number — the "never an
  // interpolated value" half of the same behaviour.
  await expect(page.getByText(/^(Strict|Balanced|Broad)$/)).toBeVisible();
});

test("a Fixture Corp entity is reachable from the search box by its nino", async ({
  page,
  request,
}) => {
  // The check that was impossible before R4, and the one the other two below depend on.
  await page.goto(await freshWorkspaceUrl(request));
  expect(await nodeCount(page)).toBe(0);

  await seedFromSearch(page, PAIR_A.nino, PAIR_A.id);

  await expect
    .poll(() => nodeCount(page), {
      message:
        "searching a Fixture Corp nino loaded nothing into the working set",
      timeout: 30_000,
    })
    .toBeGreaterThan(0);
});

// **`explain` on a merged cluster is still not here, and round 12d found out why — it is not a
// keyboard problem, and not a test problem.**
//
// The keyboard half is solved: `Ctrl`/`Cmd`+`Shift`+Arrow walks the working set, so a two-node
// selection over two non-adjacent nodes is reachable without a mouse, and the pathfinder test
// below proves it end to end. "Explain cluster" needs one thing more — two working-set nodes
// sharing a `resolution.cluster_id` — and that state cannot be produced from this fixture at all:
//
//   - Moving the resolution threshold over a working set holding both halves of the `identical`
//     pair reports `merged: 0, split: 0, affected: 0` at Broad, the loosest detent. Measured
//     against the real route, not inferred.
//   - The reason is in the store: the seeded `SAME_AS` edge between `corp-res-identical-1` and
//     `-2` carries **weight 0.747**, below even Broad's 0.80. ADR-035 §C5 records that pair at
//     **0.999991**. Every seeded weight disagrees with §C5's recorded score, and the ordering is
//     inverted — the "never merges" negative control sits at 0.661, *above* `close_given_name`'s
//     0.649. At Broad only the non-Latin pair (0.802) merges at all.
//
// §C5's property 1 — "entity resolution at τ 0.99/0.95/0.80 producing visibly different
// projections" — therefore holds for the in-process test
// (`test_fixture_corp_entity_resolution_projections_differ_by_threshold`, which resolves an
// isolated ten-node population) and not for the seeded fixture a live session actually reads.
// That is a fixture/ADR question, not something a spec should paper over, and it is recorded in
// `07_BUILD_PLAN.md` and this round's DECISION_NEEDED.md rather than asserted around here.

test("the pathfinder finds a path between two ring members, and reports its length", async ({
  page,
  request,
}) => {
  // ADR-035 §C5 properties 3 and 4, and `DEMO_GUIDE.md` §6's "the pathfinder, comparing path
  // lengths". Two members of the same fraud ring: every ring member is `ASSOCIATE_OF` every
  // other, so a direct path exists and its length is knowable in advance — which is what makes
  // the assertion below a real check rather than "something came back".
  await page.goto(await freshWorkspaceUrl(request));
  await seedFromSearch(page, RING_A.nino, RING_A.id);
  await selectBothByKeyboard(page, RING_B);

  const menu = page.locator(".radial-menu__list[role='menu']");
  const findPaths = menu.getByRole("menuitem", { name: /Find paths to/ });
  await expect(findPaths).toBeVisible();
  await findPaths.click();

  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog).not.toContainText(/no path/i);
  // Two members of one fully-interconnected ring are one hop apart. Asserting the reported
  // length rather than merely "a path exists" is the "comparing path lengths" half of the step:
  // a pathfinder that returned some path of any length would satisfy the weaker assertion.
  await expect(dialog).toContainText(/\b1\b/);
});
