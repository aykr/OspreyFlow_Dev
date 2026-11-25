# PL4h, round 4: the structural round (the conductor, 25 November 2026, about 19:50 UTC; the owner's ruling: option (a))

D225 item 3: rounds 2, 3 and 4 found the same kind of fault (work meant to be shared still done per test, or a plant
that misses it). **The owner chose option (a): explicit, explained timeouts; nothing shared, nothing moved.**
**This round is the rows below and nothing else.**

| # | Do | Done when |
| --- | --- | --- |
| 1 | **Take back the sharing.** Undo the round 2 and 3 changes that cache the walk or the texts, or that move a walk out of `sourceFiles`: every test walks and parses through the code it walked through on main. | `git diff main -- <the two test files and copyTextsTestKit.ts>` shows only row 2's timeouts, their comments, and nothing else. |
| 2 | **Every test in `copyNoClient` and `copyWords` that walks or parses, the plant tests included, gets its own explicit timeout with a comment**: the walk's size (files under each root), the loaded server's measured 5.4 to 7 s a walk, and the bound the timeout gives. One named constant, defined once, used by each. | A grep finds no walking or parsing test without it. |
| 3 | **The plant stands as written** (`plants/PL4h.patch`: 6 s a call in `sourceFiles`). With it applied, every such test still passes inside its timeout; with the timeout taken out of any one test, that test fails under the plant. | Shown both ways in the report, with the timings. |
