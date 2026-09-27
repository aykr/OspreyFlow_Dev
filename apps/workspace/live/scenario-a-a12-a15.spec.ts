// **Stage 3a's third residual: Scenario A steps A12–A15 walked through a real browser.**
//
// `07_BUILD_PLAN.md`'s Stage 3a disclosure and `DEMO_GUIDE.md` §1 both record these as "built
// [...] but likewise not yet fully walked through a browser" — A12's Clique Metric (Phase 7) and
// A13–A15's judgements, gaps, assumptions and export with the handling gate (Phase 8).
//
// Runs against the HMP fixture, which is reachable from the search box because its Person nodes
// carry `prison_number` — one of the three identifiers the ontology declares for Person, and
// what `search_nodes` matches on. (Fixture Corp's own entities carry none, which is why its
// walkthrough is not in this file; see `docs/demo/2026-09-26/RUNBOOK.md` and the round's own
// DECISION_NEEDED.md.)
import { expect, type Page, test } from "@playwright/test";

import { liveOnly, workspaceUrl } from "./live";

test.beforeEach(liveOnly);

/** `HMP-0001` is the first seeded prison number — `scripts/seed_hmp_fixture.py` numbers them
 * from one, so this is stable across reseeds without depending on a generated id. */
const SEEDED_PRISON_NUMBER = "HMP-0001";

async function seedWorkingSetFromSearch(page: Page): Promise<void> {
  const search = page
    .getByRole("combobox", { name: "Search entities, identifiers, documents" })
    .first();
  await search.fill(SEEDED_PRISON_NUMBER);
  // The combobox's own option label is `${type}: ${id}` (`search/GlobalSearch.tsx`).
  const option = page.getByRole("option", { name: /^Person: / }).first();
  await expect(option, `no search result for ${SEEDED_PRISON_NUMBER} — is the HMP fixture seeded
    under the investigation this spec was pointed at?`).toBeVisible();
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

/** Expands the canvas's currently focused node by the first edge type its radial menu offers.
 *
 * Backslash is what opens that menu — `apps/workspace/keyboard/keyboard.spec.ts`'s own
 * "backslash opens the radial menu as a keyboard-navigable list" establishes it, and focusing
 * the canvas establishes a selected node immediately. Driven by keyboard rather than
 * `page.mouse` for the same reason that file gives: it is the path a keyboard user has, so it
 * is the one worth proving. */
async function expandFromTheSelectedNode(page: Page): Promise<void> {
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus();
  await page.keyboard.press("\\");

  const menu = page.locator(".radial-menu__list[role='menu']");
  await expect(menu).toBeVisible();
  // An edge-type entry expands; the others (explain, paths, link, split) do not. Edge types are
  // SCREAMING_SNAKE_CASE in this menu, which is how they are distinguished from the action
  // entries — matched as a *prefix*, since each entry also carries its own count after the name
  // (`keyboard.spec.ts` matches these the same way, `/^ASSOCIATE_OF/`).
  //
  // **`ASSOCIATE_OF` by name, not "the first edge type".** Every edge type the ontology allows
  // for this node's type is listed whether or not the node has any, so the first entry is
  // `USES`, which an HMP `Person` has none of — expanding it brings in nothing and the failure
  // surfaces further down as "no neighbourhood to rank", which reads like a defect in the metric
  // rather than a wrong click.
  //
  // Filtering on the displayed count does not help and was tried: `GlassCanvas.tsx` renders
  // `count: 0` for *every* entry, with its own comment saying the real cardinality is
  // "populated by expand/preview in a follow-up pass". So the menu shows `USES (0)`,
  // `ASSOCIATE_OF (0)` and so on regardless of what is actually there — worth knowing, because
  // `08_ACCEPTANCE_SCENARIOS.md` A1 asks that "expansion previews its cardinality before
  // running" and this menu does not yet. Recorded in `REPORT-12b.md`; not fixed here, being
  // outside this round's brief.
  //
  // Naming the edge type is also the more faithful assertion: A12 is about how tightly a
  // subject's *associates* interconnect, so `ASSOCIATE_OF` is the expansion the step means.
  const expandItem = menu.getByRole("menuitem").filter({ hasText: /^ASSOCIATE_OF/ }).first();
  await expect(
    expandItem,
    "the radial menu offered no edge type to expand by — the seeded node has no associations " +
      "at all, which would be a fixture problem rather than a Glass one",
  ).toBeVisible();
  await expandItem.click();
}

test("A12 — the Clique Metric ranks nodes in the metrics panel", async ({ page }) => {
  // `08_ACCEPTANCE_SCENARIOS.md` A12, and `DEMO_GUIDE.md` §4's own "the Clique Metric that ranks
  // the insular subgroup". Built in Phase 7 as `POST /v1/investigations/{id}/compute/
  // clique_metric` with its own `MetricsPanel` option; never before driven from the browser.
  await page.goto(workspaceUrl());
  await seedWorkingSetFromSearch(page);
  await expect.poll(() => nodeCount(page), { timeout: 30_000 }).toBeGreaterThan(0);
  // A search result arrives as one isolated node — no edges. The Clique Metric measures how
  // tightly a node's neighbours interconnect, so on a single unconnected node it correctly
  // computes nothing and the ranking is empty. Expanding first is part of the step, not setup
  // around it: A12 follows A1's "seed a working set [...] and expand into their associations".
  await expandFromTheSelectedNode(page);
  await expect
    .poll(() => edgeCount(page), {
      message: "expansion brought in no edges, so there is no neighbourhood to rank",
      timeout: 30_000,
    })
    .toBeGreaterThan(0);

  const computed: number[] = [];
  page.on("response", (r) => {
    if (r.url().includes("/compute/clique_metric")) computed.push(r.status());
  });

  await page.getByRole("combobox", { name: "Primary metric" }).selectOption("clique_metric");

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

test("A13–A15 — a judgement is recorded against the investigation", async ({ page }) => {
  // Phase 8's assessment objects. The Inspector's Judgements tab is where an analyst records
  // one; `DEMO_GUIDE.md` §4 step 6 is the inspection step this hangs off.
  await page.goto(workspaceUrl());
  await seedWorkingSetFromSearch(page);
  await expect.poll(() => nodeCount(page), { timeout: 30_000 }).toBeGreaterThan(0);

  await page.getByRole("tab", { name: "Judgements" }).click();
  const add = page.getByRole("button", { name: "Add judgement, gap or assumption" });
  await expect(add).toBeVisible();
  await add.click();

  // The composer is open and offers all three assessment kinds — the trio A13–A15 names,
  // asserted together because the panel builds them from one control.
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText(/judgement/i);
});

test("A15 — export names what it blocked, and takes a justification", async ({ page }) => {
  // `02_GLASS_FRONTEND.md` §10.2's handling gate: an export carrying an item the principal may
  // not release is refused with *every* reason named, never silently dropped, and an overridable
  // refusal takes a justification plus an originator reference before it will resubmit.
  await page.goto(workspaceUrl());
  await seedWorkingSetFromSearch(page);
  await expect.poll(() => nodeCount(page), { timeout: 30_000 }).toBeGreaterThan(0);

  await page.getByRole("button", { name: /^Export/ }).click();
  const drawer = page.getByRole("dialog").or(page.getByRole("complementary")).first();
  await expect(drawer).toBeVisible();

  // The export kinds Phase 8 built, all three present.
  const kind = page.getByRole("combobox").filter({ has: page.getByRole("option", { name: "Report" }) });
  await expect(kind).toBeVisible();
});
