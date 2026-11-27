# Slice SE9f · SE9 · An accepted extraction candidate never sets a Document's `object_ref` or `media_kind` (security; the owner, 26 November 2026, before RL2)

- **Build id:** SE9 · **Dial setting:** balanced · **Rounds limit:** the dial's · **After:** nothing
- **Security part (SE7c's shape):** never accepted narrower; judged by the verifier, the server and the full gate.

## What (found by SE9e's builder, 26 November 2026; not yet run end to end)

`POST /v1/investigations/{investigation_id}/ingest/extract` (`services/api/app.py` about 6131 to 6160, `run_extraction_route`)
takes the caller's `profile.entity_types` (`RunExtractionRequest`, `services/api/review.py` about 151 to 160), and nothing
found excludes `Document`. Accepting a candidate (`accept_candidate`, `review.py` about 540 to 570; the one path every
accept route reaches: `app.py` about 6194, 8140, 8166 and 8377) merges the caller's `properties_override` into the new
node's properties (`properties={**record.properties, **(properties_override or {})}`), so a Document's `object_ref`, and
`media_kind`, can be set by the caller, or by the model's own extracted properties. **The owner's rule (SE9e, (a)): only
the engine's own writes set `object_ref` and `media_kind` on a Document.**

## Round 1

1. **First, show the route end to end on main, red** (a pure test with the route's fakes; no store): a caller with
   `EXTRACT_FILES` and edit access extracts with `Document` among the entity types, accepts with
   `properties_override={"object_ref": <another file's reference>}`, and the written node carries it. If the route
   refuses this somewhere you did not expect, **say where and stop**: the finding would be narrower than reported.
2. **The rule in `accept_candidate`** (every accept path), not in each route: a Document candidate whose final properties
   (extracted or overridden) hold `object_ref` or `media_kind` is refused before anything is written, with a typed error
   whose words name the entity type and the property only (never the file's dataset, reference or marking). Other entity
   types are unchanged. Say whether any other property is engine-only in the same way (read the ontology); **list, do not
   add.**
3. **Each accept route** (the four above) answers the refusal the same way (one status and code); a test per route.

## The table of cases (each red first on main, the planted fault at the real call site; rule 15)

| # | Case | Expected | Red with |
| --- | --- | --- | --- |
| 1 | `properties_override` sets `object_ref` on a Document candidate | refused; nothing written | today's merge |
| 2 | The model's own extracted properties hold `object_ref` on a Document | refused; nothing written | the check reading the override alone |
| 3 | `media_kind` the same way | refused | a check of `object_ref` alone |
| 4 | Another entity type's override | accepted as today | the check applied to every type |
| 5 | Each of the four accept routes | the same refusal | the check in one route only |
| 6 | Refusal words | the type and property only | the reference or a dataset in the words |

## Acceptance test

`OspreyFlow_Build/tests/services/api/test_accept_never_sets_document_object_ref.py` (new, pure; red on main).

## Checks

The acceptance test; the existing extraction and review tests the builder names at the start (pure only); `ruff check .`;
`mypy packages services harness`. Store-backed accept paths are judged by the server and the merge's live step.

## Out of scope

The recipe rules (SE9e); the media store's addressing; the extraction profile's entity types (Document stays allowed:
only the two properties are refused).

## Round 2 (the conductor, 26 November 2026, 20:58 UTC): the merge gate's refusal

The merge gate refused round 1's tip `04f7793` on another slice's test, `tests/glass_trees/test_govuk_pack_trends_scenario.py`
(GR4a's): `citation_diff_problems` reads `process/lanes/v062/away/GR4a_ADR152_DECISION10_CITATION.diff`, which cites
`services/api/app.py:19895` and others by line, and your `app.py` change moved those lines ("app.py:19895 does not hold
'/packs/{pack_id}/items"'"). **This round: correct only the line numbers in that diff's citations to where the same cited
text now stands on your merge result** (nothing else in the diff, no test, no other file), and keep round 1's work as it
is. Then the pack-trends scenario test is green on the merge result, and your frozen checks are green.

## Round 3 (the conductor, 27 November 2026, 00:34 UTC): the plant that names the old line

Round 2's diff is right (`app.py:19905` holds the add-item route on the merge result). The merge gate refused tip
`a0a3092` on one case of the same test: `test_the_check_fails_for_each_planted_fault[a cited route line that drifted
(the add-item route as it was before main moved)]`, "the plant's anchor 'services/api/app.py:19895' is not in
citation_diff" (1 failed, 51 passed). The plant at `tests/glass_trees/test_govuk_pack_trends_scenario.py:562` replaces
`services/api/app.py:19895` with `19861`, and the diff no longer holds 19895. **This round: change that plant's anchor
(its first string) from `services/api/app.py:19895` to `services/api/app.py:19905`, the line your diff now cites, and
check no other plant in that file names a line your round 2 changed.** Keep the drifted line `19861` and its expected
words, provided 19861 still does not hold the route. Change nothing else. The test file is green on your merge result (52
passed), the plant is still red when the check is weakened, and your frozen checks are green.
