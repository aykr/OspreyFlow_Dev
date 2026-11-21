# BL2's run sheet: the 16 rows that need a run or a definition (the owner's word of 21 November 2026, file 008)

The 16 rows the judging of 18 November marked "cannot tell, needs a run" (three more were dropped under D17 and D18). Their text is in `OPEN_BACKLOG_PLACED_2026-11-19.tsv`; the split below is read from each row's own words, **by the conductor from the placed table, and has not been run**: a row marked "this Mac" may turn out to need more than a stack.

**C023 is not here.** It stays set aside with the demo items, to be settled with PL5 (the owner, file 008 item 3). It holds neither BL2 nor CO1.
**L08 is not here as a run.** It stays folded into IS6 (ruling D16).

## The run-sheet row (one row, one seat)

| Run-sheet id | What | Seat | When | Rows |
| --- | --- | --- | --- | --- |
| **RS1** | One leased run on this Mac's test stack (`OspreyFlow_Build/scripts/stack_lease.sh`, rule 14; the lease is recorded with every measurement), in the order below, each row's result written into the placed table's disposition (closed, a fault with its build, or still unknowable and why). | **A seat**: it starts only when **no merge is in its gate and the PL4 chain has no seat waiting**; **not tonight if the slot stays busy.** | After PL4's chain is clear; first with CO1's two rows, which are CO1's own first step. | C043, C068 (CO1's); C190, C153, C022; C076, C080; C235 (the last three are "Later", D19) |

Order and the run each needs, from the row's own text:

| Order | Row | Part | The run |
| --- | --- | --- | --- |
| 1 | C043 | Ingest Studio (CO1) | The seven failing live ingest tests on main (the studio-load and run-now case-dataset stamping tests, `SourceUnreadableError`): run them on a leased stack and record which still fail and why. |
| 2 | C068 | Ingest Studio (CO1) | The slow seed's two failures (the rehearsal reset's `SourceUnreadableError` in `studio_profile`): run the slow seed on a leased stack. |
| 3 | C190 | Build line | `tests/scenarios/test_phase8_exit_criterion_end_to_end.py` on stack c: the B4 seed of four first-cohort Person nodes returns the wrong count at main; rerun and record. |
| 4 | C153 | Platform | `tests/harness/test_organisation_sign_in.py`: the throwaway Keycloak is not ready under a full `make test` load (12 setup errors; 12 of 12 pass alone). Run it alone and under load; the answer decides whether it is a readiness wait or a load flake. |
| 5 | C022 | Build line | `tests/test_lanes_heartbeat.py::test_shows_run_at_once_do_not_mix_their_lines` drops a Needs-you line under heavy load: run it alone and under load. |
| 6 | C076 | Rules and Monitoring (Later, D19) | A pattern rule or AML/KYC template made case-wide: a draft in the declared dataset with its own Test per typology, then Make live. |
| 7 | C080 | Rules and Monitoring (Later, D19) | L2.11's carries: the template-to-draft path, the composite list-id ambiguity, `test_kyc_rules`' order dependence. |
| 8 | C235 | Vault (Later, D19) | ADR-124 Amendment 20's high-degree case: `edges_among` reads every visible out-link of each start in a chunk and narrows the far end afterwards; build a synthetic high-degree graph and measure. |

## Needing a definition or the owner's environment, not a run on this Mac (listed separately, with the question)

| Row | What the row needs | The question for the owner |
| --- | --- | --- |
| C150 | `tests/harness/test_render_memory.py::test_opensearch_starts_with_the_rendered_heap_and_is_killed_by_one_beyond_its_memory` fails "on the test server" | Is the test server (your second machine) the place for this run, and may a seat be started there, or does it wait for you? |
| C131 | L1.9 part 2: SeaweedFS ignores regions; real S3's `PermanentRedirect` and `AuthorizationHeaderMalformed` are unmodelled; Athena's FAILED versus other states: the fixture against real S3 | A real S3 bucket is outside this Mac: do you run it, give me an account to run against, or leave it parked until the client's platform exists? |
| C151 | P12 part 2's exit: a leased live case of Laurium reading a conforming answer from the client's own engine; until it passes Laurium is "not proven" | The client's engine is not reachable from here: park until you have it, or define a stand-in? |
| C161 | Whether EKS's IRSA webhook makes the API token unnecessary for api, worker, report-sync, litellm and the backup pods | Needs an EKS cluster: park until the client's platform exists? |
| C167 | On the client's platform, with Athena and a bucket in another region: `test_athena_connector_live.py` | Same: client's platform. |
| C172 | P9b: restore-graph's check (`CheckDatabase.java`) timed and its memory measured on a real-sized graph, on the client's install | Same: client's install. |
| C178 | The live measurement against the client's development tenant (Amendment 6's list, and a v1.0 token's `aud`) | Same: the client's tenant. |

**Recommendation for the seven: leave them in the backlog as "needs the client's environment", all marked Later (D19) already but C150 and C131 which are "in build"; move C150 and C131 to Later as well unless you say otherwise, since no build can close them without an environment this line does not have.** (A move of two placements is yours to confirm.)
