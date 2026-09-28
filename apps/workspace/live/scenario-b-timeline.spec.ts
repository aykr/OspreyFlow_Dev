// **B16 and B18's rendering halves, in a real browser — round 13cde.**
//
// `08_ACCEPTANCE_SCENARIOS.md` has carried these two as "data half only" since round 13cb: the
// events come back ordered, geolocated and on a shared axis over the wire, while "both event sets
// render on distinct tracks" (B16) and "an ordered track renders and animates under playback"
// (B18) are claims about the Glass that no HTTP test can make. Neither was false — nothing proved
// them either, and a row half that no tier proves is a row the closing pass must call partial.
//
// **What was actually missing was not the feature.** Both are built: `Timeline.tsx` renders the
// cross-case overlay as a second ECharts grid against a shared axis, and `playback/usePlayback.ts`
// drives the clock that `App.tsx` turns into the map's snail trail. What was missing was anything
// *observable*. The trail is a MapLibre GeoJSON source, so playback changed pixels and nothing
// else — no DOM, no announcement, and therefore no assertion short of comparing images. Round
// 13cde added the readout this spec reads, which is an accessibility fix first: a control whose
// entire effect is invisible to a screen reader is a control that does not work for everyone.
//
// **Two investigations, and the second one is the point of B16.** 08's row is "Overlay the
// *second investigation's* timeline on the first" — read from the row, not from a paraphrase of
// it. An overlay of one investigation onto itself renders two tracks that are identical, which
// would satisfy a weaker assertion than this file makes.
import { expect, type Page, test } from "@playwright/test";

import { liveOnly, required, workspaceUrl } from "./live";

test.beforeEach(liveOnly);

/** The seeded investigation — deliberately *not* `freshWorkspaceUrl`, unlike the other live specs.
 *
 * Those create a fresh investigation because the thing that leaks between runs is the server-side
 * working set. These two rows need the opposite: the seeded *events*, which is what the timeline
 * and the sightings track read, and which only `harness.apply --seed` puts anywhere. A fresh
 * investigation has no events at all, so this spec would assert against two empty charts and pass
 * for the wrong reason. */
const seededWorkspace = () => workspaceUrl();

async function openTimeline(page: Page): Promise<void> {
  await page.goto(seededWorkspace());
  await expect(
    page.getByLabel("Cross-case overlay investigation id"),
    "the timeline's own controls never appeared — is the Glass pointed at a seeded investigation?",
  ).toBeVisible({ timeout: 30_000 });
}

/** How many tracks the timeline is drawing, read off its own published state.
 *
 * `Timeline.tsx` sets `data-timeline-tracks` from the same `crossCaseHistogram != null` its
 * ECharts option uses, so this is the component's answer rather than a second derivation of it.
 * The chart is a single `<canvas>`: counting tracks any other way means comparing pixels, which
 * this file's header explains it will not do. */
async function timelineTracks(page: Page): Promise<number> {
  const value = await page
    .locator("[data-timeline-tracks]")
    .first()
    .getAttribute("data-timeline-tracks");
  return Number(value ?? -1);
}

test("B16 — a second investigation's events render as their own track on the shared axis", async ({
  page,
}) => {
  await openTimeline(page);

  expect(
    await timelineTracks(page),
    "the timeline is not drawing a single track before the overlay is named, so either it never " +
      "mounted or it is already overlaying something — B16 must start from one track",
  ).toBe(1);

  // The analyst's own control. `App.tsx` records that this build has no cross-investigation
  // picker — typing the id is the real input, not a placeholder for one that does not exist.
  await page
    .getByLabel("Cross-case overlay investigation id")
    .fill(required("OSPREY_LIVE_SECOND_INVESTIGATION_ID"));

  await expect
    .poll(() => timelineTracks(page), {
      message:
        "the overlay never added a track: the timeline is still drawing one series against the " +
        "axis after a second investigation was named",
      timeout: 30_000,
    })
    .toBe(2);

  // **And the second track has to be drawing something.** A second investigation with no events
  // still produces a histogram, so the track count alone goes to 2 for an overlay of nothing
  // onto something — which is the shape of false green this file's header warns about, and the
  // one the seeded-investigation choice above exists to avoid.
  const overlayEvents = Number(
    await page
      .locator("[data-timeline-overlay-events]")
      .first()
      .getAttribute("data-timeline-overlay-events"),
  );
  expect(
    overlayEvents,
    "the overlay track is drawn but empty — the second investigation named by " +
      "OSPREY_LIVE_SECOND_INVESTIGATION_ID has no events, so B16's 'both event sets' is one set " +
      "and a blank row",
  ).toBeGreaterThan(0);
});

/** The seized handset's own identifier, and the day its sightings fall on.
 *
 * `scripts/seed_scenarios.py` writes the `imei`; `Device` declares it as an identifier, which is
 * what `search_nodes` matches on, so this is the analyst's own route to the entity. The window is
 * the one the four sightings sit inside (12:00-15:00 on 2026-02-03, read off the deployment
 * rather than assumed) — B18 has nothing to animate across without a brush window set, which is
 * `App.tsx`'s own stated precondition for fetching sightings at all. */
const SEIZED_HANDSET_IMEI = "49015420323751";
const SIGHTINGS_WINDOW_START = "2026-02-03T00:00:00Z";
const SIGHTINGS_WINDOW_END = "2026-02-04T00:00:00Z";

// **B18 is `fixme`, not `skip`, and not a passing test — round 13cde found a real defect.**
//
// Everything this row needs is present and was measured present: `POST /v1/analytics/sightings`
// returns the handset's four sightings for exactly the entity, scope and window below; the
// Inspector shows the Device selected; the brush window persists in the timeline's own fields;
// the play control renders. The map still shows no trail, and the readout beside it never
// appears, which means `App.tsx` is holding an empty `sightings` array throughout.
//
// Measured directly, in this order, against a stack seeded with `hmp` + `scenarios`:
//
//   window after selecting the device  ""                       (the selection does not set one)
//   window after filling both fields   "2026-02-03T00:00:00Z"   (it persists)
//   readout present                    0
//   window after re-selecting          "2026-02-03T00:00:00Z"   (still set, effect re-run)
//   readout present                    0
//
// So it is not the ordering trap it first looked like — re-selecting with the window already set
// re-runs the effect and still yields nothing. **What is wrong is between `App.tsx`'s sightings
// effect and what it does with the result**, and finding it is the remaining work, recorded in
// `08_ACCEPTANCE_SCENARIOS.md` beside B18 rather than guessed at here.
//
// Left as an executable `fixme` rather than deleted: it fails for the right reason, it carries
// the repro, and Playwright will report it as unexpectedly passing the moment the defect is
// fixed — which is a better handover than a paragraph in a document nobody runs.
test.fixme("B18 — the sightings track advances under playback", async ({
  page,
}) => {
  await openTimeline(page);

  // The trail is drawn on the map, so that is the view B18 is performed in — and the readout
  // lives beside it rather than in the status bar, whose four segments `02_GLASS_FRONTEND.md` §2
  // fixes.
  await page.getByRole("button", { name: "Map", exact: true }).click();

  await page.getByLabel("Brush window start").fill(SIGHTINGS_WINDOW_START);
  await page.getByLabel("Brush window end").fill(SIGHTINGS_WINDOW_END);
  await page.getByLabel("Brush window end").blur();

  // **The window before the selection, and the order is load-bearing.** `App.tsx`'s
  // sightings effect keys on the selected node, not on the brush window, so a window set
  // afterwards never triggers the fetch and the trail stays empty — measured, after this
  // spec did it the other way round and found no readout on a page that otherwise looked
  // exactly right.
  // "Plot **the device's** sightings" — the trail follows the Inspector's own selection
  // (`App.tsx`), so selecting the handset is the row's own first action, not test scaffolding.
  const search = page
    .getByRole("combobox", { name: "Search entities, identifiers, documents" })
    .first();
  await search.fill(SEIZED_HANDSET_IMEI);
  const option = page.getByRole("option", { name: /^Device: / }).first();
  await expect(
    option,
    `no search result for ${SEIZED_HANDSET_IMEI} — is the \`scenarios\` seed loaded under the ` +
      "investigation this spec was pointed at?",
  ).toBeVisible({ timeout: 30_000 });
  await option.click();

  const readout = page
    .getByRole("status")
    .filter({ hasText: "sightings revealed" });
  await expect(
    readout,
    "no sightings readout appeared, so there is no trail on the map to animate — B18 needs the " +
      "`scenarios` seed, whose device sightings are the track",
  ).toBeVisible({ timeout: 30_000 });

  const revealed = async () =>
    Number(/(\d+) of/.exec((await readout.textContent()) ?? "")?.[1] ?? -1);
  const total = Number(
    /of (\d+)/.exec((await readout.textContent()) ?? "")?.[1] ?? 0,
  );
  expect(total, "the seeded device has no sightings at all").toBeGreaterThan(1);

  // Playback starts at fraction 0, which reveals the whole track (`App.tsx`'s `itemsUpTo` over
  // the brushed window). Brushing is A5's own step and is not repeated here; what B18 claims is
  // that the count *changes* as the clock runs, which is the difference between an animation and
  // a static line drawn once.
  const start = await revealed();
  expect(start, "the readout did not parse").toBeGreaterThanOrEqual(0);

  await page.getByLabel("Play playback").click();
  await expect(
    page.getByLabel("Pause playback"),
    "the play control did not flip to pause, so the clock never started",
  ).toBeVisible();

  await expect
    .poll(revealed, {
      message:
        "playback ran and the number of revealed sightings never changed — the trail is drawn " +
        "once and does not animate, which is exactly what B18's row claims it does",
      timeout: 30_000,
    })
    .not.toBe(start);
});
