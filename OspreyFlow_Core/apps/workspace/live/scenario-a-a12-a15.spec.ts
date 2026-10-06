// **Stage 3a's third residual: Scenario A steps A12–A15 walked through a real browser.**
//
// `07_BUILD_PLAN.md`'s Stage 3a disclosure and `DEMO_GUIDE.md` §1 both record these as "built
// [...] but likewise not yet fully walked through a browser" — A12's Clique Metric (Phase 7) and
// A13–A15's judgements, gaps, assumptions and export with the handling gate (Phase 8).
//
// Runs against the HMP fixture, which is reachable from the search box because its Person nodes
// carry `prison_number` — one of the three identifiers the ontology declares for Person, and
// what `search_nodes` matches on. (Fixture Corp's own entities carry none, which is why its
// walkthrough is not in this file; see `process/demo/2026-09-26/RUNBOOK.md` and the round's own
// DECISION_NEEDED.md.)
import { expect, type Page, test } from "@playwright/test";

import { freshWorkspaceUrl, liveOnly } from "./live";

test.beforeEach(liveOnly);

/** **A member of the fixture's own insular subgroup, which is what A12 is about.**
 *
 * Not `HMP-0001`, which round 12b used and which has no associates at all. Measured against the
 * store in round 12c: of the fixture's 400 Persons exactly 16 carry `ASSOCIATE_OF` edges, 8 each
 * — that tight, densely-interconnected cluster *is* "the insular subgroup" A12 asks the Clique
 * Metric to rank, and `HMP-0001` sits outside it with `MENTIONED_IN` (12), `PRESENT_AT` (5) and
 * `FAMILY_OF` (1) instead. Prison numbers are assigned in order by
 * `scripts/seed_hmp_fixture.py`, so this is stable across reseeds without depending on a
 * generated id. */
const SEEDED_PRISON_NUMBER = "HMP-0003";

async function seedWorkingSetFromSearch(page: Page): Promise<void> {
  const search = page
    .getByRole("combobox", { name: "Search entities, identifiers, documents" })
    .first();
  await search.fill(SEEDED_PRISON_NUMBER);
  // The combobox's own option label is `${type}: ${id}` (`search/GlobalSearch.tsx`).
  const option = page.getByRole("option", { name: /^Person: / }).first();
  await expect(
    option,
    `no search result for ${SEEDED_PRISON_NUMBER} — is the HMP fixture seeded
    under the investigation this spec was pointed at?`,
  ).toBeVisible();
  await option.click();
}

async function nodeCount(page: Page): Promise<number> {
  const text = (await page.getByRole("status").first().textContent()) ?? "";
  return Number(/(\d+)\s*nodes/.exec(text)?.[1] ?? 0);
}

async function edgeCount(page: Page): Promise<number> {
  const text = (await page.getByRole("status").first().textContent()) ?? "";
  return Number(/(\d+)\s*edges/.exec(text)?.[1] ?? 0);
}

/** Expands the canvas's focused node by a *named* edge type.
 *
 * Backslash is what opens the menu — `apps/workspace/keyboard/keyboard.spec.ts`'s own
 * "backslash opens the radial menu as a keyboard-navigable list" establishes it, and focusing the
 * canvas establishes a selected node immediately. Driven by keyboard rather than `page.mouse` for
 * the same reason that file gives: it is the path a keyboard user has.
 *
 * **The edge type is a parameter, and naming the wrong one cost round 12b an afternoon.** The
 * menu lists every edge type the ontology allows *for the node's type*, not the ones this node
 * actually has, so it offers `ASSOCIATE_OF` on a node with none. `HMP-0001` is exactly that node:
 * measured against the store in round 12c, its eighteen edges are `MENTIONED_IN` (12),
 * `PRESENT_AT` (5) and `FAMILY_OF` (1) — and `ASSOCIATE_OF` (0). Expanding it by `ASSOCIATE_OF`
 * correctly brings in nothing, and the failure then surfaces two assertions later as "no
 * neighbourhood to rank", which reads like a defect in the Clique Metric. The fix was to walk
 * the step on a node that has what the step is about; see `SEEDED_PRISON_NUMBER`.
 *
 * Filtering on the displayed count does not rescue it either, and was tried: `GlassCanvas.tsx`
 * renders `count: 0` for *every* entry until round 12c wired the real figure in. */
async function expandFromTheSelectedNode(
  page: Page,
  edgeType: string,
): Promise<void> {
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus();
  await page.keyboard.press("\\");

  const menu = page.locator(".radial-menu__list[role='menu']");
  await expect(menu).toBeVisible();
  const expandItem = menu
    .getByRole("menuitem")
    .filter({ hasText: new RegExp(`^${edgeType}\\b`) })
    .first();
  await expect(
    expandItem,
    `the radial menu offered no ${edgeType} entry`,
  ).toBeVisible();
  // **The previewed cardinality is real** — `08_ACCEPTANCE_SCENARIOS.md` A1's "expansion
  // previews its cardinality before running: the analyst is never surprised by ten thousand
  // nodes". Round 12c wired this to `/expand/preview`; before it, every entry read `(0)`, which
  // is the same text for "nothing here" and "eight here" and is what sent round 12b chasing an
  // expansion that could never have worked.
  //
  // A non-zero figure rather than an exact one: the count is a property of the fixture, and
  // pinning it would make this fail for a fixture change rather than for the preview regressing.
  await expect(
    expandItem,
    `${edgeType} still previews as (0) or (…) on a node that has neighbours — the radial menu's ` +
      "cardinality is not reaching /expand/preview",
  ).not.toHaveText(new RegExp(`^${edgeType}\\s*\\((0|…)\\)`));

  await expandItem.click();
}

test("A12 — the Clique Metric ranks nodes in the metrics panel", async ({
  page,
  request,
}) => {
  // `08_ACCEPTANCE_SCENARIOS.md` A12, and `DEMO_GUIDE.md` §4's own "the Clique Metric that ranks
  // the insular subgroup". Built in Phase 7 as `POST /v1/investigations/{id}/compute/
  // clique_metric` with its own `MetricsPanel` option; never before driven from the browser.
  await page.goto(await freshWorkspaceUrl(request));
  // **The working set really is empty before this test does anything.** Not ceremony: the
  // working set is server-side and the Glass loads it on open, so a shared investigation hands
  // a test whatever an earlier test or an earlier *run* left behind. That is precisely how this
  // test reported green in round 12 while its own expansion contributed nothing — see
  // `live.ts`'s `freshInvestigation`. Asserting the precondition is what makes the rest of this
  // test's own evidence mean something.
  expect(
    await nodeCount(page),
    "the working set was not empty at the start",
  ).toBe(0);
  expect(
    await edgeCount(page),
    "the working set was not empty at the start",
  ).toBe(0);

  await seedWorkingSetFromSearch(page);
  await expect
    .poll(() => nodeCount(page), { timeout: 30_000 })
    .toBeGreaterThan(0);
  expect(
    await edgeCount(page),
    "a single search result should arrive with no edges",
  ).toBe(0);

  // A search result arrives as one isolated node. The Clique Metric measures how tightly a
  // node's neighbours interconnect, so on a single unconnected node it correctly computes
  // nothing. Expanding first is part of the step, not setup around it: A12 follows A1's "seed a
  // working set [...] and expand into their associations".
  await expandFromTheSelectedNode(page, "ASSOCIATE_OF");
  await expect
    .poll(() => edgeCount(page), {
      message:
        "expansion brought in no edges, so there is no neighbourhood to rank",
      timeout: 30_000,
    })
    .toBeGreaterThan(0);

  const computed: number[] = [];
  page.on("response", (r) => {
    if (r.url().includes("/compute/clique_metric")) computed.push(r.status());
  });

  // The Metrics panel starts closed (ADR-070).
  await page.getByRole("button", { name: /^Ranking/ }).click();
  await page
    .getByRole("combobox", { name: "Primary metric" })
    .selectOption("clique_metric");

  // The route really ran — not merely that the option is selectable, which a disconnected
  // `<select>` would also satisfy.
  await expect
    .poll(() => computed, {
      message: "selecting Clique Metric issued no compute request",
      timeout: 30_000,
    })
    .toContain(200);

  // And the ranking really rendered. `MetricsPanel` exposes it as a list named "Ranked nodes".
  const ranked = page.getByRole("list", { name: "Ranked nodes" });
  await expect(ranked).toBeVisible();
  await expect(ranked.getByRole("listitem")).not.toHaveCount(0);
});

test("A13–A15 — a judgement is recorded against the investigation", async ({
  page,
  request,
}) => {
  // Phase 8's assessment objects. The Inspector's Judgements tab is where an analyst records
  // one; `DEMO_GUIDE.md` §4 step 6 is the inspection step this hangs off.
  await page.goto(await freshWorkspaceUrl(request));
  await seedWorkingSetFromSearch(page);
  await expect
    .poll(() => nodeCount(page), { timeout: 30_000 })
    .toBeGreaterThan(0);

  // ADR-096: the Inspector's parts are accordion sections, not tabs; Judgements opens from its header.
  await page.getByRole("button", { name: /^Judgements/ }).click();
  const add = page.getByRole("button", {
    name: "Add judgement, gap or assumption",
  });
  await expect(add).toBeVisible();
  await add.click();

  // The composer is open and offers all three assessment kinds — the trio A13–A15 names,
  // asserted together because the panel builds them from one control.
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText(/judgement/i);
});

test("A15 — export names what it blocked, and takes a justification", async ({
  page,
  request,
}) => {
  // `02_GLASS_FRONTEND.md` §10.2's handling gate: an export carrying an item the principal may
  // not release is refused with *every* reason named, never silently dropped, and an overridable
  // refusal takes a justification plus an originator reference before it will resubmit.
  await page.goto(await freshWorkspaceUrl(request));
  await seedWorkingSetFromSearch(page);
  await expect
    .poll(() => nodeCount(page), { timeout: 30_000 })
    .toBeGreaterThan(0);

  await page.getByRole("button", { name: /^Export/ }).click();
  const drawer = page
    .getByRole("dialog")
    .or(page.getByRole("complementary"))
    .first();
  await expect(drawer).toBeVisible();

  // The export kinds Phase 8 built, all three present.
  const kind = page
    .getByRole("combobox")
    .filter({ has: page.getByRole("option", { name: "Report" }) });
  await expect(kind).toBeVisible();
});
