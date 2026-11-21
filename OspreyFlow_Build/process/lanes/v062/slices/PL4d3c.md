# Slice PL4d3c · PL4 · The remaining plain Conduit clients move to `packages/glass-shared`, and the stray `export/api.ts.bak` is deleted in its own commit (slice D3c; no behaviour changes)

- **Build id:** PL4 (ADR-152 R2, decision 6). D3 is cut four ways (D3a merged: reports, export, alerts, patterns; D3b merged: link, inspector, question, reader, views, promotions, analytics; **D3c (this slice): the other plain clients**; D3d: the files that need a split first, and the `help/roles.ts` / `admin/api.ts` question). Nothing the ADR names is dropped.
- **Dial setting:** balanced
- **Rounds limit:** 4
- **After:** PL4d3b merged. **This is the same job as PL4d3a and PL4d3b: read `OspreyFlow_Build/process/lanes/v062/slices/PL4d3a.md` first and do its "What (in this order)" items 1 to 5 (the word-walkers read the package too, keyed by root; the image COPY lines; the old-path test; the gates' reach), its proof of no change ((a) `dist_compare` SAME, (b) Playwright `--list` before and after, (c) reach not lower, (d) COPY lines), its acceptance-test shape, its checks and cheap checks.** It merges without waiting for GitHub if `dist_compare` says SAME.
- **Status of this brief:** written by the conductor on 21 November 2026 (night) from the D3 scout (read, not measured). **While PL4 runs nothing else touches `apps/workspace`.**

## What moves (re-read every file; destination `packages/glass-shared/src/`, folder shape kept)

| File (under `OspreyFlow_Core/apps/workspace/src/`) | Lines | fetch | Note |
|---|---|---|---|
| `assessment/api.ts` | 180 | 7 | 5 importers. |
| `boards/boardsApi.ts` | 252 | 2 | 3 importers (`boards/promotionsApi` moved in D3b). |
| `connections/connectionsApi.ts` | 118 | 3 | 3 importers. |
| `explore/exploreApi.ts` | 193 | 3 | 2 importers. |
| `map/providers.ts` | 37 | 1 | 1 importer (a Playwright spec intercepts `/v1/map/providers` by URL, not by import). |
| `metrics/api.ts` | 42 | 1 | 2 importers. |
| `ownership/api.ts` | 47 | 1 | type import of `../alerts/api` (moved by D3a: import from the package). |
| `search/addFromListApi.ts` | 158 | 1 | |
| `site/api.ts`, `site/bilinear.ts` | 156, 128 | 5, 0 | `api.ts` imports `./bilinear` (plain). |
| `strength/api.ts` | 106 | 1 | 5 importers. |
| `watches/api.ts` | 139 | 7 | 3 importers. |

Total about 12 files, 1,556 lines, about 27 importer references. **A file that cannot move whole: stop at that file, leave it, say so.** The package never imports from the workspace.

## The stray file (the owner's addition 3, in its own commit)

`OspreyFlow_Core/apps/workspace/src/export/api.ts.bak`: the scout found it is a copy of `export/api.ts` before D3a moved the live file, differing at one line (`withheld: boolean | null` against `withheld?: boolean | null`), imported by nothing, named by no test, gate, Dockerfile, scan map or allowlist, and holding no key, token, address or client name. **Before deleting it, confirm all of that yourself** (`git ls-files` shows it tracked; grep the whole repository for the name, including `OspreyFlow_Build`; read the file for any key, token, address or client name; say what it was). **If anything imports or reads it, or it holds any of those things, do not delete it: stop and say so.** Delete it in a commit of its own (message: `chore(workspace): delete the stray export/api.ts.bak (a copy of the pre-move export client)`); no other file in that commit.

## Acceptance test

`OspreyFlow_Build/tests/glass_trees/test_glass_shared_plain_clients.py` (new, pure, red first on main), built like `test_glass_shared_link_clients.py` (read it): the moved files exist under the package, are exported, not under their old paths; no old path anywhere outside the decision log and records; every import in a spec or harness file resolves; the move changed no line but the imports (**compare both sides at the rename commit, never the working tree**); the package's copies import no React and no workspace path; each word-walker reads the moved files (a plant, red then green, keyed by root); **the stray file does not exist in the tree** (red on main, where it does). **Say which folders it walks.**

## Which stage 4 builds this unblocks (say it in your report, confirmed by the code)

The scout: these clients serve screens outside the Studio and the reports (assessment, boards, connections, explore, watches, strength, site); name which stage 4 pages (from `STAGE4_SCOUTS_2026-11-20.md` and `RULINGS.md`) call which of them, or say none is planned yet.

## Out of scope

D3d; the two sign-in files; `admin/api.ts`, `help/roles.ts`; components, hooks and React; `color/nodeVisual.ts`, canvas files, `ontology/schema.ts` and structural types (E); `apps/pages/Dockerfile` (PL7); the rules files; the protected files; the budget numbers.
