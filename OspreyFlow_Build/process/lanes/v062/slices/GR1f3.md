# Slice GR1f3 · GR1 · Changing what a case reads, as a scripts-off form; its domain models said, never offered (a draft)

**Status: a draft, not ruled.** Written in an away drafting session (D246), 26 to 27 November 2026, on the branch
`drafts/2026-11-27`, read from `origin/main` at `7f4f9554a`. No row in `slices.tsv`; no builder starts from this paper.
**Size S** (about 11 cases). GR1f's third part, on GR1f1's settings page, with GR1f2's write pattern.

**Where it comes from.** The chain plan's row GR1f ("datasets and domains", `CHAIN_PLAN.md:59`). ADR-099 (a case reads
exactly one dataset, a source or a composite, changed by its Author: Amendment 12; each dataset shown with its id "in the
choice of what a case reads": Amendment 6 point 4, `spec/06_DECISIONS.md:10569`); ADR-145 Amendment 4 decision 2 (a
dataset's home case keeps reading it while the dataset exists); ADR-126 Amendment 2 (the packs come from the dataset's
domain model). The React workspace's "Data this case reads" (`apps/workspace/src/investigation/CaseDatasets.tsx`) and
"Domain models" (`CaseDomains.tsx`).

## What exists today (read on `origin/main` at `7f4f9554a`; re-read, lines move)

- **What the case reads.** `PUT /v1/investigations/{id}/datasets` (`set_case_datasets_route`,
  `services/api/app.py:4332-4371`): `require_right(SHARE_CASE)` and the **Author** gate; body `CaseDatasetsRequest`
  `{dataset_ids}`, 1 to 100 long (`services/api/datasets.py:164-167`), and the store takes exactly one
  (`_one`, `datasets.py:1300`). A dataset's home case choosing anything but its own dataset is **409 `home_case_kept`**
  (:4349-4359), before anything is written. A dataset not of the Author's unit, not a source or a composite, or not
  at all is the one **422 `dataset_refused`** with no detail (`datasets.py:1301-1309`; handler `app.py:3823-3828`).
  It answers the datasets the case now reads; audited `set_case_datasets` with before and after.
- **What may be chosen.** `GET /v1/datasets` (`app.py:4277-4281`): the caller's unit's datasets, **never an analyst
  layer or a drawn one** (`datasets.py:848`, :1028-1035), by name; none to a caller holding no right.
- **The domain models.** `PATCH /v1/investigations/{id}` refuses any `domains` with **409 `packs_from_the_model`**
  (`app.py:4489-4499`).
- **Renaming and removing a case** (`PATCH` with a name, :4474-4524; `DELETE`, :4527-4558) are routes too, but **neither is
  in the plan's GR1f row** (`CHAIN_PLAN.md:59`, "settings, access, datasets and domains"), and `spec/02` names no Glass
  surface for either (`renameCase` and `removeCaseOnServer` are in `packages/glass-shared/src/investigation/cases.ts:274`,
  :227). Found on the way: **a case's name has no length limit** at creation or rename (`CreateInvestigationInput.name`,
  `app.py:4216`; `CaseChangeInput`, :4450-4471; the store's `rename`, `services/api/investigations.py:532-545`).
- **The React words**: `setCaseDatasets` says 403, 422 and the 409 by the Conduit's message
  (`packages/glass-shared/src/investigation/cases.ts:97-115`); `datasetLabel` (:269-272); `FROM_THE_DATASET`
  (`CaseDomains.tsx:19-20`, moved to `glass-shared` by GR1f1).

## Acceptance (red before, green after)

Scenario CS's dataset-change rows, written first after GR1f2's; `apps/pages/test/govuk/case-datasets-change.test.ts`,
red on GR1f2's page, green after; GR1f1's and GR1f2's rows unchanged and green.

## Questions for the owner (the proposal first)

1. **Scope.** (a) **Change what the case reads**; the domain models are said, with GR1f1's sentence, and never offered
   (the route refuses every change). **Renaming and removing the case are out, a later part**: neither is in the plan's
   row nor in `spec/02`; the conductor adds a row if wanted. (b) Rename and remove here as well (about six more cases,
   size M).
2. **Choosing the dataset.** (a) **GOV.UK radios, one per dataset `GET /v1/datasets` sends, in its order, each labelled
   with its id as ADR-099 Amendment 6 point 4 says for "the choice of what a case reads" (`datasetLabel`), a composite
   also said as "a composite of 3 datasets"**; the one the case reads now checked; the page sends exactly one id, in a
   radio's value, never typed. A case whose current dataset is not in the list (another unit's, or a drawn one) shows it
   as GR1f1 does, with no radio for it. (b) A select box: harder by keyboard with many datasets.
3. **Saying what a change does.** (a) **One sentence above the button**: "Everyone who can open this case will read the
   dataset you choose instead. Nothing is deleted." The page claims nothing about the case's graph or its domain models,
   which the route does not say. (b) A confirmation page: one more step for a change that can be changed back.
4. **A dataset's home case.** (a) **The form is still drawn, and the 409 `home_case_kept` is said in the page's own
   words**: "This case is its dataset's home case, so it keeps reading that dataset." The page cannot know beforehand:
   no route a reader calls says which case is a home case. (b) An amendment that says it in `Investigation` (decision 11),
   so the form is not offered: the owner's, and later.
5. **Refusals in words.** (a) **One sentence for each**: 422 `dataset_refused` "That dataset is not one this case can
   read." (the React words); 403 on a hand post "Only the case's Author can change this."; an unknown code "Nothing was
   changed." (b) The Conduit's messages.
6. **After a change.** (a) **A `303` to the settings page with one banner** carried in the session (GR1f2's pattern):
   "This case now reads <name>." (b) No banner.

## The table of cases (each red first; the planted fault at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | The Author chooses another source dataset (synthetic, "Harbour logs 2026") | one `PUT .../datasets` with exactly `{"dataset_ids": ["<its id>"]}`; `303`; the banner names the dataset the route's answer says the case now reads | the banner drawn from the posted id rather than the answer |
| 2 | The radios | one per dataset sent, in its order, each by `datasetLabel` (and a composite's member count), the current one checked; no analyst layer or drawn dataset (the fixture sends none, as the route) | the list sorted by the page; the id left out of a label; a typed id field |
| 3 | Two ids posted by hand | the page sends none and says "Choose one dataset." | both sent |
| 4 | The home case (the 409) | the page's sentence; nothing changed | the 409's message shown |
| 5 | Another unit's dataset posted by hand (the 422) | "That dataset is not one this case can read." | the 422 drawn as "could not be read" |
| 6 | The domain models | GR1f1's sentence; no field, no button, nothing ever sent with `domains` | a form offered |
| 7 | An Editor with `share_case` | no change form; a hand post said "Only the case's Author can change this." | the form offered on `share_case` alone |
| 8 | No `_csrf`, an empty one, a wrong one | refused, nothing sent (I17) | the form outside the check |
| 9 | The fixture | refuses as the route does, in its order (the right, the level, then the home case before the dataset check) | a fixture that checks the dataset before the home case |
| 10 | One render of the form | the settings page's reads (GR1f1's and GR1f2's) and `GET /v1/datasets`, each once | a second datasets read |
| 11 | Keyboard and scripts off | the radios and the button reachable and working, one keyboard case for the action (rule 13) | a radio out of the tab order |

## Waits on

GR1f2 merged (its write pattern and the settings page's `GET /v1/me/rights` read).

## Files touched

`spec/08` (CS's dataset-change rows); `apps/pages/server/cases.ts`, the settings words (GR1f1's file);
`tree-govuk/case-settings.njk`; `test/govuk/case-datasets-change.test.ts`, `casesConduit.ts`, `keyboard/cases.spec.ts`,
`scripts-off/cases.spec.ts`; the scenario test's input census (`CaseDatasetsRequest`).

## Checks (frozen when cut)

GR1f2's list.

## Out of scope

Renaming and removing the case (question 1); a composite made from the page (`POST /v1/datasets/composites`, the
Studio's and Admin's); a new dataset made here (GR1b makes one with a new case); changing the domain models (the Studio's
Model tab); a name limit or a home-case flag (Conduit parts, amendments); the administrator's safety net;
`apps/workspace`.
