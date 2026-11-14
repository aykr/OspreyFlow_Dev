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

(To be filled in from rules' results: each run's id, start and end, the server's state before it, the runner's lines,
pytest's summary, M9's agreement with its time, and what each figure means for v0.5.2.)
