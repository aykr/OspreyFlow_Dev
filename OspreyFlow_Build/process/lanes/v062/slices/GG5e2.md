# Slice GG5e2 · GG5 · Site plans' rotation and pitch: the map turned to a plan's own axis and tilted, by buttons and by keys, and said in words with scripts off (a draft)

**Status: a draft, not ruled.** Written in an away drafting session (D246), 26 to 27 November 2026, on the branch
`drafts/2026-11-27`, read from `origin/main` at `7f4f9554a`. No row in `slices.tsv`; no builder starts from this paper.
**Size S.** Release scope A-full (D273). **It needs GG5e1 built** (a calibrated plan on its page). It draws nothing
with Sigma.

**Where it comes from.** Backlog row **N22** (proposed as N19-07: "D48: site plans' rotation and pitch", owned by GG5,
the owner's answer 22 of 19 November; `process/lanes/v062/backlog/N16_N22_RENUMBERED_2026-11-21.md:15`). ADR-152's
"Not decided here" names it: "site plans' rotation and pitch (D48, a backlog row owned by GG5)"
(`spec/06_DECISIONS.md:41279`). **That is all the repository says.** D48's own words are not in the repository, and
`spec/02` §3.5 says nothing of rotation or pitch (searched: no "rotation", "pitch" or "bearing" in `spec/02` or `spec/08`).
This is a spec gap (rule 11): the slice's first step is the spec's text.

## What exists today (read on `origin/main` at `7f4f9554a`; re-read, lines move)

- **Rotation and pitch are locked wherever the graph is drawn over the map.** The local port of the Sigma layer sets
  `minPitch: 0`, `maxPitch: 0` (`apps/workspace/src/map/sigmaMaplibreLayer.ts:84-85`) and
  `enableCameraRotation: false` (:91-92). On `away/WS4b`, `@sigma/layer-maplibre` 4.0.1 replaces the port and "fixes
  pitch at 0 and turns rotation off itself, as the port did" (`away/WS4b:OspreyFlow_Core/apps/workspace/src/map/MapView.tsx`,
  the import's comment; `WS4b_AWAY_REPORT.md` case 7: "the package sets `enableCameraRotation: false` itself"). **So a
  map that draws the graph layer (GG5f) cannot turn or tilt**, and a plan can only be turned on a map drawn by MapLibre
  alone (GG5b's circles, GG5e1's plan).
- **A plan's axis is known.** The four control points are stored in top-left, top-right, bottom-right, bottom-left
  order (`services/api/sites.py:46-60`), so the direction from the top-left to the top-right point is the plan's own
  "across", and the plan's "up" is a quarter turn from it.
- **No React control turns the map**: the workspace's map has no bearing or pitch control and no keyboard id for one
  (`MAP_VIEW_ACTIONS`, `packages/glass-shared/src/keyboard/actionRegistry.ts:992-998`).

## Acceptance (red before, green after)

`spec/02` §3.5 gains a "Rotation and pitch" row (question 1's answer), and scenario **MP** a site-plan row for it,
written first; the site page's browser spec (the map turned to the plan's axis and tilted, by buttons and by keys) and
`apps/pages/test/govuk/site-plans.test.ts` (the words with scripts off), red on GG5e1's page, green after.

## Questions for the owner (the proposal first)

1. **What D48 asks for (owner: client-facing scope; its words are not in the repository).** Whatever the answer, it is
   written into `spec/02` §3.5 in this slice, before the code (rule 11), never left in a reply. (a) **On a site plan's
   page: "Turn to the plan" (the map's bearing set so the plan's top is up), "North up", turn left and right by 15°,
   and tilt (0°, 30°, 60°) and flat**; written into `spec/02` §3.5 as a row. On the map page with the graph layer
   (GG5f), no turning or tilting, said in words. (b) Rotation only, no pitch. (c) The owner's words for D48.
2. **The plan's bearing.** (a) **A pure function in `glass-shared` (`planBearing`), from the top-left and top-right
   points**, the bearing of "up" in degrees from north, 0 to 359, tested on synthetic plans at 0°, 90° and 135°.
   **A mirrored plan is not refused anywhere today**: `formsASimpleQuadrilateral` accepts either winding
   (`packages/glass-shared/src/site/bilinear.ts:89`, "every turn positive, or every turn negative"), and the Conduit
   checks no shape (`set_site_control_points`, `services/api/app.py:10267-10287`). So `planBearing` reads the four
   points' winding as well and answers "mirrored" for a plan whose points run the other way; the page then says
   "This plan's points were placed in mirror order, so its top cannot be found: place them again", and offers no "Turn
   to the plan". (b) From all four points, averaged, with the same mirror check.
3. **Keys.** (a) **The buttons are the keyboard route** (each a `<button>`, each a keyboard case, ids in the page's map
   registry), and MapLibre's own keys (Shift and the arrows turn and tilt) are left on when the map has focus, except
   while GG5d's boundary drawing uses the arrows. (b) MapLibre's keys alone: not proposed, since they are not
   discoverable and rule 13 needs a case per action.
4. **Scripts off.** (a) **The plan's picture is shown as uploaded, with the sentence "The top of this plan points
   <n>° east of north" (or west)** from `planBearing`; nothing turns. (b) A parity line (the owner's file).
5. **Kept in the address.** (a) **`&bearing=` and `&pitch=` in the page's address**, so a reload or a shared link keeps
   the view; out-of-range values are said in words and ignored. The page writes the bearing 0 to 359; MapLibre 6.19
   wraps it to −180 to 180 (`setBearing`, `wrap(bearing, -180, 180)`, read in `maplibre-gl-dev.mjs` 6.19.0 from an
   installed copy, `~/away-ci/OspreyFlow_Core/node_modules`, about line 51910) and its default `maxPitch` is 60
   (about :58649). (b) Not kept.

## The table of cases (each red first; the planted fault at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | A plan whose top points 135° from north; "Turn to the plan" | the map's bearing 135° (MapLibre's bearing is the direction at the top of the screen, so the plan's top is up), read back from the live map | the bearing negated (225°: the plan upside down) |
| 2 | "North up" | bearing 0 | the bearing left |
| 3 | Turn left, turn right from north | the page sends 345 and 15 (its own 0 to 359), and the live map reads back −15 and 15 (MapLibre's −180 to 180) | 360 sent as is; or the read-back compared with the page's 345 (a case that only passes if MapLibre does not wrap) |
| 4 | Tilt 30°, 60°, flat | pitch 30, 60, 0, read back | the pitch set beyond the map's `maxPitch` and left clamped silently |
| 5 | The image and grid under a turn and a tilt | each of the plan's four corners drawn at its point (MapLibre's projection of each) | the image's coordinates recomputed from the screen after the turn |
| 6 | `planBearing` | 0°, 90°, 135° for the synthetic plans | east and west swapped |
| 6b | A plan whose four points were placed in mirror order (stored: nothing refuses it) | `planBearing` answers "mirrored"; the page says so and offers no "Turn to the plan" | the winding not read (a bearing 180° wrong offered as the plan's top) |
| 7 | Scripts off | the sentence with the plan's bearing | no sentence |
| 8 | `&bearing=400` | said in words, ignored | 400 passed to the map |
| 9 | The map page with the graph layer (once GG5f exists) | no turn or tilt offered; the sentence | the buttons offered on a map whose layer resets them |
| 10 | Keyboard | each button reached and working (rule 13); Shift and the arrows turn the focused map | a button out of the tab order |
| 11 | I2 | no violation with the map turned and tilted | a style attribute set to turn a control's icon |

## Waits on

GG5e1 built (a calibrated plan on its page); GG5d (its arrow-key drawing, which the map's own keys must not take while
a boundary is drawn); the owner's question 1 (what D48 asks for). GG5f only for case 9.

## Files touched

`spec/02` §3.5 (the row), `spec/08` (MP's row); `packages/glass-shared/src/site/` (`planBearing` and its tests); `packages/glass-shared/src/keyboard/actionRegistry.ts` (the page service's site registry, the buttons' ids);
`apps/pages/modules/map/` (the controls), `server/views/` (the words), `tree-govuk/` (the site page's controls); the
tests above, `test/govuk/keyboard/sites.spec.ts`.

## Checks (frozen when cut)

GG5e1's list.

## Out of scope

Rotation in the React workspace (no row asks for it there); turning the graph layer (it cannot: GG5f); a stored bearing
for a site (the view's, never the site's); any Conduit change.


## The owner's answers (the owner's answers of 27 November 2026, after 09:40 UTC; RULINGS.md)

1. **Q1 (a):** the controls are: turn to the plan, north up, turn by 15 degrees, and tilt at 0, 30, 60 and flat. **Write them into `spec/02` §3.5 first**, as their own commit, then build them.

Every other question in this draft stays (a) on the owner's standing word.
