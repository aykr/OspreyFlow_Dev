# v0.5.2 step 4: the record (platform's)

Step 4 measures search on B's load (ADR-149 Amendment 2) on stack d. This file is its record: who ran it, under
whose lease, against what, and what was found. The figures go in `RESULTS.md` (made by `results_table.py` from the
live gate's results); this file says how they were taken.

## The arrangement (the orchestrator's rulings, 14 November 2026)

- **The lease is rules'.** `stack_lease.sh` has no hand-over and a release brings the stack down, so rules runs
  step 4 from its own worktree with `stack_lease.sh remote rules -- …`; platform reads the results with rules and
  owns this record and `RESULTS.md`. The QUEUE line reads "rules step 4 (run by rules from its worktree, platform
  reading)". A figure in this record is a measurement under rules' lease of d, never under platform's (rule 14).
- **The query set is rules'.** B's generator, its ids and its fields are rules', so rules wrote
  `scripts/client_size_queries.py` (red first), and platform reviewed it against the runner before it was used.
- **The command list** is the one platform sent rules on 14 November: the QUEUE and `pgrep -x make` check; the
  ports; the runner (`step4_stack.py --case 01M7C2SXAPP3RF8QRSR2SKEMJK`) around the live gate for M1, M3–M6 and M10's
  leak cases (6 cases expected to pass); the never-join pass; M9 alone, only with rules' agreement at that moment
  (its time recorded below); `results_table.py`; the results to platform; the QUEUE line deleted. M2, M7, M8 and M11
  are not measured by this run; their rows say where.

## The query set, as reviewed

`~/osprey-load/step4/queries.jsonl` on d's host, made by `python -m scripts.client_size_queries` from B's files
(`~/osprey-load/b-1.0`), merged as `d71189c`. 800 rows, 200 a class, seed 4; `counts.json` beside it holds the seed,
the counts, the eligible records per class and B's manifest's sha256.

**First review, at 95093c0** (against `scripts/measure_search.py` and `tests/perf/test_search_budget_live.py`):
- Fields: `class`, `query`, and `expect_first` or `filters` as the class needs; the rows' `from` and `change` are
  read by nothing in the runner. Every query within `MAX_QUERY_CHARS` (200); suggestions 2 to 6 characters, within
  `SUGGEST_MIN_CHARS` (2).
- M4's `filters` name the case's own dataset, `cs-intel` (the loader registers `SeedDataset(id=source.dataset)`), so
  the route does not refuse them (422); each row's date bracket holds its document's `sent_at`.
- M5: Endpoint's identifiers are `[e164, …]`; a query written as `value_raw` reaches the identifier band through
  `search_alternative` (a number read as msisdn asked for in its canonical e164 too), and one written as e164 matches
  directly. A number is used only where it is the one visible record holding it, keyed by both its written form
  and its e164, so two records sharing a canonical number are both left out, as the search matches on the canonical
  form. A document naming the number ranks in a mention band, below the identifier band: one ranked first is a
  finding, not an artefact of the set.
- Visibility: `may_read` as m10-measure (OFFICIAL-SENSITIVE, codes P and C, unit-intel, the dataset `cs-intel`) at
  build and again in `check_queries`; full text only from the OFFICIAL-SENSITIVE documents (27,874 eligible, the 70%).
- Counts: 200 a class, so the runner's 200 sends after 20 discarded never repeat a query; M9's first 5 names and
  suggestion rows are there.
- Red first: Q1 to Q7 each red alone (a row the principal cannot read; an exact row's `expect_first` not compared; a
  number two visible records hold; the date filter not checked; too few rows; rows drawn from records the principal
  cannot see; the name changes not taken in turn), 16 tests green before and after.
- The one point raised: M3's "variant" as first built was the register form (the family name first and in capitals),
  which exercises word order and case, close to an exact name, not the spelling variants PLAN means.

**Re-review, at 41f4835** (the orchestrator ruled for B's own alternatives):
- `_variant` draws another spelling of the same name from its own group in `client_size_plan.FORENAME_GROUPS` or
  `SURNAME_GROUPS` (for example "Steven Morlow" for Stephen Morlow), as B's generator spells other records of the
  same person; an alternative differing only in case is excluded; a name with none comes back unchanged, and
  `check_queries` refuses an unchanged name. A case-only or order-only change is refused (rules' plants Q8 and Q9).
- So M3's variants are B's own spelling alternatives, never register-order forms; its 200 rows are 67 slips, 67
  sound-alikes and 66 variants. The rebuilt file's sha256 is f564f75f…fea0a7; the suggestion, full-text and exact rows
  are unchanged from the first build.

## The run

**A first run stopped before anything was timed, and the deviation it caused.** Run 20261114T142042Z-90e982c3,
started by rules at the repository root as the command list said, stopped at 14:21Z after "step4: the realm is up
with its subjects", with "step4: docker build failed: ERROR: failed to build: resolve : lstat services: no such
file or directory". The runner gave docker `-f services/api/Dockerfile`, which docker reads from the process's own
directory, not from the build context (`OspreyFlow_Core`); on stack f the runner had been started from
`OspreyFlow_Core`, so the gap never showed. Nothing was left on d (no step4 containers; the stores up). Rules
reran with the runner started from `OspreyFlow_Core` and the inner pytest line less its own `cd OspreyFlow_Core`,
the one change from the list: every other path in the runner goes through `ROOT`, `CORE` or `FIXTURES`, so the
run is otherwise as listed. Platform fixed the runner on this branch (9464862: `build_argv` gives docker
`CORE / dockerfile`; red first, plant 14 in `plants_step4.py`, 14/14 red), so a later run starts from either.

**Step 2's first full run is void, all but M5.** Run 20261114T142209Z-ac9b7665, 14:22–14:30Z, at 41f4835 from
`OspreyFlow_Core`, ended "5 failed, 1 passed". The runner minted every token once, before the command, and the
realm (the deployment's own rendered local-lite realm) set no `accessTokenLifespan`, so Keycloak's 300 s applied:
every send from about five minutes in was refused with 401. M5 ran first (192 s, every send inside the life) and is
a result: n=200, p50 860 ms, p95 939 ms, p99 997 ms, max 1,018 ms, against 1,000 ms and a fail of 2,000 ms, met. The
rest is void and is not a measurement of search: M4 (33 of 200 refused), M3 and M1 (200 of 200 refused), M6 ("no
board to draw on (HTTP Error 401)"), and M10 (all 500 cases reported as "does not name …", because `measure_leaks`
hid a failed control's error behind the hidden ids it listed). The void files are kept by rules in
`results-expired-20261114T142209Z` (M5.json, met, among them). Why the runner let it report as finished: a 401 was
timed as one more error. Fixed at 69bde7c, a02ac54 and 8ba5ed6 (red first, `plants_tokens.py` 6/6 red): the realm
grants four hours; the runner refuses to start (exit 2) when the IdP grants any token less than the run's hour,
reading `exp - iat` from what was granted; a 401 ends the live gate's whole session saying its figures are void
(`TokenRefused`, `pytest.exit`); M10 shows a failed control's own error.

**The never-join pass's first run is masked, not a result.** Run 20261114T143128Z-b807546c, 14:31–14:32Z, fresh
tokens, "1 failed", 500 of 500 cases: 475 (control m10-cleared-unit-fiu, partners cs-calls, cs-nominals,
cs-companies) "the cleared principal's answer does not name [the hidden id]", and 25 (control
m10-cleared-unit-covert, partner cs-covert) the control naming its record and m10-part's own search in the measured
case answered "HTTP Error 404: Not Found". The first group's cause was hidden by the masking defect above: either the
control's request erred, or the index's access filter refuses an OFFICIAL-SENSITIVE/C record of another unit that
`principal_may_read` allows (rule 3: a product finding). A 404 on the route is never counted as "hidden, not seen":
the request never reached the filtered search. Kept by rules in `results-never-join-masked-20261114T143128Z`;
rerun on the fixed runner.

**M9 is a result, not met.** Run 20261114T143515Z-d6be4f56, 14:35–14:37Z, fresh tokens. Rules agreed to it at
14:34:41Z, with d rules' alone. With OpenSearch (`osprey-test-d-opensearch`) stopped, the five name searches answered
from the fallback in 5,507, 5,543, 5,428, 5,301 and 5,404 ms, against the 5,000 ms fail: at client size the
fallback is slower than the bar's figure. The five suggestions took 1,098–1,483 ms (within 2 s), and the index was
back in 14.5 s (within 120 s), with 642,460 documents as before. Results in `results-m9`.

**Step 2, the measured run: M1, M3, M4, M5 and M6 met.** Run 20261114T143856Z-516ef319, 14:38:56–14:52Z, at
8ba5ed6 under rules' lease of d (held since 03:27:42Z), from `OspreyFlow_Core`; "1 failed, 5 passed, 1 deselected
in 678.60s", no token refused. Rules' SSH dropped at 14:47Z and the run was followed to its end with `remote-log`
(its whole log: `osprey-runs/rules.meta/runs/20261114T143856Z-516ef319/log`). `RESULTS.md` built by rules with
`--commit 8ba5ed6d0ed7…`, the JSON in `~/osprey-load/step4/results/`:

| Measure | p50 / p95 / max | Budget / fail | Result |
| --- | --- | --- | --- |
| M1 suggestions | 56.8 / 61.3 / 173.3 ms | 300 / 300 ms, any over 2 s | met |
| M3 names | 856.3 / 912.7 / 1,003.9 ms | 1 / 2 s | met |
| M4 full text | 884.5 / 957 / 1,005.6 ms | 1.5 / 3 s | met |
| M5 exact | 857.1 / 914.7 / 1,011.5 ms | 1 / 2 s | met |
| M6 lag (n 50) | 1,799 / 2,836 / 2,998 ms | 5 / 30 s | met |

The one failure is M10's leak cases, whose controls could not open the case (below). The first run's M5 (p95 939
ms) agrees with this one's (914.7 ms).

**M10 is unmeasured: the cases' design, not the product.** On the fixed runner every control's request shows its
error: "HTTP Error 404: Not Found" on the case. The Conduit opens a case only to a principal whose `org_unit` is the
case's `owning_unit` (`investigations.py` :117, :365); a grant is not enough. The intel case is unit-intel's,
companies unit-economic's, covert unit-covert's, so the unit-fiu and unit-intel-covert controls, and m10-part
(unit-records), could not open the intel case, and the cs-covert control worked only because its unit matched. So
nothing hidden was reached either way: no access divergence (rule 3 is not in question), and `measure_leaks` was
right to count a 404 as proving nothing. Rules' fix (its case design: m10-part in unit-intel, each control from its
case's owning unit, `client_size_leaks` refusing a control outside the case's unit, red first) changes
`step4_stack.SUBJECTS` to match; M10 then has one short queue turn. The never-join rerun did not start (it refused
while step 2 was still alive after the SSH drop), correctly.

**M10 with rules' new subjects: no id leaked; the words check unproven.** Leaks run 20261114T155917Z-7f9f194b,
15:59–16:16Z, then never-join, 16:16–16:29Z, under rules' lease of d, from rules-load at c7149b1 with cbb7ad9's
runner; the files regenerated (leaks eligible 10,129, 1,997 SECRET/R unit-intel-covert kept out; never-join eligible
18,115). Preflight said "m10-measure and m10-part open the case", and every leak case's control reached its record.
Both files were "not met": leaks 500 of 500 failed, every one "the hidden record's words … are in the answer";
never-join 122 of 500, 72 on words and 50 on an unreached control. No hidden id was in any of the 1,000 answers.
Rules traced every failure to the check or the cases, none to the product:
- **The query's echo** (platform's, `measure_search`): `SearchPageResponse` echoes `query`, and every string of the
  answer was read, so each leak case, which asks its hidden document's own title as its `never_text`, failed on its
  own echo, as did 7 cs-companies never-join cases. The fake Conduit had no echo, which is why the tests let it by
  (rule 15: a fake models what the real one returns). Fixed at 4a836d9: the echo is left out only where it equals the
  query sent, and the fake echoes as the real page does.
- **Words visible records hold** (rules', `client_size_leaks`): 47 cs-calls, 16 cs-nominals and 2 cs-covert cases
  whose `never_text` is in a visible record's own text. Rules' fix: drop such a word, case-folded, as a substring.
- **Unreached controls** (50 never-join cases): the visible spelling as the query does not bring the partner onto the
  control's page 1. The orchestrator ruled: reported apart as indeterminate, never a pass and never a leak, and a file
  is measured only if at least 90% of its controls reach their record, else unmeasured. Built at 4a836d9
  (`REACHED_AT_LEAST`; the live gate and `RESULTS.md` say how many reached); ADR-149 Amendment 2 says so.
Red first: on cbb7ad9's `measure_search` the new and changed tests are 8 failed, 43 passed; at 4a836d9 test_measure_search,
test_step4_dry_run and test_step4_stack are 80 passed, 2 skipped; `plants_m10.py` 7/7 red, `plants_step4.py` 16/16,
`plants_tokens.py` 6/6 (its sixth re-anchored on the control-error line). M10 runs again in a later turn (about 30
minutes) once rules' word fix is in.

**M9's profile: the unlabelled `or()` over the whole store dominates.** `profile_m9.py`, read-only, on d under rules'
lease after M10's runs, repeat 3, the five M9 names; rules' QUEUE line deleted after. At cbb7ad9:
`osprey-runs/rules.meta/runs/20261114T162936Z-90a75f73/log` (16:29–16:43Z); at 6208ee7, with `by_sql`:
`…/20261114T164402Z-8bb511ed/log` (16:44–16:57Z). 1,180 indexes. Medians per name (figures from rules' report of
the two logs):

| Variant | cbb7ad9 | 6208ee7 |
| --- | --- | --- |
| `current` (the query as sent) | 5.48–5.71 s | 5.39–5.47 s |
| `limit_20` | 5.41–5.93 s | 5.37–5.48 s |
| `no_access` | 21.3–23.1 s | 21.2–21.6 s |
| `count` (the `or()` alone) | 21.2–22.9 s | 21.2–21.4 s |
| `by_label` | 4–12 ms | 3–4 ms |
| `by_sql` | — | 67–70 ms |

What it shows: the limit is not the cost (`limit_20` as `current`), and building rows is not (`count` is slower
still). The matching is: an `or()` across every field with no start set reads every vertex; `current` is quicker
than `no_access` and `count` only because the access filter's own steps narrow first. A labelled `has()` on an
indexed field is answered from the index on 26.10.1 (`by_label`), which corrects platform's reading of ADR-124
Amendment 18's note (3.6 s at 200k), which was of `within()` and unlabelled lookups. So M9's slowness is the family of
am18's write path and am20's `edges_among`, a Gremlin read that starts from the whole store, and the fix is to start
from index-found records. Rules builds it as ADR-124 Amendment 21 in the `by_sql` shape (SQL per type and field, then
`search_nodes`' own Gremlin from the record ids, the gazetteer guard and the access filter in the traversal), which
the orchestrator ruled and am18 and am20 use. Every variant answered 0 rows for all five names (M9's queries are the
fallback's misspellings, which match nothing exactly), so the "same ids" lines show nothing; Am 21's equivalence rests
on the conformance suite's search and access cases, unchanged, and a live case on d of matching queries (a family
name, an e164, an organisation, a gazetteer place by name and by identifier) comparing the new query with the old.

**M9 with ADR-124 Amendment 21: met.** Run 20261114T203513Z-a7331cae, 20:35–20:37Z, under rules' lease, the runner
at the poc's limits ('2', '4g'), with Amendment 21 from `lane/rules-adr124-am21` (not yet on main). With OpenSearch
stopped mid-session the five name searches answered from the fallback in 92–105 ms (5.3–5.5 s before), the
suggestions within 1,490 ms and the index was back in 9.2 s; `results-m9-am21/`. Rules' equivalence run before it
(20261114T180041Z-adaf17fe) compared the old query and the new on d: 1,200 of 1,200 the same (old p50 7,278 ms, new
76 ms).

**M10's second turn: met.** Rules regenerated the files (run 20261114T205357Z-b5d8989c, 20:53Z), dropping each hidden
word the case's own query or a visible record holds (73,191 in the leaks file, 90 in never-join; every leak case still
checks at least one word), as `rules-m10-query`, merged as 55a44d5. Then, with this branch's runner (the echo left
out, the 90% floor):
- never-join, run 20261114T204635Z-869d5050, 20:46–20:48Z: 500 cases, 450 controls reached (90%, the floor), 0
  failures, 50 indeterminate; met. `results-m10-never-join-2/`.
- leaks, run 20261114T205703Z-af53b1e6, 20:57–21:01Z: 500 cases, 500 reached, 0 failures; met.
  `results-m10-leaks-3/`. The run before the regenerated files (20261114T204142Z-229690b0, `results-m10-leaks-2/`)
  failed all 500 on whole document titles that the case's own query holds, and is set aside.
- the words check's positive control, run 20261114T210353Z-80a82366: a planted hidden word in the answer found in 5
  of 5. A caveat for the record: the hidden record's `sent_at` surfaces only at `.nodes[].properties`, which
  `_answer_strings` reads (every string at any depth), so it is checked; a check reading only the results would miss
  it.
So no hidden id, count or word reached m10-part in 1,000 cases, with the check shown to fire. Step 4 closes with M1,
M3 to M6, M9 (with Amendment 21) and M10 met; M2, M7, M8 and M11 measured elsewhere, as their rows say (`RESULTS.md`).

**A search page's time (the owner's question).** Step 4's M3 to M5 took about 860 ms p50 against M1's 57 ms. Profiled
by `profile_page.py` at a28f93e (run 20261114T210234Z-ea50964d, 21:02–21:03Z, run tree 496e714: main 8347d28 with
this branch and rules-m10-query, Amendment 21 not in it): one query of each kind, 2 discarded and 10 timed, each
sent alone and the same query repeated:

| Over the wire | median ms |
| --- | --- |
| `/healthz` | 0.8 |
| names ('Tomasz Kellly') | 93.9 |
| full text ('in a dark blue estate') | 126.8 |
| exact ('+447700000945') | 101.8 |
| suggest ('Ashham') | 56.5 |

In process, at the case's threshold (0.95): names 86 ms, full text 114 ms, exact 88 ms in all; `get_nodes` about 39 ms
and the merge's `edges_among` about 38 ms, each 18 per-type SQL lookups overlapping (some 330 ms summed, 38 ms wall)
and the store's list of types about 5 ms a read; OpenSearch 8–35 ms (its own `took` 6–33 ms); building the results,
the body, the access filter and serialisation under 2 ms together. So a page measured now has no fixed 0.8 s. The
step 4 run tree (8ba5ed6, on main e684ef1) predates ADR-124 Amendment 20 (3c96ba7), whose `edges_among` started
from every vertex in the store (`g.V().has("id",within(…))`), and a search page with two or more hits calls it to
merge them while a suggestion never does; that is the leading account of the gap, to be shown by measurement, not
assumed (the orchestrator's ask: the same 200 exact sends, under the runner's limits and without them).
