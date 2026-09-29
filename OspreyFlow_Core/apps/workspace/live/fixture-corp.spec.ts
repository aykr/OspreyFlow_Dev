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

/** Deterministic, from `packages/demo_fixtures/fixture_corp.py`'s own `_synthetic_nino`.
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
  const option = page.getByRole("option", { name: `Person: ${expectedId}` });

  // **Retried, deliberately, and bounded.** `GlobalSearch` fires its query on each change and
  // keeps the previous `results` until the next response lands, so a second search issued
  // straight after a first is racing that response: the option list can still be the previous
  // one, or briefly empty. Re-typing is what a person does when nothing appears, and three
  // attempts is enough to tell a race from an absent record — if the identifier genuinely is not
  // there, all three fail and the message below is the right one.
  for (let attempt = 0; attempt < 3; attempt++) {
    await search.fill("");
    await search.pressSequentially(identifier, { delay: 15 });
    try {
      await option.waitFor({ state: "visible", timeout: 5_000 });
      await option.click();
      return;
    } catch {
      // fall through and retype
    }
  }
  throw new Error(
    `no search result for ${identifier} (${expectedId}) after three attempts. The identifier ` +
      "resolves through POST /v1/search — if it does here too, this is the Glass, not the data; " +
      "before owner ruling R4 it returned nothing for every Fixture Corp entity, because the " +
      "fixture carried no identifier search could match.",
  );
}

async function edgeCountOf(page: Page): Promise<number> {
  const text = (await page.getByRole("status").first().textContent()) ?? "";
  return Number(/(\d+)\s*edges/.exec(text)?.[1] ?? 0);
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

const PAIR_B = { nino: "QQ843781D", id: "corp-res-identical-2" };

test("explain on a merged cluster names the pair's real resolution score", async ({
  page,
  request,
}) => {
  // **Stage 3a's last Fixture Corp check.** ADR-035 §C5 property 1's other half, and
  // `DEMO_GUIDE.md` §6's "`explain` on a merged cluster".
  //
  // **The sequence is the finding, and it took four rounds to get right.** "Explain cluster"
  // appears when the focused node carries a `resolution.cluster_id` shared by another working-set
  // node. That needs three things in order, and round 12d had none of them:
  //   1. both halves of the pair in the working set — searchable only since owner ruling R4;
  //   2. the `SAME_AS` edge between them *expanded in*, because `projection.py` collapses
  //      components over the working set's own edges and a search-seeded node carries no edges
  //      (REPORT-12c). Expanding it was impossible until round 12e fixed the radial menu's
  //      wildcard filter — `SAME_AS` is declared `from: ["*"]` and was silently absent;
  //   3. only then, a threshold commit, which is what computes the projection.
  //
  // Round 12d read the resulting `merged: 0` as the fixture being wrong and compared the edges'
  // `weight` (§6.1's load-time strength) against §C5's match `score`. Round 12e measured both:
  // every stored `score` matches §C5 exactly. The fixture was never at fault.
  await page.goto(await freshWorkspaceUrl(request));
  await seedFromSearch(page, PAIR_A.nino, PAIR_A.id);
  await seedFromSearch(page, PAIR_B.nino, PAIR_B.id);
  await expect.poll(() => nodeCount(page), { timeout: 30_000 }).toBe(2);

  // Expand SAME_AS from the canvas, by keyboard — the step that was unreachable until 12e.
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus();
  await page.keyboard.press("\\");
  const menu = page.locator(".radial-menu__list[role='menu']");
  await expect(menu).toBeVisible();
  const sameAs = menu.getByRole("menuitem", { name: /^SAME_AS/ });
  await expect(
    sameAs,
    "the radial menu offers no SAME_AS entry — it is declared from:[\"*\"] to:[\"*\"], so a " +
      "filter that does not read the wildcard drops it (see canvas/edgeTypeMenu.ts)",
  ).toBeVisible();
  await sameAs.click();
  await expect
    .poll(() => edgeCountOf(page), { timeout: 30_000 })
    .toBeGreaterThan(0);

  // Commit a detent, which computes the projection over those edges and pushes the resulting
  // `resolution.cluster_id`s down in its delta.
  //
  // **`Home` (Strict, 0.99), not `End` (Broad, 0.80)** — and the reason is worth keeping: a
  // fresh investigation already sits at Balanced, so committing Broad from it changes nothing,
  // returns `merged: 0, split: 0, affected: 0`, and emits no delta at all. The nodes then still
  // carry no `cluster_id` and the menu item never appears, which looks exactly like the
  // projection being broken. Measured that way against the route before changing this.
  // The identical pair scores 0.999991, so it is merged at Strict as at every other detent.
  const slider = page.getByRole("slider", { name: "Resolution threshold" });
  await slider.focus();
  await slider.press("Home");
  await expect(
    page.getByText(/Resolution threshold: .* — \d+ merged, \d+ split, \d+ affected/),
  ).toBeVisible();

  // Now the item is there, on a single focused node — `explain` takes one cluster id, not a pair.
  await canvas.focus();
  await page.keyboard.press("\\");
  const explain = menu.getByRole("menuitem", { name: /Explain cluster/ });
  await expect(explain).toBeVisible();
  await explain.click();

  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  // The per-comparison evidence `01_DOMAIN_MODEL.md` §4 calls the "full comparison vector" —
  // every gamma level, not a bare verdict.
  await expect(dialog).toContainText(/gamma_family_name/);
  await expect(dialog).toContainText(/gamma_given_names/);
  await expect(dialog).toContainText(/gamma_date_of_birth/);
  // The model version that produced the score, which `same_as_writer.py` records alongside it so
  // an explanation is attributable rather than a floating number.
  await expect(dialog).toContainText(/splink-/);
  // And the verdict for this pair at the committed detent.
  await expect(dialog).toContainText(/Meets τ/);
  await expect(dialog.getByRole("row").filter({ hasText: "SAME_AS" }).first()).toContainText(
    "Yes",
  );
  // **Not asserting the score's digits.** §C5 records 0.999991 and the panel renders it as
  // `1.00`; pinning either would test the formatter rather than the explanation. That the score
  // is §C5's is established where it can be established exactly — round 12e read all five
  // stored `properties.score` values off the seeded store and every one matched to the sixth
  // decimal (`07_BUILD_PLAN.md`'s Stage 3a table).
});

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
