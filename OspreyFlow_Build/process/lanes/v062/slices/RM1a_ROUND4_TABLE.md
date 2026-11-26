# RM1a, round 4: take main in, change nothing (the conductor, 26 November 2026, on its own word; the owner's item 3)

The merge gate refused RM1a's verified tip `f35dd00` because of another test, not its own:
`apps/workspace` `MatrixView.budget.test.tsx` ("opens inside §5's first-frame budget"), which the server's run named red. The
Mac's rerun passed it (1756 ms) but recorded red because of two line faults (now with line-fix). RM1a changes no
`apps/workspace` file. **This round is the row below and nothing else.**

| # | Do | Done when |
| --- | --- | --- |
| 1 | Merge main into your branch. Keep both sides where they meet; change nothing else. If the merge conflicts, or a frozen check is red after it, stop and say which (do not fix another slice's test). | Your frozen checks green on the new tip. `git diff main...HEAD` is round 3's diff (only main's changes added). |
