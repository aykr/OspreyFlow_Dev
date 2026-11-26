# PL4h, round 6: start again from main's files (the conductor, 25 November 2026, 20:25 UTC; the owner's option (a))

From the round-5 verifier's record (tip `e30efd4733`). Rounds 2 to 5 kept a cache that option (a) forbids (round 5's
table wrongly assumed round 4 had taken it back). **This round is the three rows below and nothing else.**

| # | Do | Done when |
| --- | --- | --- |
| 1 | **Restore from main**, as your first commit and with no other change in it: `git checkout main -- OspreyFlow_Core/apps/workspace/src/copyTextsTestKit.ts OspreyFlow_Core/apps/workspace/src/copyNoClient.test.ts OspreyFlow_Core/apps/workspace/src/copyWords.test.ts`, and delete `copyTextsTestKit.test.ts`. No `walkedOnce`, no `beforeAll`, no cache, no module-level walk or parse: `sourceFiles` is main's `export function sourceFiles(...)`, so `plants/PL4h.patch` applies **unchanged**. | `git diff main` on those files after this commit is empty. |
| 2 | **Then add only this:** one exported constant `GUARD_TEST_TIMEOUT_MS` in the kit, with a comment (files under each root; the loaded server's measured 5.4 to 7 s a walk; the bound it gives), passed as the third argument of each `it`/`test` in `copyNoClient` and `copyWords` that walks or parses, the plant tests included. No `vi.setConfig`, no file-, suite- or config-wide timeout. | `git diff main` on the three files shows only the constant, its comment and the third arguments. |
| 3 | **Show the plant both ways**, applying `plants/PL4h.patch` as it is: every such test passes inside its timeout; with the timeout argument taken out of one walking test, that test fails under the plant (vitest's 5 s). Record the timings in the report. | Both runs in the report, with the commands. |
