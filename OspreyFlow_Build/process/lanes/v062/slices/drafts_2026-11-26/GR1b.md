# Slice GR1b · GR1 · New case as a GOV.UK page, scripts off: the case's name, the data it reads (an existing dataset or a new empty one) and its domain models, posted once (a draft)

**Status: a draft, not ruled.** Written on the server's build account in an away round (D246), 26 November 2026, on the
branch `drafts/2026-11-26`. No row in `slices.tsv`; no builder starts from this paper.

**Where it comes from.** The owner ruled on GR1a's draft (25 November, as GR1a's away report records them) that **New
case is GR1b**, which answers NEXT_BATCH question 7 for GR1. GR1a (built on `away/GR1a`, not merged) is the reader's
cases at `/cases` and one case at `/cases?case=<id>`. `spec/02_GLASS_FRONTEND.md` (about lines 949 to 962): a new case
asks *What data does this case read?*: *Use an existing dataset…* or *Make a new dataset, empty, loaded in the Ingest
Studio* (the default), "with a field for its name that, left empty, takes the case's"; and *Domain models*, three
boxes, "with none ticked, 'Bespoke POLE (the core model)' is said beside them". ADR-099 Amendment 12 item 6 (R16).

## What exists today (read on `origin/main` at `042c882f2`; re-read, lines move)

- **The route.** `POST /v1/investigations` (`create_investigation`, `services/api/app.py:4229-4275`), behind
  `require_right(CREATE_CASE)`, "needs no grant: whoever creates a case is its first Author". Body
  `CreateInvestigationInput` (:4214-4226): `name` (optional, `Untitled case` if left out, :4211), `dataset_ids`,
  `new_dataset_name` (up to `MAX_DATASET_NAME`), `domains` (`DomainPack` list; left out is "never chosen"; an empty list
  is a choice; an unknown pack is 422).
  - "**A case reads exactly one dataset: name one, or a new one**" (:4250-4251), and a named one must be the unit's
    (:4253-4255), both `DatasetRefusedError`.
  - A new dataset is made **before** the case, "so a name already taken refuses the whole request" (:4257-4258), also
    a `DatasetRefusedError` (`services/api/datasets.py:365-366`, through `_free_name` :479).
  - **All three answer the same `422 {"error": "dataset_refused"}`, with no detail** (handler `app.py:3823-3828`). The
    page can tell them apart only by which branch it sent (an existing dataset or a new name). An unknown domain pack
    fails the body's own validation (`DomainPack`, :4226) before any of them.
  - Packs sent with a dataset that has a live model are not stored (:4259-4263).
  - Audited `create_investigation` with the dataset ids (:4266-4272). Answers `Investigation` with its derived packs.
- **The choices.** `GET /v1/datasets` (`list_datasets_route`, :4278-4281): the unit's datasets, "none to a caller holding
  no right". The new-dataset name is **not** defaulted by the route: "left empty, takes the case's" is the Glass's.
- **The React form.** `apps/workspace/src/investigation/NewCaseForm.tsx` (131 lines), `DatasetChoice.tsx` (35),
  `DomainChoice.tsx` (42); the plain parts are in `packages/glass-shared/src/investigation/cases.ts`
  (`createCase`, `datasetChoiceLabel` :261, `DOMAIN_PACKS`, `domainLabels`; exported at `src/index.ts:241-249`).
  Keyboard: `apps/workspace/keyboard/case-datasets.spec.ts`.
- **The pattern for a write** is the Studio's (`apps/pages/server/studio.ts:732-738`: `methods: ["GET", "POST"]`, the
  server half calling the Conduit, a `303` back, :241) with `_csrf` (`csrf.ts`). GG4c proposes the same for boards.
- **The page registry** allows one page per `FUNCTIONS.yaml` row in a tree (`server/pages.ts:133-136`), and GR1a's
  `/cases` already is the `cases-and-views` row's page. **So New case cannot be a page of its own today**: it is either
  a form on `/cases` (its `POST`), or a second page after GR1c.

## Acceptance (red before, green after)

Scenario CS's new rows (CS16 onward), written first, and `apps/pages/test/govuk/cases-new.test.ts`, red on GR1a's page,
green after; GR1a's CS1 to CS15 unchanged and green.

## Questions for the owner (the proposal first)

1. **Where the form is.** (a) **At `/cases?new=1` (the list page's own `POST` handling it), "New case" a button on the
   list**, until GR1c gives it `/cases/new`. (b) Wait for GR1c.
2. **When the form is offered.** (a) **When `GET /v1/me/rights` holds `create_case`**; a post by hand without it is said
   as "You cannot make cases". (b) Always offered.
3. **The data it reads, scripts off.** (a) **Both choices on one form as GOV.UK radios with conditional content**: *Make
   a new dataset* (the default) with its name field, and *Use an existing dataset* with the unit's datasets as a second
   group of radios. With scripts off, every field is shown; the server reads only the chosen branch's field and **sends
   exactly one of `new_dataset_name` and `dataset_ids`**, so "returning to *Make a new dataset* forgets the dataset
   chosen" holds by construction. (b) Two steps: choose the kind, then its field.
4. **The new dataset's name left empty.** (a) **The server half sends the case's name, as `spec/02` says**; if the case's
   name is empty too, the route's `Untitled case` is sent for both. (b) Refuse an empty name.
5. **Domain models.** (a) **Three checkboxes labelled as `domainLabels` labels them, with "Bespoke POLE (the core
   model)" said beside them when none is ticked; the list is sent as ticked, empty included** (an empty list is a
   choice, `app.py:4223-4225`). When the existing dataset chosen has a live model, the page says "This dataset's model
   decides its domain models" and the boxes are not sent. The builder reads whether a route says which datasets have a
   live model; **if none does, the sentence is left out and the boxes are always sent** (the route ignores them, :4262). (b)
   Leave domains out.
6. **`dataset_refused`, which carries no detail.** (a) **Said by the branch the page sent: for a new dataset, "A
   dataset with that name may already exist. Choose another name", against the name field; for an existing one, "That
   dataset cannot be used for a new case", against the choice**, the person's words kept and nothing made (the route
   refuses before the case exists). The page never claims to know which rule refused it. (b) A Conduit part that adds a
   reason to the refusal (an amendment, decision 11).
7. **After the case is made.** (a) **`303` to the new case's page** (`/cases?case=<id>`), with a banner "Case made. Its
   data is loaded in the Ingest Studio", and a link to the Studio when a new dataset was made. (b) To the list.
8. **The scenario and the fixture.** (a) **CS extended, written first; the fixture refuses as the route does, in its
   order**: 403 for the right; 422 for the body (an unknown pack among them); then the one `422 dataset_refused`, the
   same answer for all three of the route's dataset rules, as the real handler sends it. (b) Your words.

## The table of cases (each red first; the planted fault at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | "Harbour thefts" with a new dataset "Harbour 2026" | one `POST /v1/investigations` with `name` and `new_dataset_name` only; `303` to the case's page; the banner | `dataset_ids` sent as well (the fixture refuses it, as the route does) |
| 2 | An existing dataset chosen | `dataset_ids: [<its id>]` and no `new_dataset_name` | the name field's leftover text sent too |
| 3 | A new dataset with its name left empty | the case's name sent as the dataset's | an empty string sent (the route refuses) |
| 4 | Both names empty | `Untitled case` for both | a refusal of the person's empty name |
| 5 | Two boxes ticked | `domains` with the two | the boxes' labels sent in place of the packs' ids |
| 6 | None ticked | `domains: []` sent, and "Bespoke POLE (the core model)" shown | `domains` left out (a different meaning: "never chosen") |
| 7 | A dataset name already taken (the fixture answers `422 dataset_refused`, as the route does) | question 6's sentence against the name field, words kept, no case made | the case made first (the fixture models the route's order: the dataset before the case) |
| 8 | A dataset not the unit's, posted by hand (the same `422 dataset_refused`) | question 6's sentence against the choice, nothing made | the page saying "the name is taken" for a refusal of an existing dataset (the branch ignored) |
| 9 | A reader without `create_case` | no button; a hand post said as "You cannot make cases" | the button drawn from the case level |
| 10 | No datasets to choose (the route sends none) | only *Make a new dataset* offered, with no empty group | an empty radio group |
| 11 | No `_csrf` | refused, nothing sent (I17) | the route outside the check |
| 12 | The Conduit gives no answer, or 401 | the 502 page says nothing was made; 401 says to sign in again | a success banner |
| 13 | One case made | exactly one `POST` (one audit row) | a second post on reload (no `303`) |
| 14 | Keyboard | the form, both radio groups and the boxes reachable and working (rule 13) | a group out of the tab order |
| 15 | Scripts off | the form completes (I4) | none: the page holds no script |
| 16 | No dataset id on the page outside a form value | the radios name datasets by name alone (`spec/02`: "a raw id reads as noise") | an id printed beside a name |

## Files touched

`spec/08` (CS16 onward); `apps/pages/server/cases.ts` (the `POST` half), `server/views/casesWords.ts`;
`tree-govuk/cases.njk` and a new-case partial; `test/govuk/cases-new.test.ts`, `casesConduit.ts` (the create route's
refusals), `keyboard/cases.spec.ts`, `scripts-off/cases.spec.ts`; `OspreyFlow_Build/tests/glass_trees/test_govuk_cases_scenario.py`
(the census of `CreateInvestigationInput` and `Dataset`).

## Checks (frozen when cut)

GR1a's list, with `apps/pages/test/server/csrf.test.ts` (I17) over the new `POST`.

## Out of scope

The case's datasets changed later (GR1f); a composite dataset made from the form (`POST /v1/datasets/composites`); the
no-case drawing; `apps/workspace`; the Default tree's twin.
