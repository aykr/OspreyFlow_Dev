# studio lane · report · L1.3 (phase 7a: the staging catalogue's engine; ADR-140 Amendment 11), 8 November 2026
1. **Golden files per step: met.** `tests/ingest/test_staging_golden.py` covers all six kinds, with the left Join normalised by `msisdn` and the inner one exact. Derive's seven operations are in `tests/knowledge_adapters/test_derive.py`; each golden file shows its refusals.
2. **Provenance survives a Join: met.** `test_staged_run.py::test_a_join_s_provenance_survives_to_the_link_it_makes`, red with `source_refs` dropped at the join (P1). It is also read back live from ArcadeDB (`test_staged_provenance_live.py`), red twice (L1, L2).
3. **A screening list round-trips through the catalogue: met.** `test_staging_catalogue.py`: the OFAC golden goes through staged Parquet and comes back as kind `screening`, entries equal, then serves a subscribed Lookup (P3–P5, P8).
4. **Rule 8: met.** No expression is accepted under any key (`tests/schemas/test_recipe_staging.py`, S3). Every key adapter and Derive operation is a Knowledge Adapter with golden tests (P6).
5. **Phase 7a's exit: met, offline and live.** The synthetic Visits and contacts pipeline without its expert steps (Lookup → Join → Derive → Map) runs end to end; every element names its source rows, and Test and the load reject the same rows (P7). Fixtures are in `tests/ingest/fixtures/visits_and_contacts/`. Live: lease studio, stack a, 13:12:40Z–13:13:37Z, with `stack_lease.sh up`/`down`. ArcadeDB only; the Parquet went to a temporary directory.
6. **Orchestrator's settlement, 8 November** (Q1–Q3, all (a)):
   - the schemas-only commit is `47b53df` (`cded186` before the rebase);
   - refs go in `provenance.sources`;
   - spec 09 §4/§9 and Amendment 11.
7. **Red record:** S1–S3, D0, G1–G3, P1–P8, L1–L2 in `L1.3_RED_RECORD.md`.
8. **Slip, mine:** at about 10:35, three synthetic Parquet files went to the object store on host 9000 without a lease (the import bypassed the fixture). Fixed, reported, and in the friction row.
9. **Left for L1.4 (7b):**
    - the drawers and the profiler on staged tables;
    - the Studio's run route feeding a pipeline's sources;
    - per-step counts and refs on the run report, which needs a schemas change.
10. **Recorded, not resolved:** in a staged run, a Map rejection's `row_index` is its staged-table position (Amendment 11).
11. **Green:** `make ci`'s gates pass, ruff, eslint, mypy, `tsc`, trivy fs and harness axe (34) among them. The exception is the image scans, which stopped on Docker Hub's 429 rate limit. The ingest suite fails nothing that `main`'s engine does not also fail (store-bound tests, offline). There is no screen, so no theme axe pass is due.
12. **Commits:** `47b53df` (schemas, merge first), `4ee9a4b`, `3d1c128`, `c842f7d`, `f13b832`, `099f794`, `496cea9`, `77d46c4`, `817720d`.
13. **Requests:** merge `47b53df` alone first; mark the Amendment 11 reservation written; re-run the image scans once Docker Hub allows. **Questions:** none. **Running:** nothing; no lease held.
