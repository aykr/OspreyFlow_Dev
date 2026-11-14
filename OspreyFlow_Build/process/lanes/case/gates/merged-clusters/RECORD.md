# Step 3h: clusters per reader (ADR-124 Amendment 19)

## Red first

`merged_clusters_reds.py`, 11 of 11 red at 01181bd (`merged-clusters-reds.01181bd.log`). Among them:
- **The old shared path, planted back whole.** It sends a reader not cleared for H `{p-v: p-h, p-x: p-h}`: the hidden
  member's id, and V and X joined through it.
- **The stream-first defect.** Its plant is the eleventh.

## On stack b

The lease was taken 11:37Z, under the orchestrator's grant, and the stack was released afterwards.
- **The working-set tests against ArcadeDB: 321 of 321** (`3h-live-pytest.log`, then `3h-live-pytest2.log` after the
  explain access test was held to the amendment).
- **The API replay of the explain flow** (`3h-diag2.log`): seed, seed, expand by SAME_AS, threshold to Strict. Each
  answer carries the right clusters.
- **fixture-corp live, run 1** (`3h-live-corp2.log`, load 6.8). The stream-first defect, found here:
  - *What happened:* the case's stream drew the Same as expansion's add before its answer landed. The canvas said
    "Nothing new" for four people added, and that notice held its keys, so *Explain cluster*'s menu never opened.
  - *The fix:* f9bc8d2 judges *nothing new* against what the canvas held when the expansion was asked for. Its red case
    is `keyboard/canvas-expand-stream-first.spec.ts`.
  - *Scope:* this is outside Amendment 19's own scope, which is the clusters, but it is named in its tests because the
    amendment's live check found it.
- **fixture-corp live, run 2** (`3h-live-corp3.log`): **unmeasured.** The host's load was 56, the pages drew blank, and
  the status bar and search box never appeared. It is neither a pass nor a fail.

## Still to run

In the orchestrator's order, after rules-b's full run and the osprey-small update:
1. `make test`, then `make -k ci`, offline on the server.
2. fixture-corp's explain case live on stack b, taken only when `uptime` shows a load under 16, with the load and the
   lease recorded with the log.
