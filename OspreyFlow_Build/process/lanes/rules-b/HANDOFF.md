# rules-b · handoff · T3b's review fixes, paused 11 November 2026 (moved to sol)

**Step:** T3b, the server round, on `lane/rules-b-t3b` (rebased onto a7bb34a; it merges clean onto 8aa3da5). Code head 7befa52.
The last gated head, 9697ad3, was sent back by the orchestrator's review: four must-fixes and five minors.
**The full list, with what is done and how to do the rest: `t3b/REVIEW_FIXES.md`.**

**Done:**
- item 2's code (7befa52): an SVG element other than the root is never opaque; a cover under a mask border hides nothing; shadows' corner radii read.

**Half done:**
- the alpha bracket (minor 1): `t3b/wip-alpha-bracket.patch`. It is uncommitted code, and its constant `SHORT_MEASURED` is not yet measured on the server.

**Not done:**
- item 1: each `hides()` guard shown red with that guard removed, on 13:1 words, with the plant files committed under `a11y/plants/`;
- item 2's plants (the SVG rect with a CSS background, a mask border);
- item 3: a real `own` pin for words hidden at every point, and the two places GOV.UK listings repinned (19.59 on main);
- item 4: REPORT's retake sentence (the canvas pair failed 141740Z too and passed at 142957Z);
- the minors: the friction row as one, RED_RECORD line 3, a CARRIES row for GOV.UK `data-brand`'s 5s wait.

**Then:** the browser set once on the server, slot 13; `make -k ci` through offline; "ready-to-merge" to the orchestrator by message.

**What was running:** nothing. No server run is alive and no lease is held.

**Open questions:** none.

**Must not redo:** the rebase; the server round's earlier plants and records. The scratch plants from this session are
in this Mac's session scratchpad (the path is in REVIEW_FIXES), and their shapes are in `t3b/server-round-plants.txt`.
