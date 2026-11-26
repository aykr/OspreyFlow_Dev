# Slice GR1c · GR1 · A page may own a path with named parts (`/cases/{case_id}`), and one function row may have several pages in a tree; GR1a's and GG4a's pages moved to them (a draft, needed only if the owner answers GR1a's question 1 with (b))

**Status: a draft, not ruled.** Written on the server's build account in an away round (D246), 26 November 2026, on the
branch `drafts/2026-11-26`. No row in `slices.tsv`; no builder starts from this paper. **This slice exists only if the
owner answers GR1a's question 1 with (b).** With (a), every case page keeps the query form (`/cases?case=…`,
`/cases/boards?case=…&board=…`), and this paper is withdrawn.

**Where it comes from.** GR1a's away report (`away/GR1a`, `OspreyFlow_Build/process/lanes/v062/away/GR1a_AWAY_REPORT.md`,
question 1): the owner ruled `/cases` and `/cases/{case_id}`, and two rules of the page registry stood in the way, so
GR1a built `/cases?case=<id>` "as you kept `/packs/trends?case=…&pack=…` for GR4a". GG4a followed with
`/cases/boards?case=…&board=…` (its question 7). **Every later case page names an address** (GG3a to GG3e, GG4c to GG4f,
GA1a to GA1e, GR1b to GR1f, GG2b and GG2e): about twenty slices. Ruling this once, early, saves moving each page later.

## What exists today (read on `origin/main` at `042c882f2`; re-read, lines move)

- **The registry** (`OspreyFlow_Core/apps/pages/server/pages.ts`). Its header (:1-18) calls itself "the route-module
  convention (ADR-152 decision 6)": "`path` is a plain path (no pattern) … and claimed by no other page", and "`id` is the
  page's row in `FUNCTIONS.yaml`". `PLAIN_PATH` (:55) is lower-case segments only, and the reason given (:49-54) is that
  Express folds case and a trailing slash, so two spellings could claim one route. `checkTree` (:106-145) refuses a path
  that is not plain (:116-120), **an id used by more than one page in a tree** (:133-136) and a path claimed twice
  (:137-142). Pages are registered behind the session and the anti-forgery check (:168-177).
- **What the decision record says.** ADR-152 decision 6 (`spec/06_DECISIONS.md` about lines 41024 to 41071) lays out
  folders and what is kept once; **it says nothing about plain paths or one page per row.** Amendment 1 decision 1
  (about 41809 to 41821): "A row has its page when its route is in `tree-govuk`'s route list." **So the plain-path rule
  is the code's, and the one-page-per-row rule is the code's reading of Amendment 1.**
- **The route list and its readers.** `tree-govuk/routes.yaml` lists `/help`, `/admin/people`, `/reports` (:8-11), and
  GR1a and GG4a add `/cases` and `/cases/boards` on their branches. `scripts/tree_parity.py` reads it (:10, :59);
  `harness/pages_service.py`'s `route_paths` sends each listed path **and everything under it** to `pages` (:85-104,
  `caddy_matcher` :107-112: `{path} {path}/*`). `OspreyFlow_Build/tests/harness/test_pages_setting.py` pins the exact set
  (about line 2348). I2 (`spec/06` about 41224) runs "each route in the tree's route list"; I4 (about 41226) names no list, but its spec
  (`scripts-off/every-page.spec.ts`) would walk the same one.
- **The workspace's own case addresses** do not use `/cases`: `caseUrl` is `/?investigation=<id>&from=case`
  (`packages/glass-shared/src/investigation/cases.ts:251-258`), so `/cases/*` going to `pages` takes nothing from it.
- **What GG4a found about a decoded slash.** "A slash in case or board asks nothing (the Conduit decodes %2F into another
  route)" (GG4a's review fixes, `away/GG4a` commit `3559dd0ed`). The forwarder refuses `%2f`, `%5c` and `%2e` in a
  `/v1` path (`server/forward.ts:156-170`), but a page's own handler builds its Conduit path from the address.

## Acceptance (red before, green after)

`apps/pages/test/server/pages.test.ts`'s new cases (a named part admitted; the refusals of questions 3 and 4; two pages
on one row), each red against today's `pages.ts`; GR1a's CS and GG4a's BD scenarios green **at the new addresses**, with
the old query addresses answering as question 6 says.

## Questions for the owner (the proposal first)

0. **GR1a's question 1 itself.** (a) **(b): amend, so a page may own `/cases/{case_id}`**, since about twenty pages will
   sit under a case and a path reads as what it is. (b) (a): keep the query form; this slice is withdrawn.
1. **Is it an amendment?** (a) **Yes, a short ADR-152 amendment, written as a diff file**: decision 6's route-module
   convention (the code cites it) gains named parts, and Amendment 1's "a row has its page when its route is in the route
   list" is read as "when its first page's route is", several pages naming one row. (b) No: the rule is the code's, and
   `spec/02`'s page-service section records it.
2. **The form of a named part.** (a) **`{name}`, a whole segment, lower case with underscores** (`/cases/{case_id}/boards/{board_id}`),
   turned into Express's `:name` by the registry, never written in Express's form by a page; the first segment is
   always plain (so the front proxy's prefix matcher still works: `route_paths` sends `/cases` and `/cases/*`). (b)
   Express's form directly.
3. **What a part's value may be.** (a) **The registry refuses, before the handler runs, a value that is empty, holds a
   `/`, `\` or `%` after decoding, is a dot segment, or is longer than 128 characters, with the same 404 page as a
   missing page**, so no handler can build a Conduit path from a decoded slash (GG4a's finding, made a rule for all).
   (b) Each handler checks its own.
4. **Two pages whose paths could match one address** (`/cases/{case_id}` and `/cases/new`). (a) **A plain segment wins
   over a part, and the registry refuses two pages whose paths match exactly the same addresses**, in words, at start.
   (b) Order of registration. Not proposed: a silent winner.
5. **Several pages on one row.** (a) **A page gains `row` (its `FUNCTIONS.yaml` row, by default its `id`), and `id`
   becomes the page's own name, unique in the tree**; the row's `route` in `FUNCTIONS.yaml` is its first page's path;
   the route list lists every page's path, parts included; `tree_parity.py` counts a row as having its page when its
   `route` is listed. (b) Keep one page per row, and put each extra page's path in a sub-path of its row's page handled
   by one handler.
6. **The old query addresses** (from GR1a and GG4a, if merged first). (a) **A `303` from `/cases?case=X` to
   `/cases/X`, and from `/cases/boards?case=X&board=Y` to `/cases/X/boards/Y`, for one release, then removed** (a line
   in RL2's notes); nothing outside the product links to them yet. (b) Drop them at once.
7. **I2 and I4 over a pattern.** (a) **Each pattern in the route list names, in the test's own table, the synthetic id
   its page is opened with**, and a pattern with no entry fails the spec in words. (b) Skip patterns in I2 and I4.
   **Not proposed:** a page that escapes the policy test.
8. **Order.** (a) **GR1c merges before any new case page**; a page slice already written in the query form moves in its
   own next round. (b) After the pages, moving them all at once.

## The table of cases (each red first; the planted fault at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | A page at `/cases/{case_id}` | registered; `/cases/c-1` reaches its handler with `case_id` = `c-1` | today's `PLAIN_PATH` (red as it stands) |
| 2 | `/Cases/c-1`, `/cases/c-1/` | not that page (404) | the case folding of Express left on |
| 3 | `/cases/a%2Fb`, `/cases/..`, `/cases/%5C`, an empty part, a part of 129 characters | the 404 page; the handler never runs | the value check moved into one handler and left out of another |
| 4 | A part's name in Express's form (`:case_id`) or upper case | refused at start, in words | the form accepted |
| 5 | `/cases/{case_id}` beside `/cases/new` | both registered; `/cases/new` reaches the plain page | registration order deciding it |
| 6 | Two pages `/cases/{a}` and `/cases/{b}` | refused at start, in words | the second registered silently |
| 7 | A pattern whose first segment is a part (`/{x}`) | refused at start (the proxy matcher needs a plain first segment) | admitted |
| 8 | Two pages naming the row `cases-and-views` | both registered; the row's route is the first page's path; parity unchanged | the old one-id rule (red as it stands) |
| 9 | `route_paths` and `caddy_matcher` under the GOV.UK brand | `/cases` and `/cases/*` once, never a `{` in the proxy's file | the pattern written into the matcher |
| 10 | I2 and I4 over the route list | each pattern opened with its table's id; a pattern without one fails in words | the pattern skipped |
| 11 | `/cases?case=c-1` (question 6 (a)) | `303` to `/cases/c-1` | a `200` on the old address |
| 12 | GR1a's CS and GG4a's BD at the new addresses | green, every link on the pages the new form | a link still in the query form (a test that walks every `href`) |
| 13 | A part value used to build a Conduit path | built with the page service's own `v1()` (`server/conduit.ts:41-42`, `encodeURIComponent`) **after** question 3's check has refused a decoded `/`, `\` or `%`; encoding alone is not the guard, since a `%2F` it writes is decoded by the Conduit's server into another route (GG4a's finding) | question 3's check removed: a value `a/b` reaches a handler and the Conduit answers another route |

## Files touched

`OspreyFlow_Core/apps/pages/server/pages.ts`; `server/pageList.ts`; `server/cases.ts` and `server/boards.ts` (on their
branches, or after their merge); `tree-govuk/routes.yaml`; `tree-govuk/cases.njk`, `boards.njk` (links);
`scripts/tree_parity.py`; `harness/pages_service.py` (`route_paths`, only if a pattern can reach it);
`apps/pages/test/server/pages.test.ts`, the GOV.UK CSP and scripts-off specs' route tables, `cases.test.ts`,
`boards.test.ts`; `OspreyFlow_Build/tests/glass_trees/test_tree_parity.py`, `test_functions_yaml.py`,
`tests/harness/test_pages_setting.py`; `spec/02` (the page service's address rule) and **the diff file** for ADR-152 if
question 1 (a).

## Checks (frozen when cut)

`npm test --workspace apps/pages`, lint, typecheck; `test_tree_parity.py`, `test_functions_yaml.py`,
`test_pages_setting.py`, `test_pages_foundation.py`; the GOV.UK keyboard, scripts-off and CSP specs; `ruff check .`;
`test_doc_citations_check.py`; the cheap checks of 20 November. **A harness file is touched, so the render tests run in
full** (`test_pages_setting.py` over every shape and brand).

## Out of scope

Any new page; the Default tree's twins; Home and `/` (the owner's ruling of 24 November: "no new Home path").
