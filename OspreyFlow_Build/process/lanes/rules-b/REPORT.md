# rules-b lane · report · T3b, the contrast probe's limits, its server round and the review fixes (10–11 November 2026)

(T3's report is in git history, at ea3ba26 and before. T3b's first gating, at d41df45, is at 8eb8c95; its gating at
be4052a, sent back by the orchestrator's review of 9697ad3, is at 9697ad3.)

1. **CARRIES rows 110 and 121: met at d41df45.** Show as BPMN's task box is measured, and the probe's limits are
   closed (`t3b/RED_RECORD.md`).
2. **The server round (be4052a)** judges the probe alike on every platform:
   - a shadow is measured by what Chromium paints at each point;
   - hidden points are not judged, and words hidden at every point are unmeasurable;
   - every scroll is restored.
3. **The orchestrator's review of 9697ad3, item by item** (`t3b/REVIEW_FIXES.md`), then my lane-reviewer's pass on
   d677105. Its records findings are answered by this report, the gates and the commits below.
   - **Item 1** (d677105, f5a4b4c): the guard plants are committed in `a11y/plants/`, run by
     `node a11y/plants/run.mjs`.
     - The runner writes 16 guard-removed variants of the probe outside the repository.
     - Every covering plant is a real failure read in pixels: under 4.5:1 under the cover, 14.74:1 beside it.
     - Each guard passes the words silently without it: the opacity walk, the background clip, filter, blend, mask,
       mask border, the walk up from the cover, and the SVG exclusion.
     - Recorded unreachable, with why: clip-path, the slack, both corner cases, a nested `<svg>` (Chromium neither
       paints nor hit-tests its CSS background), and the clip narrowings. The flow and inline narrowings have no plant
       that reaches them.
   - **Item 2** (7befa52, 1d4b441): only the outermost `<svg>` may paint a CSS background, and a cover under a mask
     border hides nothing. Both are planted red.
   - **Item 3** (664ea74, 1d4b441): words hidden at every point are pinned to their own surfaces, and the findings file
     refuses a listing of them without a floor. Places' two GOV.UK listings are pinned at 19.59.
   - **Item 4: my earlier retake sentence was wrong.**
     - At be4052a, the canvas pair (`a11y.spec.ts`'s dark-theme canvas and `canvas-focus.spec.ts`) failed the first
       retake too, 20261111T141740Z, on load timeouts.
     - They passed only on the second, 20261111T142957Z (load average 37), with both files whole: 13 passed.
     - The three others passed on the first retake.
   - **Minor 1** (110c368, 1d4b441): a shadow's alpha is bracketed between what Chromium may paint at the least and
     the most, over the pixel round each point.
     - The least is the Gaussian less 0.0175 (0.0148 measured), and nothing near a rounded corner.
     - A lightness swap inside the bracket is 1:1.
     - It is measured in 12 geometries, including the tokens' negative spreads and sharp shadows at fractional edges.
     - The plant is red three ways.
   - The other minors: RED_RECORD's line 3, and the friction fragment as one row.
4. **Carried, for the orchestrator:**
   - (a) The bracket's worse-end rule rests on a search, not a proof. A coloured shadow can dip inside the bracket in
     one placement, but no case was found worse than every placement's ends; sampling inside could not be shown red,
     so it was not added.
   - (b) A pin for words hidden at every point reads no SVG shapes or shadows at those points.
   - (c) The flow and inline narrowings have no plant that reaches them.
   - (d) **CARRIES row, for the merge (owner: rules-b):** "every-harness's GOV.UK looks wait 5s for `data-brand`
     before the probe runs, and on the test server under load that wait timed out in every full run (4, 1, 4, 1
     tests). It is an environment wait, not a contrast finding: raise or replace it with a wait on the brand's own
     stylesheet."
   - (e) **CARRIES row, for the merge (owner: rules-b):** "every-harness's map-view looks scan before the map's
     attribution ('Harness tiles ©') is drawn when the server is loaded, so its listed finding is reported gone (once in
     each of two full runs, in different looks). Wait for the attribution before the scan."
5. **Findings:** nothing new listed.
6. **Gates**, all on the test server, slot 13 (`gates/f5a4b4c.browser.txt`, `gates/2515840.ci.txt`). 2515840 changes
   only a type guard after f5a4b4c.
   - **Browser set at f5a4b4c, two full runs.**
     - 20261111T154955Z, load average up to 17: 968 + 32 passed, 13 failed.
     - 20261111T161902Z (a `--last-failed` retake that found no record, so the whole set ran again): 976 + 34 passed,
       8 failed. The canvas pair and both harness screens passed there.
     - No new contrast finding in either run. Every failure was one of three things:
       - GOV.UK's 5s `data-brand` wait (8, then 7, in different looks: carry (d));
       - load timeouts (the canvas pair and two harness install screens in the first run);
       - map-view's listed "Harness tiles ©" not found, once in each run, in different looks: carry (e).
     - Diagnosed for (e), 20261111T164630Z at load 30, each look 5 times: the first repeat found no node at all,
       because the map's attribution was not yet drawn when axe ran. The other 14 measured as listed.
   - **`make -k ci` at 2515840:** exit 2, on `trivy-image-workspace` alone. That is libxslt 1.1.43-r3, the server's
     stale layer as at be4052a; this branch touches no image.
   - My own typecheck error at f5a4b4c (an `unknown` read) was red in the first run and fixed in 2515840.
   - **`make test`:** not re-run. The branch changes only the workspace's a11y probe, its judgement, their unit cases
     and the plants.
7. **Friction row:** `process/friction/2026-11-10-rules-b-contrast-probe.md`, one row. **Still running:** nothing.

## Decisions taken (each the recommended option; the owner may overrule)

1. **SVG shapes under a label's words.** Q: always a cover, or a surface? **Chose:** a surface, through a fail-closed
   allowlist.
2. **The point cap.** **Chose:** fail closed past 600 points.
3. **Decision 3's own reason under a cover.** **Chose:** record that axe changes its reason.
4. **A shadow's placement.** **Chose:** every place in the words' chain.
5. **Words hidden at every point.** **Chose:** unmeasurable, pinned to their own surfaces, with a floor required.
6. **σ.** **Chose:** measured from Chromium's pixels, and the alpha bracketed at both ends over the pixel.
7. **Where the plants' variants are written.** Q: a gitignored folder in the tree (which needs `.gitignore` and
   `eslint.config.js`, outside this lane's files), or the system's temporary directory? **Chose:** the temporary
   directory, so no file outside the lane changes.
8. **Sampling inside the bracket.** Q: add it unproven, or carry the search's finding? **Chose:** carry it (rule 15:
   code that cannot be shown red is an untested state).
