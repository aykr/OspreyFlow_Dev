# Away-round drafts of 25 November 2026 (D246, the server's build account)

**Status: drafts, not ruled.** Written on the branch `drafts/2026-11-25` in `~/away-drafts`, from main at `4f77858a5`.
Nothing is pushed, merged or written outside this folder. No row is in `slices.tsv` and the decision log is unchanged.
Each draft gives what exists today (read from the code, with file and line), the questions with a proposal first, a
table of cases (each red first), checks and what is out of scope. No product code was written and no test was run.

**Second batch (the owner's correction and rows, the same day):**
- GA1 is Ask & Chat, so GA1a is rewritten and the assessments finding has its own file.
- Each question 0 is rechecked against the plan's rows the owner gave. Where a draft changed is listed below.
- GR4b and GG2b are added.

## The drafts and their open questions (the proposal for each is in the draft)

| Draft | What it proposes | Its open questions |
| --- | --- | --- |
| [AD4_DECISION_DRAFT.md](AD4_DECISION_DRAFT.md) | **A decision record** (an ADR-152 amendment): Themes settings changed by `administer_system` alone, kept in `appearance.yaml` (`600`, its own Conduit volume, the *Admin › Maps* pattern, backed up and restored), read through `GET /v1/appearance` | 0 is AD4 this (not among the rows given); 1 the right; 2 where kept, whole replacement; **3 the GOV.UK identity switch stays a deployment setting (a build argument of the workspace image, `apps/workspace/Dockerfile:59`): this contradicts decision 14's menu**; 4 the logo; 5 the wider list, and which slots "standard wording" means; 6 who reads; 7 the sign-in page (question 25); 8 the audit; 9 the override warning; 10 the first slice, AD4a |
| [ACCESS_FINDING_assessments.md](ACCESS_FINDING_assessments.md) | **A finding, read and not run, naming an access rule (the owner's)**: a gap's `linked_entities` and an assumption's `linked_judgements` are saved unchecked and listed with no visibility step (`services/api/assessments.py:360-370`, :417-427; `app.py:8770-8812`, :8817-8846), while a judgement is hidden in full (ADR-046). Two failing tests are written out, modelled on `test_assessment_routes.py:255-290` | 1 is it a fault; 2 drop the hidden links or hide in full; 3 a security part in the Conduit, tests first; 4 the write side in the same part |
| [GA1a.md](GA1a.md) (**rewritten**) | A case's **Ask & Chat**, read-only, at `/cases/{id}/ask`: each answer with its documents, engine and model, what was read, and its proposals in words (never as fact: rule 5) | 1 scope (asking is GA1b); **2 waits for GG2b: the route's visibility reads the reader's working set (`questions.py:1350-1370`)**; 3 the case's conversation only; 4 nothing about left-out answers, `unplaced` in words; 5 no accept or reject yet; **6 `ASK_MODEL` is commented "Viewer" (`rights.py:38`) but the route needs an editor**; 7 one 404; 8 scenario AC; 9 the fixture hides as the route hides |
| [GG2b.md](GG2b.md) (**new**) | The canvas's first real page: **a saved view**, `/cases/{id}/views/{view_id}`, drawn read-only by GG2a's Sigma 4 module, with paged tables of the same graph for scripts off. The only graph read over HTTP is a saved view; the live working set comes only by WebSocket, which has no scripts-off form | **1 a saved view in place of the scouts' "working set and delta client" (moved to GG2c)**; 2 the module reads through `/v1`, not a multi-megabyte JSON block; 3 a paged table at 50k; 4 the tables as the alternative until the Matrix; 5 the read-only actions of the 65; 6 the cap's options; 7 `missing`; **8 `open_case_view` names no `require_right` (the board routes add `INVESTIGATE`): confirm, or stop**; 9 merges only after WS4; 10 scenario GV. **GG2a has not run: no `away/GG2a` branch exists** |
| [GG3a.md](GG3a.md) | The case workspace's **search panel**, read-only, scripts off, at `/cases/{id}/search` | 1 search first; **2 now waits for GG2 and PL8 (changed)**; 3 a `GET` form over the `POST` route; 4 a limited result in words; 5 one search, one audit row; 6 what a result shows; 7 scenario SP; 8 the fixture |
| [GG4a.md](GG4a.md) | A case's **drawing boards**, read-only, as tables | **0 GG4 is all of R6 (changed): boards stay first, as the one row drawing nothing with Sigma; open, whether the Matrix is GG2d's or GG4's**; 1 tables first; **2 now waits for GG3 (changed); starting early is the owner's exception**; 3 the path; 4 one 404; 5 `missing`; 6 the cap; 7 drawn watches later; 8 scenario BD; 9 the fixture |
| [GG5a.md](GG5a.md) | **An extension of `slices/GG5a.md`**: questions and nine cases for the strict-policy run of MapLibre 6.19 | **0 GG5 needs GG2: proposed, the word of 21 November stands for GG5a alone (a test-only page), and GG5b waits for GG2 (added)**; **1 decision 8 already allows `img-src blob:` on map pages (proposed: still stop)**; 2 browsers; 3 where the spec lives; 4 an exact devDependency; 5 the tile fixture; 6 the `eval` branch; 7 a standing test |
| [GR1a.md](GR1a.md) | The reader's **cases** at `/cases` and one **case page** with its brief, read-only. New case is GR1b | **0 the reading holds; New case is not in the row's own words (still open, NEXT_BATCH question 7)**; 1 scope; **1b when it starts: after GG2b as the row says, or early by the owner's exception, since GG3a, GG4a and GA1a sit under its path (added)**; 2 who owns the case list, GR1 or GG2d; 3 paths; 4 a 403 shown as the 404; 5 closed tabs; 6 one read, one audit row; 7 scenario CS; 8 the fixture and the brief's attachments |
| [GR4b.md](GR4b.md) (**new**) | **Arranging the trends shown together**: "Move up" and "Move down" buttons, scripts off, posting to `PUT .../packs/{pack_id}/order` with every visible item named, as the route requires | **Waits for GR4a's merge and its questions 1 (the address: built as `/packs/trends?case=…&pack=…`) and 2 (no place for a withheld item)**; 1 the buttons; 2 a trend swaps only with the next trend; 3 working packs only; **4 the route has no expected version: the form carries the order seen and refuses a stale one**; **5 the draft read is viewer-level but the order route is editor-level**; 6 the 422 as a change; 7 the address; 8 TS16 onwards |
| [WS4a.md](WS4a.md) | Before the port, **the gates WS4 is held to, built on Sigma 3 and shown red**: the canvas-look comparison (none exists), `VERSION_WINDOW.yaml` and I20's check (neither exists), and readiness signals naming no `.sigma-*` element | **0 "needs GG2" must mean GG2a: GG2b to d wait for WS4 (decision 9), so the whole of GG2 would deadlock (added)**; **2 now after GG2a (changed)**; 3 the comparison; 4 references in CI; 5 the window file and the release check; 6 the readiness mark; 7 Sigma 4's version and the `@sigma/*` packages; 8 ADR-119 |

## Where each draft changed against the plan's rows

| Draft | The plan's row | Change |
| --- | --- | --- |
| GA1a | "Ask & Chat as server-rendered pages (R5)", stage 1, needs GG2 | **Rewritten** (it was assessments); the finding moved to its own file |
| GG3a | "Inspector, search, timeline, documents (R5)", needs GG2 and PL8 | Documents added; question 2's proposal now waits for GG2 and PL8 (it proposed starting before PL8) |
| GG4a | "Graph extras, drawing boards, Matrix, Ownership, query builder, metrics (R6)", needs GG3 | Question 0 widened to all of R6, with boards kept first and the Matrix's owner asked; question 2 now waits for GG3 (it proposed starting after GR1a) |
| GG5a | "Map and site plans on MapLibre 6 (R8)", needs GG2 | Question 0 added: GG5a before GG2 on the word of 21 November, GG5b after |
| GR1a | "Cases, case brief, saved views, history (R5)", needs GG2 | The reading holds; question 1b added (when it starts); New case marked as not in the row's words |
| WS4a | "Today's React workspace moves to Sigma 4", needs GG2 | "Needs GG2" read as GG2a, with the deadlock explained; question 2 now after GG2a (it proposed now) |
| GR4b | "A board page: saved trends together (Trends shown together)" | New; it follows GR4a's ruling 1 ("arranging is GR4b") |
| AD4 | not among the rows given | No change |
| RL2 | "Release 0.7.0: version and notes, owed live tests, release build" | No draft asked. Noted for RL2: WS4a's I20 check refuses a release while `VERSION_WINDOW.yaml` lists anything |

## Corrections to cited lines found on the way (for the orchestrator, with each draft's spec changes)

- ADR-152 decision 14 cites `packages/schemas/deployment.py:1656` and `harness/render.py:1045`. They are now
  `deployment.py:1708` and `render.py:1160` (AD4).
- ADR-152 decision 6's table gives `GlassCanvas.tsx` as 4,078 lines; it is now 4,104 (WS4a).
- `slices/GG5a.md` says "if `apps/pages` has no browser runner yet": two exist. It also puts the tile fixture directly
  under `keyboard/`; it is at `apps/workspace/keyboard/fixtures/map-tiles.pmtiles` (GG5a).
- ADR-143's status line still says "Not built", while its routes and screens are on main (GG4a).
- ADR-152 decision 5 cites `services/api/app.py:21232-21236` for the socket accepting a header. The stream route is
  now at `app.py:21995`; whether the header check has moved with it was not read (GG2b).
- `rights.py:38`'s comment on `ASK_MODEL` ("Viewer") disagrees with the ask route's editor gate (GA1a).
