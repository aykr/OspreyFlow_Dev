# Slice GG2c · GG2 · The working set's delta client moves to `glass-shared`, behaviour unchanged (I11; from away/GG2c)

- **Build id:** GG2 · **Dial setting:** balanced · **Rounds limit:** the dial's · **After:** nothing
- **The owner's ruling (D268, 26 November 2026, 10:45): GG2c may merge before WS4b**, the one exception to decision 9.

## What

The draft is `slices/drafts_2026-11-26/GG2c.md`, every proposal (a). The client (`deltaClient.ts`) and its unit tests
(`deltaClient.test.ts`, `deltaOps.test.ts`) move to `packages/glass-shared/src/workingset/`, and the integration test stays
in the workspace. Its out-of-date header is corrected. No browser socket factory yet. `deltaClientHome.test.ts` (new) holds
that the client has one home: no copy and no relative import is left in the workspace. `deltaClient.exports.test.ts` (new)
holds the package's export.

## Round 1 (D247; the conductor, 26 November 2026): merge `away/GG2c` first

**Your first step: merge the local branch `away/GG2c` into your branch.** Its report,
`process/lanes/v062/away/GG2c_AWAY_REPORT.md` on that branch, is the record: read it whole. **Every figure in it was taken
on the server under its namespace, not on the Mac or CI.** Then run your frozen checks here and say what differs from
the report. The answers to its questions, for this round:

- **Q2 (a):** correct the case table to say what catches case 2's plant (the workspace's vitest run and the new guard
  test; `test_file_coverage_check` reads no TypeScript). A TypeScript half of that check is not this slice's.
- **Q4 (a):** keep `deltaClientHome.test.ts`.
- **Q6:** main's citation red was fixed by hand-back 61 (`b72aaba`); say whether your branch's checks are green on it.
- **Q1, Q3 and Q5 are the owner's** (the perf proof on this machine; away worktrees and `lane_ports.tsv`; who runs the
  integration test against a real Conduit before the merge). Build nothing for them; the conductor takes them to the
  owner.

## Checks

`npm test --workspace packages/glass-shared`; `npm test --workspace apps/workspace`; `npm run lint`; `npm run typecheck`;
`node scripts/no_react_check.mjs`; `node scripts/version_isolation_check.mjs`.

## Out of scope

A browser socket factory; the page service's use of the client (GG2e); the perf gate itself.
