# Slice GG2f1 · GG2 · Seeding and expanding the case's live working set on a GOV.UK page, with the cap's refusal in the canvas prompt's words (a draft)

**Status: a draft, not ruled.** Written in an away drafting session (D246), 26 to 27 November 2026, on the branch
`drafts/2026-11-27`, read from `origin/main` at `7f4f9554a` and from `away/GG2a`, `away/GG2c` and `away/GR1d`. No row in
`slices.tsv`; no builder starts from this paper. **Size M** (the first half of the plan's GG2f, L). **It draws with
Sigma 4, so by decision 9 it may be written meanwhile but merges only after WS4b** (`spec/06_DECISIONS.md` about lines
41091 to 41102; the owner's one exception is GG2c).

**Where it comes from.** The plan's row GG2f ("seed and expand with the refusal"), the `working-set` row of
`apps/pages/FUNCTIONS.yaml` (:197-203: "Working set, delta stream, cap refusal, batch expansion"), and scenario A9
(`spec/08_ACCEPTANCE_SCENARIOS.md` :390: relationships expand "with a cardinality preview first"; B5, B7 and B15, :556,
:558, :566, are Search Around and the Endpoint model, GG4i's query builder, not this slice's).
NEXT_BATCH question 9 (`slices/NEXT_BATCH_2026-11-24.md:45`): the canvas prompt's words are canonical. It builds on
GG2e (the live page at `/cases/graph?case=…`, the module fed by the stream through CO3's proxy, read-only actions),
GG2c (the delta client in `glass-shared`) and GG3a (the case's search page at `/cases/search?case=…`, whose brief
says "Adding to the working set (GG2b)" is out of its scope, `slices/GG3a.md:48`; the plan has since moved adding to
GG2f).

## What exists today (read on `origin/main` at `7f4f9554a`; re-read, lines move)

- **The routes** (`OspreyFlow_Core/services/api/app.py`), each `require_right(INVESTIGATE)`:
  - `POST .../seed` (:5655-5685), the case's **Editor** gate, `SeedRequest` (:5633-5635) of whole `Node` and `Edge`
    bodies. **The bodies are thrown away**: "a caller's body is used for its id alone"; each id is re-read through the
    Vault for the seeding principal, and a hidden id, a superseded id and a missing id are left out alike, with no error
    (`working_set/service.py:1073-1103`). A `Node` has required `provenance`, `handling` and `audit`
    (`packages/schemas/domain.py:515` onward), which a page does not hold.
  - `POST .../working-set/add-by-ids` (:5688-5722), Editor: `{node_ids, link_ids}` (`AddByIdsRequest`, :5638-5643),
    read by the same `_seed_ids` (`service.py:1105-1124`), answering `AddedByIds` with `not_shown`, a count, never which
    (`working_set/models.py:342-351`). History label `SEEDED`, audited `add_by_ids`.
  - `POST .../expand` (:5725-5756), Editor, `ExpandBody` (:5646-5648): `ExpandRequest` (`domain.py:693-698`, a plain `BaseModel`, as `AddByIdsRequest` and
    `ExpandBody` are: **an unknown key is dropped, not refused**, `batchExpansionApi.ts:113-115`: `node_ids`,
    `depth` 1 to 4, `edge_types`, `direction`, `temporal_window`) and a `justification`. Answers `ExpansionOutcome`
    (`models.py:323-340`): the `delta`, `links_among` (`added`, `not_asked`, `view_full`) and `clusters` "on this response
    only, never the shared stream (rule 3)".
  - `POST .../expand/preview` (:5797-5816), **Viewer**: `CardinalityPreview` (`models.py:442-462`): the candidate
    counts, `link_count` (the asked type's links the reader may see) and `would_breach`, the same `LimitExceeded` shape.
  - `POST .../links-among` (:5759-5794), Editor: all the links among the view's nodes, "or none and `limit_exceeded`".
- **The cap.** `MAX_NODES = 50_000`, `MAX_EDGES = 250_000` (`models.py:31-32`). `LimitExceeded` (:50-65): `error`,
  `cap_kind` (`nodes`, `edges`, `pairs`), `cap`, `would_be` and `options`, always the three
  `save_as_view`, `filter`, `promote_to_batch` (:40-47). Sent as a **409** (`app.py:3134-3136`).
- **The words** (`spec/02_GLASS_FRONTEND.md`): "Every expansion previews its cardinality before executing. Above 500 new
  nodes the action requires a filter or an explicit acknowledgement" (:992-995); at the cap, "Too many for the canvas:
  ‹n› nodes against a limit of ‹cap›." with "Nothing has been added.", then the three choices, each by keyboard:
  *Expand by one relationship instead* (not offered for an expansion already by one type), *Save a smaller view…* (the
  over-cap dialog's save form, titled "This expansion is too large", no *Try again*), *Run as a batch job*; "A 409 that
  is not the cap's stays 'Expand failed (409). Try again.'" (:997-1008).
- **What a page module can reuse, already plain TypeScript:** `EXPANSION_CONFIRM_ABOVE = 500`, `gateExpansion` and
  `narrowingOptions` (`packages/glass-shared/src/canvas/expansionGate.ts:8-53`). The React prompts are
  `apps/workspace/src/canvas/CapRefusalPrompt.tsx` (73 lines) and `LargeExpansionPrompt.tsx`; the figure's sentence is
  `figure()` in `workingset/ViewOverCapDialog.tsx:35-38` (React file). The per-type preview the menu shows is one
  `/expand/preview` per valid link type (`GlassCanvas.tsx` about :2906-2970).
- **The keyboard ids** in `CANVAS_ACTIONS` (`packages/glass-shared/src/keyboard/actionRegistry.ts:87-203`):
  `enter-expand` (:112), `backslash-open-menu` (:113), `menu-item-expand-by-edge-type` (:114),
  `show-links-among-all-by-keyboard` (:95), `overlay-dismiss-large-expansion` (:174), `expand-with-nothing-new-says-so`
  (:176), `large-expansion-add-all-by-keyboard` (:184), `an-expansion-leaves-the-view-and-the-settled-nodes-where-they-were`
  (:202), `overlay-dismiss-action-error` (:144).
- **A script on a page posts with `X-CSRF-Token`** from `<meta name="csrf-token">` (`apps/pages/tree-govuk/layout.njk:13`;
  `server/csrf.ts:48`); the forwarder carries every `/v1` path but the stream and `ws-ticket`, adds the person's bearer
  and passes a 409 through with its body (`server/forward.ts:1-56`).
- **The reader's level on the case** is read from the case list, as GR1a's page reads it (`server/cases.ts:6`).

## Acceptance (red before, green after)

Scenario **GW**'s seeding and expanding rows (after GG2e's), written first;
`apps/pages/test/govuk/live-graph-expand.spec.ts` (Playwright, both browsers, against the fixture Conduit and a fixture
stream) and `apps/pages/test/govuk/graph-seed.test.ts` (the search page's form), red on GG2e's page, green after;
GG2e's rows unchanged and green.

## Questions for the owner (the proposal first)

1. **Scope.** (a) **Put a search result on the graph (from GG3a's page), expand a node (Enter across every type, or one
   type from the node's menu), *Show links among* the view, and the cap's refusal with its three choices**, of which
   *Run as a batch job* hands over to GG2f2. Add by identifiers goes with GG2f2. (b) Expand only; seeding later.
2. **How a page seeds.** `/seed` wants whole bodies it then throws away, and a page holds none. (a) **The server half
   sends `POST .../working-set/add-by-ids` with the hit's node id**: the same `_seed_ids` read, the same cap and history
   label, ids only. `spec/03` §3.2 (:413 onward) and the route's docstring name add-by-ids as Ask's; their words gain
   "and a page's *Add to the graph*" (rule 11, a words change, no code). (b) The server half re-reads each hit's body and
   sends `/seed`: a second read for nothing. (c) The page builds a placeholder body: **not proposed** (a forged body is
   exactly what `seed` is written to ignore, and it would teach the page to make one).
3. **Seeding with scripts off.** (a) **A plain form on each search hit, "Add to the case's graph"**, posting to the
   page service with `_csrf` and the hit's id in a hidden field; the server half calls the route and answers `303` to
   `/cases/graph?case=…`, which with scripts off says GG2e's parity sentence. `not_shown` (if 1) is said as "It could
   not be added." and nothing more. A cap refusal from this form is a page of its own with the three choices (question
   6). (b) Scripts-on only.
4. **Expanding on the live page** (scripts on: the graph exists only there). (a) **The module calls the Conduit through
   the forwarder** (`fetch('/v1/…')` with `X-CSRF-Token`), as the React workspace calls through nginx; the result arrives
   on the stream as every other reader's does, so the module never applies `outcome.delta` twice (it applies the
   stream's frame and ignores the response's delta, keeping only `links_among`'s words). (b) Every expansion a form post
   and a reload: no.
5. **The preview and the 500 gate.** (a) **Before every expansion one `/expand/preview`; `gateExpansion` decides**; above
   500, or a count that could not be read, the module asks first in `LargeExpansionPrompt`'s words ("This would add ‹n›
   nodes, more than 500.", one relationship instead, everything, or nothing), and `would_breach` goes straight to the cap
   refusal with nothing sent. The node's menu shows each type's `link_count`, "count unavailable" when its preview
   failed, and folds the types with none into one line, as `spec/02` :1198-1200 says. (b) Expand without preview: against A9.
6. **The cap refusal's words** (NEXT_BATCH question 9, the canvas prompt canonical). (a) **The page's words are
   `spec/02` :997-1008 word for word**: "Expanding ‹name› was refused.", "Too many for the canvas: ‹n› nodes against a
   limit of ‹cap›.", "Nothing has been added.", then *Expand by one relationship instead* (each type with what it would
   add; not offered when the expansion was already by one type), *Save a smaller view…* (a link to GR1d's save form on
   the case's page, which saves a filtered view; titled "This expansion is too large", no *Try again*), *Run as a batch
   job* (GG2f2's form), and *Cancel*. The sentence is made one plain function in `glass-shared` (I11, the React file
   re-pointed, behaviour unchanged) so both front ends say one sentence. **`glass-shared/src/canvas/linksAmong.ts:70-71`
   already holds a copy that prints `cap_kind` raw ("edges" by default)**: the one function replaces that copy too, so
   `cap_kind: "edges"` says "links" everywhere, *Show links among* included (case 12). (b) The page's
   own words.
7. **The graph while the refusal is open.** (a) **Unchanged**: nothing drawn, nothing cut, the focus moved into the
   refusal (an `alertdialog`), Escape returning it to the node; a node taken out by another reader's delta while it is
   open closes it (`spec/02` :1007). (b) Your words.
8. **Who is offered what.** (a) **Expanding, *Show links among* and *Add to the graph* are offered to an Editor and
   above** (the routes' gate), read from the case list's level; a Viewer sees the menu's counts (preview is Viewer) and
   no action. A hand-made post by a Viewer gets the route's 403, said "You need the Editor level on this case to change
   its graph." (b) Offer to everyone and say the refusal after.
9. **The expansion's justification** (`ExpandBody.justification`). (a) **Not asked on the page**, as the React canvas
   does not ask it either; the builder confirms that and says so. (b) A field on the large-expansion prompt.
10. **`clusters` on the expand response** (per-reader, never on the stream). (a) **Ignored by this slice**; match
    strictness on a page is GG4i's. (b) Drawn now.
11. **The batch choice between merges (rule 2).** The refusal offers *Run as a batch job*, which is GG2f2's form. (a)
   **GG2f1 and GG2f2 merge together, in one merge train**, so the refusal never offers a choice that leads nowhere. (b)
   GG2f1 merges first and shows only the two choices it can carry out until GG2f2 lands: the typed refusal names three
   options (`models.py:40-47`), so (b) shows fewer than the Conduit gives for one merge's time.

## The table of cases (each red first; the planted fault at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | An Editor adds a search hit "Pier office" (synthetic) with scripts off | one `POST .../working-set/add-by-ids` whose body equals exactly `{node_ids: [<id>], link_ids: []}` (the fixture records it; the route would drop an extra key silently, so the body is asserted, not refused); `303` to `/cases/graph?case=…` | `_csrf` passed through in the body |
| 2 | The same with scripts on | the node appears from the stream's frame, once | the module applying both the response's delta and the stream's (the fixture counts `applyDelta` calls) |
| 3 | A hit the reader may no longer see (`not_shown: 1`) | "It could not be added."; no id, no reason, no count but that | the page saying "hidden" or "not found" |
| 4 | Enter on a focused node whose preview says 12 | one preview, then one `/expand` with `node_ids: [that node]`, `depth: 1`, no `edge_types`; the 12 drawn from the stream | the expand sent without the preview |
| 5 | Preview says 640 | the large-expansion prompt, nothing sent; "everything" sends it, one type sends that type, Escape sends nothing | the gate's threshold read as 5,000 (the constant copied, not imported) |
| 6 | Preview's count fails | asked first, "The size of this expansion could not be counted."; nothing sent | an unreadable count treated as 0 |
| 7 | Preview's `would_breach` | the cap refusal at once, nothing sent to `/expand` | the expand sent anyway and its 409 waited for |
| 8 | `/expand` answers 409 `limit_exceeded` (nodes, 63,210 against 50,000) after an earlier expansion that succeeded | the spec's sentences word for word; three choices and Cancel; the graph's node and link count unchanged | the module applying the delta it kept from the earlier successful response again on the refusal (the fixture stream sends nothing for the refused call) |
| 9 | The same refusal for an expansion by one type | *Expand by one relationship instead* not offered | offered |
| 10 | `cap_kind: "edges"` | "links", not "edges" | the field's value printed |
| 11 | A 409 that is not the cap's (`error` absent or another) | "Expand failed (409). Try again." | read as the cap's |
| 12 | *Show links among* past the cap | the same refusal, nothing added; `view_full` on an expand said as the links not brought "because the view would be too large" | the refusal read as "no links" |
| 13 | A Viewer | counts in the menu, no expand, no add; a hand post's 403 in the page's words | the actions offered by the module without the level |
| 14 | Another reader's delta removes the node while the refusal is open | the refusal closes, focus to the canvas | the refusal left over a node that is gone |
| 15 | No internal id in the HTML, the live region or the refusal | none (the hit's id only in a hidden field) | the node id in the prompt's text |
| 16 | Keyboard | one case per id in the list above (rule 13), in `test/govuk/keyboard/`; `assertAllCovered` red with one removed | an id offered with no case |
| 17 | The fixture | refuses as the routes do: 409 `limit_exceeded` with the exact `LimitExceeded` body, 403 below Editor, 404 for another case; an unknown key dropped, as the plain models drop it, and every body recorded for the cases' exact-body asserts | a fixture that accepts a Viewer's expand |

## Waits on

GG2e (the live page and its module); GG2c (the delta client in `glass-shared`); CO3 (the stream proxy, merged); GG3a
(the search page the add form sits on); GR1d (the save form *Save a smaller view…* links to); GG2f2 (question 11: the
batch choice); **WS4b to merge** (decision 9).

## Files touched

`spec/08` (GW's rows); `spec/03` §3.2's words for add-by-ids (question 2; the route's docstring in `services/api/app.py`
is left as it is, so no Conduit file changes); `apps/pages/modules/graph/`
(the expand menu, the prompts, the forwarder calls); `apps/pages/server/` (the search page's add form, its handler);
`tree-govuk/` (the search hit's form, the refusal page for the form); `packages/glass-shared/src/canvas/` (the cap
sentence, one function with its unit test, `linksAmong.ts` re-pointed to it) and `apps/workspace/src/workingset/ViewOverCapDialog.tsx` re-pointed (I11);
`test/govuk/live-graph-expand.spec.ts`, `graph-seed.test.ts`, `keyboard/`, `scripts-off/`, the fixture Conduit's routes.

## Checks (frozen when cut)

GG2e's list, plus the React workspace's whole suite and its budget (the moved sentence, I11) and
`test_route_rights.py` unchanged (no route changed).

## Out of scope

Batch expansion and add by identifiers (GG2f2); the selection, drag, remove, groups and suppression (GG2g); match
strictness and clusters (GG4i); the inspector (GG3d); any Conduit code change; `apps/workspace` beyond the one re-pointed
import.
