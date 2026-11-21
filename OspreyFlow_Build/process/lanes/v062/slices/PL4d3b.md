# Slice PL4d3b · PL4 · The link, inspector, question, reader, views and analytics Conduit clients move to `packages/glass-shared` (slice D3b; no behaviour changes)

- **Build id:** PL4 (ADR-152 R2, decision 6). **D3 is cut four ways on the scout's finding:** D3a (merged: reports, export, alerts, patterns), **D3b (this slice): the link, inspector, question, reader, views, boards-promotions and analytics clients**, D3c: the other plain clients (assessment, boards, connections, explore, map providers, metrics, ownership, search, site, strength, watches), D3d: the files that need a split first (`investigation/cases.ts`, `home/guides.ts`, `home/homeData.ts`, `canvas/entityPictures.ts`, `ingest/runs/ExternalOrchestration.tsx`), the `help/roles.ts`, `shell/placesByRole.json` and `admin/api.ts` question, and the stray `export/api.ts.bak`. Nothing the ADR names is dropped.
- **Dial setting:** balanced
- **Rounds limit:** 4
- **After:** PL4d3a merged. **This slice is the same job as PL4d3a: read `OspreyFlow_Build/process/lanes/v062/slices/PL4d3a.md` first and do its "What (in this order)" items 1 to 5 (including the traps closed before the verifier looks: every word-walker reads the package too, keyed by root; the image COPY lines; the old-path test), its proof of no change ((a) `dist_compare` SAME, (b) the Playwright `--list` collection check before and after, (c) reach not lower, (d) COPY lines), its acceptance-test shape, its checks and its "before your final report" cheap checks. Read `PL4d2.md` and `PL4d1.md` too.** It merges without waiting for GitHub if `dist_compare` says SAME.
- **Status of this brief:** written by the conductor on 21 November 2026 (night) from the D3 scout (read, not measured). **While PL4 runs nothing else touches `apps/workspace`.**

## What moves (re-read every file; destination `packages/glass-shared/src/`, folder shape kept)

| File (under `OspreyFlow_Core/apps/workspace/src/`) | Lines | fetch | Note |
|---|---|---|---|
| `inspector/emailDocuments.ts` | 67 | 1 | the `window` at about line 32 is a parameter, not the DOM (check). |
| `inspector/linkChangeApi.ts` | 144 | 1 | 5 importers (a keyboard harness imports its type). |
| `inspector/linkEventsApi.ts` | 197 | 2 | imports `../models/modelDeadline` (moved by D3a: import it from the package); 8 importers. |
| `inspector/linkNotesApi.ts` | 105 | 4 | |
| `linktypes/http.ts`, `linktypes/linkTypesApi.ts`, `linktypes/modelProposalsApi.ts` | 50, 155, 55 | 1, 0, 0 | `http.ts` is the shared helper; 2, 6 and 1 importers. |
| `questions/questionsApi.ts` | 193 | 1 | type import of `../inspector/linkEventsApi` (moves with it); 2 importers. |
| `reader/readerApi.ts` | 179 | 4 | imports `../dossier/models`, `modelDeadline`; 4 importers. |
| `dossier/api.ts`, `dossier/models.ts` | 21, 21 | 1, 0 | |
| `views/viewsApi.ts` | 151 | 1 | 10 importers; keyboard harnesses import it. |
| `workingset/batchExpansionApi.ts` | 157 | 2 | type import of `../views/viewsApi` (moves with it); 2 importers; keyboard harnesses import its type. |
| `boards/promotionsApi.ts` | 72 | 1 | 6 importers (the Studio Runs grid's clients reach it). |
| `analytics/api.ts` | 115 | 2 | 8 importers; imports the generated schemas by a relative path (resolve as D2 did). |

Total about 15 files, 1,680 lines, about 58 importer references. **A file that cannot move whole (React, the DOM, a workspace import you cannot resolve): stop at that file, leave it, say so.** The package never imports from the workspace. Anything else in these folders (components, hooks) stays.

## Acceptance test

`OspreyFlow_Build/tests/glass_trees/test_glass_shared_link_clients.py` (new, pure, red first on main), built like `test_glass_shared_report_clients.py` (read it): the moved files exist under the package, are exported, not under their old paths; no old path anywhere outside the decision log and records; every import in a spec or harness file resolves; the move changed no line but the imports (**compare both sides at the rename commit, never the working tree**); the package's copies import no React and no workspace path; each word-walker reads the moved files (a plant in a moved client, red then green, keyed by root). **Say which folders it walks.**

## Which stage 4 builds this unblocks (say it in your report, confirmed by the code)

The scout's reading: **IS2's Model step** (the proposals block calls `linktypes/modelProposalsApi` and `http`, and "define a type" calls `linkTypesApi`: all in this slice); **IS5's Runs grid** (`boards/promotionsApi`, in this slice); **GR3/GR4's trends** (`analytics/api`, in this slice). Confirm or correct from the React screens, and name any client such a page calls that is in neither the package nor D3c/D3d.

## Out of scope

D3c and D3d; the two sign-in files; `admin/api.ts`, `help/roles.ts`; components, hooks and React; `color/nodeVisual.ts`, canvas files, `ontology/schema.ts` and structural types (E); `apps/pages/Dockerfile` (PL7); the rules files; the protected files; the budget numbers.
