# PL4h, round 5: one row (the conductor, 25 November 2026, 20:08 UTC; the owner's option (a) stands)

From the round-4 verifier's record (tip `174bc2aea8`). **This round is the row below and nothing else**; round 4's
other work (the sharing taken back, the plant standing) is kept.

| # | Open case | Done when |
| --- | --- | --- |
| 1 | **The timeout is raised for every file that imports the kit**, by `vi.setConfig({ testTimeout: GUARD_TEST_TIMEOUT_MS })` at `copyTextsTestKit.ts`'s module scope: every test in every importing file gets 30 s, `auth/resolvedPrincipal.test.ts` and tests that read no file included. Option (a) is a timeout **on each test that walks or parses, and only those**. | No `vi.setConfig` (or any file-, suite- or config-wide timeout) anywhere in the slice. The kit exports the constant with its comment. Each walking or parsing test in `copyNoClient` and `copyWords` passes it as that test's own timeout argument (`it(name, fn, GUARD_TEST_TIMEOUT_MS)`). A test that reads no file keeps vitest's default, shown by a case that asserts it. The plant still passes inside the per-test timeouts, and taking one test's timeout out fails that test under the plant. |
