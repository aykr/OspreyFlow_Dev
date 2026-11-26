# PL4h, round 7: four timeout arguments (the conductor, 25 November 2026, 20:55 UTC; the owner's option (a))

From the round-6 verifier's record (tip `380afc49fd`). Round 6's shape stands (main's files, one constant, per-test
arguments, no cache). **This round is the row below and nothing else.**

| # | Do | Done when |
| --- | --- | --- |
| 1 | The ruling is literal: every test that **walks or parses**, a short string handed to the parser included. Give `GUARD_TEST_TIMEOUT_MS` as the third argument to the four parsing tests without it: in `copyNoClient.test.ts`, "is found in each shape the copy took before this change (rule 15)" and "leaves alone what is not copy"; in `copyWords.test.ts`, the same two. Reword the kit's comment to say what the code does: the constant goes on each test that walks or parses. | `git diff main` on the three files shows only the constant, its comment and third arguments, and every `it` that calls the walk or the parser carries it. Round 6's plant record still holds. |
