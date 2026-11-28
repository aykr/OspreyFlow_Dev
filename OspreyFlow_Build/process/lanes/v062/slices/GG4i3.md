# Slice GG4i3 · GG4 · Match strictness and its explanation on the case's live graph page: Strict, Balanced or Broad by form, the change said in figures, and why a group was shown as one (a draft)

**Status: a draft, not ruled.** Written in an away drafting session (D246), 26 to 27 November 2026, on the branch
`drafts/2026-11-27`, read from `origin/main` at `7f4f9554a`. No row in `slices.tsv`; no builder starts from this paper.
**Size M.** The third of GG4i's four parts. **Its explanation opens from a selected item on the Sigma canvas, so by
decision 9 it may be written meanwhile but merges only after WS4b** (`spec/06_DECISIONS.md` about lines 41091 to 41102).

**Where it comes from.** The `query-builder` row (`apps/pages/FUNCTIONS.yaml:276-282`). **This part takes B9 and B10**
(`spec/08_ACCEPTANCE_SCENARIOS.md:560`: "Move the resolution threshold from Strict to Balanced … The merge applies; the
change summary reports entities merged and nodes affected"; :561: "Open `explain` on the merged `Person` cluster …
Per-comparison match weights are shown, not just the total score"). Rules 5 and 6: a match score is inferred, and
resolution writes scored `SAME_AS` links that are collapsed when read, never merged in storage.

## What exists today (read on `origin/main` at `7f4f9554a`; re-read, lines move)

- **The strictness routes** (`services/api/app.py`), each `require_right(INVESTIGATE)`:
  - `GET .../resolution/threshold` (:5924-5942), **Viewer**: `ThresholdResponse` (`threshold`, a number,
    `services/api/resolution.py:29-30`). Audited `get_resolution_threshold`.
  - `PUT .../resolution/threshold` (:5945-5966), **Editor** (`InvestigationEditorDep`, :5950): `SetThresholdRequest`
    (`threshold` 0 to 1, `resolution.py:33-34`), answered `ResolutionOutcome` (`services/api/working_set/models.py:462-473`):
    the `delta` every reader receives and `merged`, `split`, `affected`, "as the acting analyst's own view counts them …
    they are not on the delta, which other readers receive". The delta is published to every reader's stream (:5958).
  - **The threshold is the case's working set's, shared by its readers**: one Editor's change re-projects every reader's
    view (`working_set/service.py:589-630`); the counts cannot leak a hidden item, since a node the actor cannot see
    "always arrives with no edges … an untouched singleton at every τ" (:617-624).
- **The three stops**: `THRESHOLD_STRICT = 0.99`, `THRESHOLD_BALANCED = 0.95`, `THRESHOLD_BROAD = 0.80`, default
  Balanced (`services/resolve/projection.py:31-34`). The React control offers exactly these three
  (`apps/workspace/src/resolution/ThresholdControl.tsx:16-23`) and says "Match strictness: Balanced — 3 merged, 0 split, 47
  affected" (:111).
- **The explanation.** `GET .../resolution/explain/{cluster_id}` (`app.py:6058-6077`), **Viewer**: `ClusterExplanation`
  (`models.py:431-440`): `cluster_id`, `member_node_ids`, and `pairs` of `PairwiseExplanation` (:412-428): `node_a`,
  `node_b`, `edge_type` (`SAME_AS` or `NOT_SAME_AS`), `score`, `model_version`, `comparison_vector`,
  `manually_asserted`, `meets_threshold` (against the current τ). A cluster id is the reader's own ("the reader's own
  clusters, as their canvas was given them", ADR-124 Amendment 19, `service.py:883-885`), carried to the module on the
  delta's `affected_cluster_ids` (`models.py:265`). A cluster the reader cannot see any member of is 404
  `cluster_not_found` (`app.py:3732-3736`), "indistinguishable from the cluster never having existed" (`service.py:876-880`).
- **The React explanation** (`apps/workspace/src/canvas/ClusterExplainOverlay.tsx`, fetched at `GlassCanvas.tsx:2768-2790`)
  draws a pair only when the answer's members **and** the canvas both hold both ends (`resolution/explainView.ts:17-28`),
  and says a pair's basis ("Asserted by analyst", or the score, the model and the comparison vector, :39-49). Its keyboard
  ids are `menu-item-explain-cluster` (`packages/glass-shared/src/keyboard/actionRegistry.ts:117`) and
  `overlay-dismiss-cluster-explain` (:127).
- **The page it sits on.** GG2e's `/cases/graph?case=…`; with scripts off that page says the live graph needs scripts
  (GG2e question 2, ruled (a)).

## Acceptance (red before, green after)

Scenario **RS** (new; "resolution strictness"), written first in `spec/08`, with B9 and B10 run on the GOV.UK tree as
its last rows; `apps/pages/test/govuk/match-strictness.test.ts` (the form, scripts off) and `live-explain.spec.ts`
(Playwright) red on GG2e's page, green after. B9's and B10's existing tests stay green and unchanged.

## Questions for the owner (the proposal first)

1. **Where it sits.** (a) **A "Match strictness" part of GG2e's graph page, server-rendered, which works with scripts off**:
   the current setting in words and a form of three radio buttons (Strict, Balanced, Broad), each with one sentence of
   what it does. The explanation is a panel of the same page, scripts on. (b) Both scripts on.
2. **A setting that is not one of the three** (the route takes any number from 0 to 1, so another client may set 0.9).
   (a) **Said as "Custom (0.90)", with the three offered; nothing changed until one is chosen.** (b) Shown as the nearest.
3. **The change in words.** (a) **After the `PUT`, a `303` back to the page with a banner: "Match strictness is now
   Balanced. 3 groups were shown as one, 0 were split, 47 items were affected. Nothing was merged in storage; the
   matches are a model's and stay inferred until a person confirms them"** (rules 5 and 6). The figures are the actor's own
   (the answer's), and are shown only to the actor. (b) The React control's words.
4. **A change reaches every reader of the case.** (a) **The form says so before it is sent ("This changes how the case's
   graph is shown to everyone who reads it")**, since the threshold is the case's, not the reader's. (b) Say nothing.
5. **Who may change it.** (a) **Offered to an Editor of the case (the route's gate); a Viewer sees the setting and no
   form**, offered from the case level the page already reads. A hand post by a Viewer is refused as the route refuses it,
   said in words. (b) Offered to all, refused after.
6. **Opening the explanation.** (a) **When the selected item (GG2e2's selection) belongs to a group shown as one, the
   panel offers "Why are these shown as one?"**, which sends the `GET` with the item's cluster id from the store, never
   from the address or the page's HTML. (b) A list of every group in view, each explainable.
7. **What the explanation shows.** (a) **A table: each pair by the two items' labels (from the store), the link ("the
   same as" or "not the same as"), the basis ("Asserted by a person", or "A model's score: 0.97, model v3, inferred"),
   whether it meets the current setting, and the comparison vector as its own sub-table, one row a comparison (B10:
   "per-comparison match weights … not just the total")**. A pair whose either end the store does not hold is left out
   entirely, never shown redacted (`explainView.ts`'s rule). (b) The React overlay's one-line basis.
8. **A stale group** (404 `cluster_not_found`, after a later change). (a) **"These are no longer shown as one. The graph
   has changed since"**, the panel closed. (b) The React words, "Explain cluster failed (404). Try again".
9. **Manual same-as and split** (`RESOLVE_ENTITIES`, B11). (a) **Not here: the inspector's link change (GG3d2).**
   (b) Here, beside the explanation.

## The table of cases (each red first; the planted fault at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | B9 on the GOV.UK tree: Strict to Balanced, as an Editor, on the fixture's close `Person` pair (synthetic) | one `PUT` with `threshold` 0.95; `303`; the banner with the answer's `merged` and `affected` | the banner's figures counted by the page from its own store |
| 2 | The setting read on load | "Balanced" from `GET .../threshold`; one read per render | the stop drawn from the page's own default |
| 3 | A setting of 0.9 | "Custom (0.90)"; three choices, none checked | 0.9 shown as Balanced |
| 4 | A Viewer | the setting in words, no form; a hand post refused and said in words | the form offered from `investigate` alone |
| 5 | Two readers of different clearance after a change | each reader's view re-projected through the stream; the second reader shown no figures | the actor's figures sent to every reader |
| 6 | No `_csrf` | refused, nothing sent (I17) | the form outside the check |
| 7 | B10: explain the merged `Person` group | each pair by its labels, its basis, and its comparison vector as rows | the vector joined into one string, the weights not shown per comparison |
| 8 | A pair whose end the store does not hold (the fixture sends one) | left out; no redacted row | the pair drawn with "unknown" for the missing end |
| 9 | A manually asserted pair | "Asserted by a person"; no score | a blank score shown as 0 |
| 10 | A model's pair | the words say "inferred" (rule 5) | "confirmed" or no provenance word |
| 11 | A stale group | question 8's sentence | the 404 said as an error to retry |
| 12 | Two readers, the same item: the explanation | each sees only pairs between items they may see | at the page's call site: the module's explanation kept by cluster id in the browser's shared storage and reused for a second reader signed in on the same browser, or one reader's bearer reused for the other's request |
| 13 | No id or cluster id in visible text or the live region | none (rule 7) | the cluster id printed as the panel's heading |
| 14 | Keyboard | the strictness form by keyboard; `menu-item-explain-cluster` and `overlay-dismiss-cluster-explain` each a case in `test/govuk/keyboard/` (rule 13) | the panel's close not reachable |
| 15 | Scripts off | the setting and the form work; the explanation's place says it needs scripts | an empty panel |

## Waits on

GG2e (the page) and GG2e2 (the selection the explanation opens from); PL8b (the panel); WS4b to merge. Nothing for
the owner.

## Files touched

`spec/08` (RS); the graph page's server half (`apps/pages/server/`) for the strictness part and its post, its words
(`server/views/`), its template (`tree-govuk/`); `apps/pages/modules/graph/` (the explanation panel);
`packages/glass-shared/src/resolution/` (`explainView.ts`'s two pure functions moved there, behaviour unchanged, I11,
with their tests; the React overlay's import re-pointed); `test/govuk/match-strictness.test.ts`,
`live-explain.spec.ts`, `keyboard/`, `scripts-off/`, the fixture Conduit's three routes (narrowed, refusing as the routes
refuse); the scenario test's census of `ThresholdResponse`, `ResolutionOutcome` and `ClusterExplanation`.

## Checks (frozen when cut)

GG2e's list, plus `apps/workspace`'s `resolution/` suite (unchanged and green after the move).

## Out of scope

Manual same-as and split (GG3d2); the resolution run and "Resolve now" (the Studio's); any Conduit change;
`apps/workspace` beyond the re-pointed import.
