# The assessments access finding, tested (25 November 2026, D246 away round)

**Proven.** A case's gaps and assumptions routes send a reader ids of linked items that reader may not see:
- `GET .../gaps` sends a SECRET node's id to an OFFICIAL reader.
- `GET .../assumptions` sends that reader the id of a judgement that `GET .../judgements` hides from them in full (ADR-046).
- Neither save checks its links, unlike a judgement's citations.

Each case is red for the reason claimed, and seven control tests stay green. **No product code was changed and nothing was
fixed.** Whether, and how, to fix it is the owner's (the finding's questions 1 to 4 stand as written).

Branch `away/access-assessments`, from `origin/main` (`6d821f405`); the test commit is `73db76f11`. Not pushed, not merged.
Synthetic data only. Run through `~/osprey-d246/d246_ns.sh` from `OspreyFlow_Core`. Before switching, `away/GR4a` was
confirmed fully committed (clean tree; last commit `886366fb2`).

## How it was tested, and why not as the finding sketched

The finding's own tests use real ArcadeDB and Postgres (`tests/services/api/test_assessment_routes.py`'s
`with TestClient(app)` lifespan). This machine has neither, and no `initdb` or Java, and D246 runs no container, so those
tests cannot run here. The new file instead runs **the product's own code in process**: the real routes, the real
`IntelligenceGapStore`, `AssumptionStore` and `JudgementStore` classes, and the real `list_visible_judgements` and
`judgement_visible_to`. The stores and graph are supplied through `dependency_overrides`, the same pattern as
`tests/services/api/test_suggest_route.py`.

Two stand-ins replace the absent services. Each refuses what it does not model (rule 15):

- **`_PinnedPool`**, in place of asyncpg. It accepts only the stores' own `INSERT` statements (reading the columns from the
  statement itself) and the one list query each store sends:
  `SELECT * FROM <table> WHERE investigation_id = $1 AND owning_unit = $2 ORDER BY created_at`. Any other SQL raises.
  `test_the_pinned_pool_refuses_a_query_it_does_not_model` shows a query with an added visibility clause refused. So if a
  store gains a filter, these tests error rather than answer as if it had not.
- **`_ClearanceGraph`**, in place of `GraphPort.get_node`. It returns `None` for a node above the principal's clearance and
  for an unknown id. That is the shape the real port gives, which `_unverifiable_citations` and `judgement_visible_to` rely on.

The world: one case and one unit. Two analysts in that unit: `SECRET_EDITOR` (cleared SECRET) and `OFFICIAL_READER`
(cleared OFFICIAL). Two nodes: `node-visible-official` (OFFICIAL) and `node-hidden-secret` (SECRET).

**What the stand-in does not model:** the real graph's handling-code and owning-unit rules beside clearance. The hidden
node differs from the visible one by classification alone, which is the case ADR-046's existing route test uses. A real-store
run of the finding's own two tests, under the stack lease on a machine with the stores, would close that last step. It was
not possible here.

## The tests and their output

File: `OspreyFlow_Build/tests/services/api/test_assessment_links_access.py`. Result: **4 failed, 7 passed** (twice, the same).

| Test | Result | What it shows |
| --- | --- | --- |
| `test_a_gap_never_names_to_its_reader_a_node_they_may_not_see` | **FAILED** (finding 1 proven) | The OFFICIAL reader's `GET .../gaps` body holds `"linked_entities": ["node-visible-official", "node-hidden-secret"]` |
| `test_an_assumption_never_names_to_its_reader_a_judgement_hidden_from_them` | **FAILED** (finding 2 proven) | The judgement is first shown hidden in full from the OFFICIAL reader; their `GET .../assumptions` still holds its id in `linked_judgements` |
| `test_a_gap_cannot_link_a_node_its_saver_cannot_confirm` | **FAILED** (finding 3 proven) | The OFFICIAL analyst saves a gap linking the SECRET node: 201, stored |
| `test_an_assumption_cannot_link_a_judgement_its_saver_cannot_see` | **FAILED** (finding 3 proven) | The OFFICIAL analyst saves an assumption linking a judgement hidden from them: 201, stored |
| `test_a_gap_names_to_its_reader_a_node_they_may_see` | passed (control) | The visible link does reach the lower reader: the red above is the hidden id, not an empty answer |
| `test_an_assumption_names_to_its_reader_a_judgement_they_may_see` | passed (control) | A visible judgement stays linked |
| `test_the_graph_stand_in_hides_the_secret_node_from_the_official_reader` | passed (precondition) | The real judgements route hides the judgement from the OFFICIAL reader and shows it to the SECRET editor |
| `test_a_judgement_cannot_cite_a_node_its_saver_cannot_confirm` | passed (control) | The existing write rule the two write tests are measured against holds in this world (422 `unverifiable_citation`) |
| `test_the_pinned_pool_refuses_a_query_it_does_not_model` | passed (stand-in) | A list query with any other clause is refused |
| `test_the_real_list_queries_are_the_ones_the_pool_models` | passed (stand-in) | The SQL the routes sent was exactly two INSERTs and the two pinned list queries. The graph was **never asked** about a gap's or an assumption's links on either read: no visibility step ran |
| `test_the_graph_stand_in_refuses_above_clearance_and_unknown_ids` | passed (stand-in) | `None` above clearance and for an unknown id |

The four failures, as pytest printed them (ids are generated per run):

```
E   AssertionError: the OFFICIAL reader was sent the SECRET node's id: [{'id': '01M89FSQWBVC9N67C6DQDKE2J4', 'investigation_id': 'case-estuary-assessments', 'question': 'Who supplied the vehicle?', 'raised_by': 'analyst-secret', 'raised_by_name': None, 'linked_entities': ['node-visible-official', 'node-hidden-secret'], 'status': 'open', 'created_at': '2026-11-25T13:54:51.915658Z'}]
E   AssertionError: the OFFICIAL reader was sent the id of a judgement hidden from them: [{'id': '01M89FSR3WQ7ST5QHPD9J95XVR', 'investigation_id': 'case-estuary-assessments', 'statement': 'The subject acted alone.', 'if_false_impact': 'The organiser judgement falls over.', 'linked_judgements': ['01M89FSR3E84H8606TYNCPJAFS'], 'created_at': '2026-11-25T13:54:52.156289Z'}]
E   AssertionError: a gap linking 'node-hidden-secret' was stored: 201 {"id":"01M89FSRB90YMNK5CAPNPR0BDZ", ... "raised_by":"analyst-official", ... "linked_entities":["node-hidden-secret"], ...}
E   AssertionError: an assumption linking '01M89FSRBVX4RE04YKPBZY858B' was stored: 201 {"id":"01M89FSRC2D8HJ9CBTHHK4W6AG", ... "linked_judgements":["01M89FSRBVX4RE04YKPBZY858B"], ...}
4 failed, 7 passed, 2 warnings in 4.55s
```

The second write test's second id (`judgement-that-does-not-exist`) is not reached: the first link already stores. The gap
test's unknown id (`node-that-does-not-exist`) is likewise not reached.

Also run: `ruff check --ignore E501` on the file (clean); `make test-file-coverage-check` (1291 test files, no new drift).

## The exact lines (at `73db76f11`; the product code is unchanged from `origin/main`)

**The read side: no visibility step on either list.**
- `OspreyFlow_Core/services/api/app.py:8804` `list_gaps_route`. Line 8810: `gaps = await gaps_store.list_for_investigation(investigation.id, principal)`. Line 8813 returns each gap whole, adding only `raised_by_name`.
- `OspreyFlow_Core/services/api/app.py:8850` `list_assumptions_route`. Line 8856: `assumptions=await assumptions_store.list_for_investigation(investigation.id, principal)`, returned whole.
- `OspreyFlow_Core/services/api/assessments.py:365` (gaps) and `:422` (assumptions). The stores select `WHERE investigation_id = $1 AND owning_unit = $2`: case and unit only.
- `OspreyFlow_Core/services/api/assessments.py:177` `linked_entities=list(row["linked_entities"])` and `:189` `linked_judgements=list(row["linked_judgements"])`. The stored links are returned as stored.
- For comparison, the judgements route's step: `OspreyFlow_Core/services/api/assessments.py:544`, `if not await judgement_visible_to(judgement, principal, graph):`, inside `list_visible_judgements`.

**The write side: links stored unchecked.**
- `OspreyFlow_Core/services/api/app.py:8775` `save_gap_route`. Line 8786: `linked_entities=body.linked_entities`. Then `new_gap` at `OspreyFlow_Core/services/api/assessments.py:626` (`linked_entities=linked_entities or []`) stores them.
- `OspreyFlow_Core/services/api/app.py:8822` `save_assumption_route`. Line 8833: `linked_judgements=body.linked_judgements`. Then `new_assumption` at `OspreyFlow_Core/services/api/assessments.py:647`.
- For comparison, a judgement's check: `OspreyFlow_Core/services/api/assessments.py:223`, `unverifiable = await _unverifiable_citations(graph, principal, judgement.supporting)` in `JudgementStore.save`.

**The models:** `OspreyFlow_Core/packages/schemas/domain.py:2074` (`IntelligenceGap.linked_entities: list[NodeId]`) and `:2086`
(`Assumption.linked_judgements: list[JudgementId]`).

## For the owner

- The four red tests are committed red on purpose, as asked ("red first, do not fix"). They will fail any CI run that
  includes them until the owner rules and a fix lands, or until they are marked to pin today's behaviour if the ruling is
  "not a fault". The owner may prefer them held off `main` until then.
- The finding's questions 1 to 4 (is it a fault; drop the hidden links or hide in full; where; the write side) are
  unchanged. Their tests are now these, observed red rather than predicted.
- Nothing here tests the Glass. How the React panel draws `linked_entities` was not read, as in the finding.
