# live-drift: the live specs held to today's Glass

On 14 November 2026, on stack g (ospreyflow-test), under the orchestrator's grant. The stack was brought down and released afterwards. The runner was `process/lanes/case/live/run_search_results_live.sh`, through `stack_lease.sh remote`, with `LIVE_SEED` and `LIVE_SPECS` set per run. The red is main's own code for these specs: the runs at 5f071e7, in `../live-fresh-case/fixed.*.5f071e7.log`, where fixture-corp passed 0 of 5 and scenario-a 1 of 3.

## What changed in the specs, and why

| Change | Why | Proved by |
|---|---|---|
| fixture-corp chooses its suggestion by the record's position in the box's own `/suggest` answer | Options are now named by value (`displayValue`), and the resolution pairs share their names, so a name can't tell `-1` from `-2` | The NINO case and the threshold case pass |
| The threshold summary reads "Match strictness: …" | `ThresholdControl.tsx`'s words since ADR-097 step 3 | The threshold case passes |
| The query builder's side panel is unfolded first | `SidePanelStack`'s DEFAULT_FOLDED folds every panel but the Inspector | Not yet: see below |
| Every dialog is picked out by its name, heading or close button | The welcome panel is a dialog too, and showed on every first visit. A13's bare lookup matched two dialogs. A15's `.first()` over every dialog could pass on the welcome panel alone, without the export drawer | A13 and A15 pass, A15 now with the drawer "Export" found by name |
| The working set's counts are read through `live.ts`'s `workingSetCounts`, which finds the status bar by a number followed by "nodes" | `getByRole("status").first()` read another live region, or waited a whole test out. The bar's text runs the pairs together ("0 nodes0 edges"), so `\bnodes\b` matched nothing; my own first try made that mistake and its run showed it. Numbers are en-GB ("1,234") | Each count is read |
| A12 no longer asserts that a chosen suggestion arrives with no edges | A chosen suggestion is drawn with the links around it (`drawSearchResult`, SEARCH_DRAW_DEPTH 3) | — |
| A failure says what the page holds and what errors it raised | So a cause is read, not guessed (`pageErrors`; the runner prints a failure's whole error context) | It found the crash below |

## Where they stand at 86af88e

- **scenario-a-a12-a15: 2 of 3** (`scenario-a.last.log`). A13 and A15 pass. A12 fails on a product crash, not drift (see "A product crash" below).
- **fixture-corp: 2 of 5** (`fixture-corp.last.log`). The threshold and NINO cases pass. Still failing:
  - **The query builder:** its "Entity type" control isn't there even with its panel unfolded. The cause hasn't been seen yet; the next run will print the page tree.
  - **Explain and the pathfinder:** both expect exactly two nodes after two searches, and got 6 and 7. Each chosen suggestion now draws three hops around its record, so the specs' premise is gone, not just a locator. They need a new way to put exactly their pair in the selection. With no keyboard hook in the real Glass, and names the pair share, that is a redesign of the two cases, not drift.

## A product crash, found live

In scenario-a's A12, with a fresh case reading the HMP fixture, the spec chooses the search suggestion for `HMP-0003`. The Glass then throws `NotFoundError: Failed to execute 'insertBefore' on 'Node': The node before which the new node is to be inserted is not a child of this node.` React throws the whole tree away: `#root` is left empty and focus is on `<body>`. It happened on every A12 run (`scenario-a.blank-page.log`, then `scenario-a.last.log` with the page's errors). Fixture Corp's suggestions, chosen the same way, didn't crash.

This is not proven, but the lead is the search box's own path. A chosen suggestion is seeded and then expanded three hops (`drawSearchResult`). The search-results page's Show on graph seeds without expanding, and never crashed in its live runs. `HMP-0003`'s case holds 1,203 entities, so its three hops may reach the working-set cap, or an overlay the canvas draws into the container Sigma also writes to. It needs its owner and a reproduction outside the live tier.

## Blank pages under host load

The runner's warm-up records what the browser saw:
- At a load average of 26 (08:20Z) the Glass drew nothing for 10 minutes, and the Conduit received no request at all.
- At a load of 3 to 4 it drew in about a second.
- The blank first pages in the v052-results runs, at loads of 49 and 23, fit the same pattern.

A live run should note the host's load, and a first page that draws nothing should be read as the host, not the Glass, until shown otherwise. The runner prints both.

## Not run

| Spec | Why |
|---|---|
| `basemap.spec.ts` | Needs a PMTiles basemap build |
| `ingest-folder.spec.ts` | Needs a staged ingest folder |
| `scenario-b-document.spec.ts` | Needs an extraction model |
| `ledger-capture`, `pid-capture` | Capture kits with their own configs, not checks |

## For step 6 on the 25th: the live specs to run

Each runs through the runner on one stack (`LIVE_SEED` and `LIVE_SPECS`), so the case, the index's drained outbox and a warm Vite are set up the same way each time. Each run records the host's load.

| Spec | Seed (`LIVE_SEED`) | Expected on the 25th | What a red means |
|---|---|---|---|
| `live/search-results.spec.ts` | `scripts.seed_fixture_corp` (the default) | 4 of 4, as on 14 November | The results page or the search route has changed |
| `live/scenario-a-a12-a15.spec.ts` | `scripts.seed_hmp_fixture` | A13 and A15 pass. A12 passes once the crash above is fixed, and until then is the crash's own check | A13 or A15 red is drift or a defect; A12 red is still the crash |
| `live/fixture-corp.spec.ts` | `scripts.seed_fixture_corp` | The NINO and threshold cases pass. The query builder, explain and pathfinder cases are red until they are reworked as above | The two passing cases going red is drift or a defect |

Not for the 25th until their needs are on the stack: `basemap.spec.ts` (a PMTiles build), `ingest-folder.spec.ts` (a staged folder) and `scenario-b-document.spec.ts` (an extraction model). The capture kits (`ledger-capture`, `pid-capture`) are not checks.

A red in the table, or a known red that is still red, goes in the step's record by name, so drift is seen when it starts, not found months later as it was here.
