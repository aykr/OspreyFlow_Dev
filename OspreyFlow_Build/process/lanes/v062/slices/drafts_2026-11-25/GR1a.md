# Slice GR1a · GR1 · The cases as GOV.UK pages, read-only: the list of the reader's cases and one case's page with its brief (a draft)

**Status: a draft, not ruled.** Written on the server's build account in an away round (D246), 25 November 2026, on the
branch `drafts/2026-11-25`. No row in `slices.tsv`; no builder starts from this paper.

**Question 0, rechecked against the plan's row (the owner, 25 November 2026, later the same day):** "**GR1: Cases,
case brief, saved views, history (R5)**", which **needs GG2**. **The reading holds**: GR1 is the `cases-and-views`
row of `FUNCTIONS.yaml`. Three things change.
1. **GR1 needs GG2**, which this draft did not say. A new question 1b says when GR1a may start.
2. **"New case" is not in the row's own words.** The plan's row names cases, the brief, saved views and history. The
   function row adds "also access, settings, datasets, domains, new case" in brackets. So GR1b (New case) stays a
   proposal, and **whether New case is GR1's or GG2's is still open** (NEXT_BATCH question 7, unruled).
3. **The case list may be GG2d's** (NEXT_BATCH question 6), and question 2 still asks this.

## What exists today (read on 25 November 2026 at `4f77858a5`; re-read, lines move)

- **The function row.** `OspreyFlow_Core/apps/pages/FUNCTIONS.yaml:203-209`: `cases-and-views`, "Cases, case brief, saved
  views, history (also access, settings, datasets, domains, new case)", in `apps/workspace/src/investigation/`,
  `views/` and `history/`, slice "R4 (list), R5" ("the plan has not yet named a build for this row"), scenarios
  "A7, B14, B21", no route. NEXT_BATCH's question 6 (not yet ruled) proposes that the plain case list be GG2d.
  **Two builds may claim one page** (question 2).
- **The React screens.** `apps/workspace/src/investigation/`:
  - the list and new case: `CaseList.tsx` (111), `NewCaseForm.tsx` (131), `CasePicker.tsx` (171), `CaseSwitcher.tsx`
    (122), `DatasetChoice.tsx` (35), `DomainChoice.tsx` (42);
  - the case: `CaseBrief.tsx` (544), `briefApi.ts` (135), `CaseDatasets.tsx` (150), `CaseDomains.tsx` (65),
    `CaseSettings.tsx` (69), `CaseAccessPanel.tsx` (152), `access.ts` (68), `caseNavigation.ts` (47).

  Saved views are in `src/views/` (`ViewsPanel.tsx`, `SaveViewForm.tsx` and others).
- **The Conduit (no change needed for reading).** In `services/api/app.py`:
  - **`GET /v1/investigations`** (`list_investigations`, :4344) has no `require_right`. It answers the cases the caller
    holds a level on (`investigations.list_for(principal)`) as `InvestigationListing` rows (:4322-4341). Each row has
    `id`, `name`, `level`, `created_at`, `created_by`, `domains`, `tab_hidden` (ADR-084, a flag per account) and
    `datasets` / `dataset_ids` (the names and ids of the datasets the case reads, from `datasets.of_case(case.id,
    principal)`, :4371). Its docstring says "Counts are not here yet".
  - **`GET /v1/investigations/{id}`** (`get_investigation`, :4708) sits behind `InvestigationViewerDep` (:2930,
    `_authorized_at(AccessLevel.VIEWER)`). Its gate (`_authorized_at`, :2851-2878) says: "**'No level at all' and
    'wrong unit' and 'no such case' are the same 404** (ADR-041's existence-leak rule); a level too low is a 403, since
    the account can already see the case exists. Either denial is audited." Reading a case writes an audit row
    (`get_investigation`, :4714).
  - **`GET /v1/investigations/{id}/brief`** (`get_case_brief_route`, :8487-8495) sits behind
    `require_right(Right.INVESTIGATE)` as well as the viewer gate. `CaseBrief` (`services/api/case_brief.py:172-178`)
    holds `priority` and `requirements`, with "**deliberately no count, no last-edited time and no stored field
    beyond these**: each is a way for a reader to notice what they may not read".
  - Writes, for later slices: `POST /v1/investigations` (:4177-4180, `Right.CREATE_CASE`, `rights.py:26`);
    `GET /v1/datasets` (:4225); `POST /v1/datasets` (:4232-4235, `CREATE_CASE`); `GET .../datasets` (:4272); views
    (:4732, :4822, whose rights were not read).
- **The new-case form's specification.** `spec/02_GLASS_FRONTEND.md` about lines 904 to 910: *What data does this case
  read?*, offering *Use an existing dataset…* (the unit's source and composite datasets as radios, named by name alone)
  or *Make a new dataset: empty, loaded in the Ingest Studio* (the default), with a name field that takes the case's
  name if left empty. The analyst layer is never offered (ADR-143 decision 1). ADR-140 R16 is at `spec/06` about line
  25177.
- **The page service.** `apps/pages/tree-govuk/routes.yaml:7` says `/` is not in the list and is the service's own
  route. `server/app.ts:414` is `app.get("/")`, which redirects to sign-in with no session (:416-417). The owner's
  ruling of 24 November (`RULINGS.md` line 57, item 5): "**no new Home path, the tree switch decides which tree serves
  `/`**". Pages built so far: `pageList.ts:13-20`. No `/cases` route exists.
- **The scenarios** A7 (`spec/08` about line 388, filtering reports), B14 (about 565, opening an alert at its address)
  and B21 (about 572, the pathfinder) are rows of the journeys. **None is about the case list or the case page**, so a
  scenario is the first item (the owner's rule).

## Questions for the owner (the proposal first)

1. **The first slice's scope.** (a) **Read-only:** the reader's cases at `/cases`, as a table (the case's name as a
   link, its level, its domains, the datasets it reads, who made it and when), and one case's page at
   `/cases/{case_id}` (the same facts and the brief's priority and requirements, read-only). **New case is GR1b**: a
   form, scripts off, with the anti-forgery token, posting to `POST /v1/investigations` and redirecting to the new
   case's page. (b) The list and New case in one slice, which brings the dataset choice of `spec/02` (and
   `POST /v1/datasets`) into the first slice.
1b. **When GR1a may start (new, after the plan's row was given).** (a) **After GG2's first page with a working set
   (GG2b), as the plan's row says**, so that a case's page can link to its workspace from the start and GR1a's paths
   are the ones GG2b's page sits under. (b) An exception to the plan's needs, for the owner alone to give: start now.
   GR1a reads only `GET /v1/investigations`, the case and its brief, none of which needs a working set or Sigma. GG4a,
   GA1a and GG3a each sit under GR1a's case path, so an early GR1a would let their paths be fixed early.
2. **Who owns the case list.** (a) **GR1**, the GOV.UK tree's page. GG2d's "plain case list" (NEXT_BATCH question 6)
   is then the case list inside the graph workspace, if it is anything at all, and the row's slice reads "GR1a" for the
   list and the case page. (b) GG2d, with GR1 holding only New case, the brief and settings.
3. **The path, and Home.** (a) **`/cases` and `/cases/{case_id}`.** `/` stays the service's own route (the owner's
   ruling of 24 November); whether a signed-in GOV.UK reader landing at `/` is sent to `/cases` is the Home row's (R1,
   R7), not GR1a's. (b) `/` as the case list.
4. **Who sees what.** (a) **Exactly what the Conduit sends.** The list is the route's (cases the reader holds a level
   on); the page filters nothing (decision 5) and shows no count, since the route sends none. A case the reader holds
   no level on, one in another unit and one that does not exist are the same GOV.UK 404 page, words and status, as any
   page that does not exist. A reader whose level is too low, or who lacks `INVESTIGATE` for the brief, also gets the
   same 404 page (the owner's no-oracle rule, as for the report route), even though the route answers 403 because it
   already lets them know the case exists. (b) The 403 shown as "You do not have access to this part of the case", true
   to the route, since the existence is already known.
5. **Closed tabs (`tab_hidden`).** (a) **Listed like any case, with the words "You closed this case's tab" after its
   name.** The flag is the reader's own. (b) Left out of the list, which would hide a case from its own reader.
6. **The audit of reading a case.** (a) **Nothing to do:** the route audits each read (:4714), and the page reads once
   per render. A test pins that the page makes exactly one `GET /v1/investigations/{id}` per render, so the audit is
   not doubled. (b) No test.
7. **The scenario.** (a) **A new `spec/08` scenario, CS, written first and red first, from these rulings.** Its id goes
   in `cases-and-views` for these two pages only, with the row's route left empty until the row is whole (as AD3a did
   for `admin`). (b) Your words.
8. **The fixture.** (a) **The strict reader and the field census, as ruled for GR3a**: every field of
   `InvestigationListing`, `Investigation` and `CaseBrief` is drawn or named in the scenario as left out (`dataset_ids`
   is used only for links). A requirement (`BriefRequirement`, `case_brief.py:164-169`) carries `id`, `text`,
   `status`, `answered_at` and `attachments` (each a kind and an id). **Proposed: each attachment is shown as its kind
   alone ("a document", "a saved view") until a GOV.UK page exists to link it to.** The builder reads whether the route
   already drops an attachment the reader may not open; if it does not, that is a stop (rule 3), not a filter in the
   page. Answers come from the real routes when GR3b lands, and the fixture refuses as the real gate
   refuses: 404 for no level, 403 for a level too low (rule 15).

## The table of cases (each red first; planted faults at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | A reader with three cases at different levels | `/cases`: a table of the three, in the route's order, each name a link to its page, with level, domains, datasets and who made it when | a case of another unit added by the page from a second read |
| 2 | A reader with no cases | a sentence saying so and nothing else; never an empty table | headings with no rows |
| 3 | A case whose tab the reader closed | listed, with "You closed this case's tab" | the row left out |
| 4 | `/cases/{id}` for a case the reader holds a level on | the case's name, level, domains and datasets, and the brief's priority and requirements in the route's order | a requirement's status drawn as anything but the route's words |
| 5 | A case with an empty brief | "This case has no brief yet" | an empty list |
| 6 | No level, another unit, no such case | the same 404 page, words and status, for all three | a "you do not have access" sentence for the first two |
| 7 | A level too low, or no `INVESTIGATE` for the brief (the route answers 403) | the same 404 page (question 4 (a)) | the route's 403 passed through as its own words |
| 8 | One render of a case page | exactly one `GET /v1/investigations/{id}` (one audit row at the Conduit) | the page reading the case twice (for the title and the body) |
| 9 | The Conduit gives no answer, or 401 | the 502 "could not be read" page; an ended session says to sign in again (AD3a's AP4) | an empty table |
| 10 | A body missing a field the generated types require | "could not be read", never a zero or an empty list | each required field removed in turn (one case per field, from the type's own field list) |
| 11 | Keyboard | each link reachable and working, one case per page in the GOV.UK keyboard folder (rule 13) | a link out of the tab order |
| 12 | Scripts off | both pages whole, with no control that needs a script | none: they hold no script; the spec proves it |

## Checks (frozen when cut)

GR3a's list, adapted: `npm test --workspace apps/pages`, lint, typecheck, `no_react_check.mjs`; the new scenario's test
and the pages' tests; `test_functions_yaml.py`, `test_tree_parity.py`, `test_no_react_check.py`,
`test_pages_foundation.py`, `test_design_gates_reach.py`; `test_ui_words_check.py`, `test_copy_says_no_client.py`,
`test_doc_citations_check.py`; **`tests/harness/test_pages_setting.py`** (the route list: `/cases` and its pattern added
with their words); `ruff check .`; `make -C OspreyFlow_Build design-check`; the cheap checks of 20 November.

## Out of scope

New case (GR1b); the case's settings, access, datasets and domains changes (later GR1 slices); saved views and history
(later, or GG2's); the graph workspace (GG2, GG3); `/` and Home (R1, R7); any Conduit change; `apps/workspace`; the
Default tree's twin.
