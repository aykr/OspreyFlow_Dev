# Slice GR1f1 · GR1 · A case's settings and access as a GOV.UK page, read-only: what it reads, its domain models, and who can open it (a draft)

**Status: a draft, not ruled.** Written in an away drafting session (D246), 26 to 27 November 2026, on the branch
`drafts/2026-11-27`, read from `origin/main` at `7f4f9554a`. No row in `slices.tsv`; no builder starts from this paper.
**Size S to M** (about 11 cases). The first of GR1f's three parts: **GR1f1 the reads**, GR1f2 the access changes, GR1f3
the datasets, the name and removing the case.

**Where it comes from.** The chain plan's row GR1f ("a case's settings, access, datasets and domains: the reads first,
then each change as a form"); `FUNCTIONS.yaml`'s row `cases-and-views`, whose name already says "also access, settings,
datasets, domains, new case" (`OspreyFlow_Core/apps/pages/FUNCTIONS.yaml:205-211`). ADR-052 §4, §5 and §7 (`spec/06`
about lines 7242 to 7258): an Author manages access, a unit-wide level is none, Viewer or Editor, and "a Viewer or
Editor sees only their own level". ADR-099 (a case reads exactly one dataset, Amendment 12). ADR-126 Amendment 2 (a
case's domain models come from its dataset's model). The React workspace's Cases drawer: "Who can open this case"
(`apps/workspace/src/investigation/CaseAccessPanel.tsx`, 152 lines) and the settings, "Data this case reads" and
"Domain models" (`CaseSettings.tsx`, `CaseDatasets.tsx`, `CaseDomains.tsx`).

## What exists today (read on `origin/main` at `7f4f9554a`; re-read, lines move)

- **GR1a is merged** (`5614900f8`). Its page is `/cases` and `/cases?case=<id>` (`apps/pages/server/cases.ts:1-27`),
  GET only (:116), the case read first, then its brief, then the listing (:94-110). It already shows the case's
  **domains** and its **datasets by name** from `InvestigationListing` (`server/views/casesWords.ts` `CENSUS`,
  :56-62), and leaves out `created_by` and `dataset_ids`.
- **The reads this part adds** (`services/api/app.py`):
  - `GET /v1/investigations/{id}/access` (`get_investigation_access`, :4573-4592): `require_right(SHARE_CASE)` and the
    **Viewer** gate. It answers `AccessView` (:4561-4570): `your_level`; and **only to an Author** `unit_level`,
    `grants` (account id to level) and `names` (display names for those ids, ADR-106; "an account with no name to give
    is absent"). A reader without `share_case` gets the right's **403**. **It writes no audit row** (no
    `audit.record` in the handler).
  - `GET /v1/investigations/{id}/datasets` (`case_datasets_route`, :4324-4329): the Viewer gate, no right; "none to a
    caller holding no right" (ADR-099 Amendment 11, `services/api/datasets.py:176-179`, :574-576). Each `Dataset`
    (`datasets.py:91-110`) carries `id`, `name`, `owning_unit`, `created_at`, `created_by`, `egress`, `kind`
    (`source`, `composite`, `analyst_layer`, `drawn`, :80-86), `members`, `layer_of`, `highest_marking` and
    `promotion_policy`. The case's analyst layer is not sent (`CaseDatasets.tsx:1-3`). **No audit row either.**
  - `GET .../access/history` (:4750-4757): the Author, or the administrator's safety net. `AccessHistoryEntry`
    (`services/api/investigations.py:141-146`) is `changed_at`, `changed_by`, `action`, `subject`, `level`: account
    ids, **with no names**. **Nothing in the React workspace reads it** (no caller under `apps/workspace/src`).
- **The domain models are read-only on a case.** `PATCH /v1/investigations/{id}` refuses any `domains` with 409
  `packs_from_the_model` (`app.py:4489-4499`): "change them on the Ingest Studio's Model tab". The React sentence is
  `FROM_THE_DATASET` (`apps/workspace/src/investigation/CaseDomains.tsx:19-20`), in the workspace, not in
  `glass-shared`.
- **The words already shared.** `datasetLabel` and `datasetChoiceLabel` (`packages/glass-shared/src/investigation/cases.ts:261-272`);
  `LEVEL_WORDS`, `domainLabels` (imported by `casesWords.ts`). The React access panel's words are in the workspace
  (`apps/workspace/src/investigation/access.ts:64-68` `LEVEL_NAMES`; `CaseAccessPanel.tsx:61-122`).
- **What is offered and to whom** in React: `canChangeCase` is the Author holding `share_case`
  (`apps/workspace/src/rights/visibility.ts:83-90`); the access panel is not shown on a 403 (`access.ts:20-25`).
- **On the away branches.** `away/GR1d` (built, not merged) adds a case's saved views to the same page, reading the
  case, the brief, the listing, the views and `GET /v1/me`, and sets the page's first write pattern (a `POST` to
  `/cases` with `_csrf`, then a `303`), with its asking page in the query (`&delete=<view>`)
  (`away/GR1d:OspreyFlow_Build/process/lanes/v062/away/GR1d_AWAY_REPORT.md`). GR1b (cut, not built) puts New case at
  `/cases?new=1`.

## Acceptance (red before, green after)

Scenario CS's settings rows, appended after GR1b's and GR1d's and numbered when cut, written first;
`apps/pages/test/govuk/case-settings.test.ts`, red on main, green after; GR1a's CS1 to CS15 (and GR1b's and GR1d's rows,
whichever have merged) unchanged and green.

## Questions for the owner (the proposal first)

1. **Where it sits.** (a) **A settings page of the case's own row, in the query: `/cases?case=<id>&settings=1`**, linked
   from the case's page ("Settings and access"), as GR1b's `?new=1` and GR1d's `&delete=<view>`. The case's page keeps
   its reads as they are (no extra read on every case render). (b) A part of the case's page itself: two more reads on
   every render, one of them a 403 for most readers. (c) A row and page of its own (`/cases/settings?case=<id>`), as
   GR4a's board page has: a `FUNCTIONS.yaml` row split from `cases-and-views`.
2. **What it reads, in order.** (a) **The case (its gate, first), then the listing (for the reader's level, as GR1a),
   then `.../datasets`, then `.../access`**, each once. (b) The access read first: not proposed, since the case's own
   gate must decide before anything else is asked (GR1a's order).
3. **A reader without `share_case`** (the access read's 403). (a) **The access part says only "Your level: Viewer"
   from the listing, and nothing about who else can open the case**, and the 403 is never shown as a failure (as the
   React panel, `access.ts:20-25`). (b) The whole page as GR1a's 404: wrong, since the reader may see the case.
4. **The datasets' words.** (a) **Each by `datasetLabel`, its name then its id (whole if twelve characters or fewer,
   else its last five), as ADR-099 Amendment 6 point 4 says the Glass shows a dataset "in the Cases drawer"
   (`spec/06_DECISIONS.md:10569`)**, and a composite also said as "a composite of 3 datasets"; `egress`,
   `highest_marking`, `promotion_policy`, `owning_unit` and `created_by` left out (the Admin area's, and "who made it" is
   left out for 0.7.0). An empty answer is "None shown", GR1a's words (the route sends none to a reader with no right).
   (b) The name alone, as GR1a's case page leaves `dataset_ids` out: a departure from Amendment 6, so the owner's.
5. **The domain models.** (a) **The case's domains as GR1a draws them, and `FROM_THE_DATASET` beside them**, the
   sentence moved to `glass-shared` with the React panel importing it (I11), so the page never offers a change the
   route always refuses. (b) The sentence written again in the page's words: a second copy.
6. **The grants an Author is sent.** (a) **A table: each grantee by its display name when `names` holds one, and by its
   account id otherwise** (the React panel's rule, `CaseAccessPanel.tsx:72-84`), its level in the Help page's words,
   in the order the Conduit sent them; a `team:<id>` grantee said as "Team" and its id; the unit-wide level as one
   line ("Everyone in your unit: Viewer", or "No one else in your unit"). This is not "who made it": the grantees are
   what the part is for. (b) Ids only.
7. **The access history.** (a) **Left out of 0.7.0**: the React workspace does not show it, and its entries are account
   ids with no names (`changed_by`, `subject`), the same family as the "who made it" ruling. A later part shows it when
   the Conduit names them (an amendment, beside the `display_names` backlog part). (b) Shown now with ids.
8. **No audit row on the two reads** (`.../access`, `.../datasets`) **(owner: security, the audit of a read of who can
   open a case).** (a) **Noted for the conductor, not changed here**:
   the case's own read (first) is audited, and a Conduit change is an amendment (decision 11). (b) An amendment that
   audits both, cut before this part.

## The table of cases (each red first; the planted fault at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | An Author with `share_case`, a case with three grants (one with a name, one without, one `team:analysts`) and the unit-wide level Viewer (synthetic accounts) | the grants table in the route's order, the named one by name, the unnamed by its id, the team said as a team; "Everyone in your unit: Viewer" | the grants sorted by the page; `names` ignored |
| 2 | An Editor holding `share_case`, after an Author's render of the same case in the same service | "Your level: Editor" and nothing about anyone else (the fixture sends `grants: null`, as the route does, `app.py:4583-4585`) | the server half keeping the last access answer per case and drawing the Author's grants for the Editor; the access read sent with the Author's bearer |
| 3 | A Viewer without `share_case` (the 403) | "Your level: Viewer" from the listing; no failure, no access table | the 403 drawn as "could not be read" |
| 4 | A case reading a composite of three datasets (a ULID id) | `datasetLabel`'s name and the id's last five, and "a composite of 3 datasets" | the name alone; the whole ULID printed |
| 5 | A reader holding no right (the datasets route sends none) | "None shown", never "This case reads no dataset" | an empty list said as none |
| 6 | The domain models | GR1a's labels and the `FROM_THE_DATASET` sentence, no form, no button | a change offered |
| 7 | No level, another unit, no case | GR1a's 404 page, and only the case is asked (no listing, datasets or access read) | the access read made before the case's gate |
| 8 | One render | exactly four reads, in the order of question 2, each once (GR1f2 adds `GET /v1/me/rights` as a fifth, once, for its forms; this case is widened then) | a second listing read |
| 9 | A body missing a field `AccessView` or `Dataset` requires (each in turn), or a level not in `AccessLevel` | "could not be read" (502), no part of a table (the strict reader) | a missing `grants` read as no grants |
| 10 | The census | `CENSUS` gains `AccessView` and `Dataset`, drawn and left out, and the scenario test holds both to the models' own fields | a field of `Dataset` neither drawn nor named as left out |
| 11 | Keyboard and scripts off | the page whole, its link from the case's page reachable (rule 13, I4) | the link out of the tab order |

## Waits on

GR1a (merged, `5614900f8`); GR1d merged (`away/GR1d`, the page's first write pattern and its reads); GR1b merged
(the same `cases.ts`, `casesWords.ts` and specs: the Cases lane runs one after another).

## Files touched

`spec/08` (CS's settings rows); `apps/pages/server/cases.ts`, `server/views/casesWords.ts` (or a
`caseSettingsWords.ts` beside GR1d's `caseViewsWords.ts`); `tree-govuk/case-settings.njk`, `cases.njk` (the link);
`packages/glass-shared/src/investigation/cases.ts` (`FROM_THE_DATASET` moved) and
`apps/workspace/src/investigation/CaseDomains.tsx` (imports it); `test/govuk/case-settings.test.ts`, `casesConduit.ts`
(the access and datasets routes, refusing as the routes do), `keyboard/cases.spec.ts`, `scripts-off/cases.spec.ts`;
`OspreyFlow_Build/tests/glass_trees/test_govuk_cases_scenario.py` (the two models' census).

## Checks (frozen when cut)

GR1a's list, with the workspace's `CaseDomains` test for the moved sentence.

## Out of scope

Any change (GR1f2, GR1f3); the access history (question 7); the administrator's safety net (an administrator holding no
level cannot open the case's page, since `GET /v1/investigations/{id}` is Viewer-gated: the Admin area's); any Conduit
change; the Default tree's twin.
