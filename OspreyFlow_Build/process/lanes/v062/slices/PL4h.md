# Slice PL4h · PL4 · The two copy tests hold under a loaded machine: one walk per file, or an explicit, explained timeout (a test-only part; the owner, 25 November 2026)

- **Build id:** PL4 (the shared package and the copy guards that read it)
- **Dial setting:** balanced
- **Rounds limit:** 8
- **After:** nothing
- **A test-only part with a planted fault** (`plants/PL4h.patch`, committed on main before the start: the line's rule of
  24 November). The fault adds a 6-second busy wait to `sourceFiles` in `copyTextsTestKit.ts`, a walk as slow as a
  loaded server makes it.

## What (the owner's words)

The demo server reproduced its unnamed `test-js` reds: **`apps/workspace/src/copyNoClient.test.ts` and
`copyWords.test.ts` time out at vitest's 5 s under load** (1.5 to 2 s alone; 5.4 to 7 s in the full suite). Each test
calls `sourceFiles()` (`copyTextsTestKit.ts` about line 21) again, so each walks and reads the whole source again (7 calls
a file). **Make them faster, or give each an explicit, explained timeout.**

1. **Walk once per file** (for example the walk and its texts made once, in a `beforeAll` or a module-level value the
   tests share), so no test pays for the walk again; the planted cases (`plantedCopy`, `plantedLinkClients`, ...) still
   read the same walk's result, and each still finds the word it plants (rule 15: the guard stays shown able to fail).
2. **If a test must still walk, give it an explicit timeout with a comment saying why** (the walk, its size, the loaded
   server's figure), never a timeout raised for the whole suite or the config.
3. Nothing the two guards check changes: the same files walked (a test compares the walked list before and after, or
   with `sourceFiles()` called directly), the same words found.

## Acceptance test

`cd OspreyFlow_Core && npm exec --workspace apps/workspace -- vitest run src/copyNoClient.test.ts src/copyWords.test.ts`.
On main it is green; **with the planted fault it is red** (every test that walks times out at 5 s), which the merge
checks on an assertion. **After the part, with the fault applied by hand in your worktree, it is green** (the walk is
paid once, inside a hook with its own explained timeout): show that in your report (the line does not run it), then
take the fault out again; never commit it.

## Checks

The acceptance; `npm test --workspace apps/workspace` (the whole workspace suite, both its configs); `npm run lint`;
`npm run typecheck`; `node scripts/no_react_check.mjs` is not affected (the workspace).

## Out of scope

`MatrixView.budget.test.tsx`'s timing on the server (line-fix: the server should not judge timing budgets); vitest's
config or any global timeout; any product code.
