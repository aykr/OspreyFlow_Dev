# Case lane · L3.1 · report (7 November 2026, after the final review, the branch ruling and the rule-14 breach)

**Phase 5's exit moved to L3.1b, by the owner's ruling.** The target-model half (`TargetModel`, reference lists, ADR-126 derived, the domain-model node) is L3.1b's. Writing into a composite is a later step of its own. Below is what L3.1 meets.

## What L3.1 meets

1. **Read set** (ADR-143): each case reads its one dataset, or one composite, plus its own analyst layer. No list offers the layer. Tests: `conformance/graph_port/test_analyst_layer.py`, `services/api/test_analyst_layer{,_store}.py`.
2. **Analyst writes into the layer** (ADR-143 A1): marks and manual links go in, in any case, a composite case included. The writer makes the layer after the level check.
3. **Branches hold no layer** (ADR-144 A1 decision 2, the owner's "no branches anywhere"):
   - A branch reads its original case's layer, read-only. Every write into that layer is refused (409 `branch_layer_read_only`) at three points: `analyst_writes_into`, the stamping graph's last word, and the store.
   - A case opened from an alert keeps an empty layer of its own (the orchestrator's choice, (c)). `copy_case` is split by caller.
   - Existing cases with `branched_from` keep an empty layer: a branch can't be told from an alert jump (the orchestrator's choice, (a)). ADR-143 A1 records this as a temporary exception for cases made before L3.1 only.
   - Tests: `test_branch_layer.py`, `test_analyst_layer{,_store}.py` and `test_migrate_cases_to_one_dataset.py`. Each is red with the other behaviour swapped in.
4. **A composite is read-only for now** (the owner's ruling; ADR-099 A14 and A15):
   - In a case reading a composite, every write is refused before anything is written (409 `composite_read_only`, "do this in a case that reads that dataset"). The only exception is a write into the case's layer. Every write naming a composite's id is refused too.
   - The composite is named only to someone who may be told dataset names.
   - The final review's fixes, each red first and each with its own companion that removes only its own check:
     - `stamp_datasets` writes nothing of a composite case's into a member and reports, in words with a count, what it left unplaced.
     - Monitors keep working, and their alerts go into the layer: a scheduled rule, a list's re-screening and the KYC sweep. They are scoped by what the case reads.
     - These are refused up front: the scheduler's `check_case` (three refusals pause the schedule); the admin schedule run, PUT and resume; the site grid; and held-rows reject.
     - Corrections' last word asks `composites_among` with no case in scope. In a composite case it refuses unless the old element is visible and wholly in the layer.
     - A true-positive close confirms only the layer's elements (approved; Amendment 15).
     - Postgres has its own `composites_among` test.
5. **The Studio's composite refusal runs after the route's own level check** (4a453a8, bff988e). Before, it depended on a viewer check of its own. That gave 16 loading routes two declared levels (`test_investigation_levels.py`, red at 19bffba). It also told a caller with only the viewer level, by name, that the case reads a composite: a 409 came ahead of the route's 403.
   - Now it depends on the very callable the route's `InvestigationEditorDep` (or `AuthorDep`, for held rows) uses. FastAPI runs it once per request.
   - This is narrower, not wider:
     - each route already declared editor or author itself, so no route gains a level;
     - only an editor or author reaches the refusal;
     - a viewer gets the 403 and is told nothing of the composite;
     - a non-member gets the 404 as before;
     - every write still needs the route's own level and right and passes the refusal and the last word.
   - Pinned by `test_a_viewer_is_answered_403_not_told_the_case_reads_a_composite`. It is red on 19bffba's own `app.py` (409 naming "both data") and again with the old viewer dependency put back.
6. **Conflicts** (ADR-025 A1), Q2 and Q3 as ruled, egress (Postgres too), the candidate leak, the resolution run's split, the worker's bindings: met, each with a planted-red companion.

## Live figures (every one with its lease)

- **Live set**, lease `case` (taken 18:51:49Z), run 18:52:04–18:54:56Z: 133 passed, 15 failed.
  - 12 came from the re-screening fakes, which lacked `read_only_layer_of`. Fixed in 449dead.
  - 1 was the stamping test's design. Fixed in 449dead.
  - 3 in `ingest/test_kyc_rules.py` fail the same way on main's code, run under the same lease.
- **Migration rehearsal**, lease `case`, in the throwaway `case_rehearsal` Postgres and ArcadeDB databases:
  - The seed was Fixture Corp, HMP, and HMP into the Fixture case (making it a composite), plus three planted legacy cases: `legacy-both`, `legacy-notes` and `legacy-branch`.
  - The dry run at 19:01:36Z wrote nothing (hash compared).
  - The real run at 19:02:12Z reported "4 kept, 1 on a composite (0 made), 2 layers made, 0 not placed; 3 writes".
  - Per case: the Fixture case and `legacy-both` read the composite, with the read-only message. `legacy-notes` got its layer. `legacy-branch` kept an empty layer of its own and was named in the agreed words.
  - The one-per-case index was rebuilt, and `case_layer_reads` held 0 rows. A second run made 0 writes. Both databases were dropped at 20:49Z.
- **Whole suite**, lease `case`, at 19bffba, 19:02:30Z until one SIGINT at 20:48:58Z (71% reached): 163 failed, 7,399 passed, 77 skipped. The run was stopped on the orchestrator's ruling, and its short summary was kept.
  - 16 were mine: `test_investigation_levels.py`, fixed in 4a453a8 (above).
  - 119 are the ClickHouse half of the analytics conformance suite. There was no ClickHouse on 18123 then.
  - 3 are `test_kyc_rules.py`, which fails on main too (above).
  - 1 is `test_deployment_schema`'s `osprey.yaml` check. It reads this worktree's skip-worktree local `osprey.yaml`, the local file, not committed code.
  - 24 fail identically on main without the stack.
  - In the unreached 29%, four more were mine, fixed in cf6bc5a:
    - the composites route was missing from the rights table;
    - the place scan took the Studio's dataset base for a call to the composites route;
    - a review fake lacked `get_nodes`;
    - the statelessness case named no dataset.
- **The re-run under the next lease: PENDING.** It covers the 16 files, everything from `services/api/test_investigation_levels.py` on, and the 24, all with `-rf`. A throwaway ClickHouse runs on 18123 for it. Each failure shared with main is shown on main's code under the same lease; event_frequency's 30-day RANGE overflow is main's.

## The rule-14 breach (7 November, 20:49–21:40Z)

- **The cause.** After releasing the lease at 20:49:43Z, I ran tests I believed were stack-free, with closed ports (5999x) exported. They weren't stack-free. My scratch runner, written under the lease at 18:12, exported `OSPREY_LANE=case` and the leased ports itself, overriding mine. When I checked that runner I filtered out lines with a password in them, and that hid the very line.
- **The runs:**
  - (a) about 20:51–20:57Z: the level test and the 16 failing files, twice;
  - (b) 21:00–21:03Z: all of `services/api`;
  - (c) about 21:05–21:12Z: four files, statelessness among them;
  - (d) the composite-schedule runs, in-memory only;
  - (e) the whole suite, 21:13:46–21:39:01Z. The orchestrator asked me to stop it, and I did with SIGINT and then a kill. Its orphan instance, pid 19630, was stopped at 21:40:30Z.
- **The guard.** It refused the test process's own connections, logging 24 refusals in (a) and 809 in (b): the lease was never held by `case`. But `test_statelessness` starts API instances as subprocesses, and they carry no guard. They reached glass's stack in (c) and (e), during glass's lease (20:54:13–21:37:20Z), and studio's stack in (e)'s tail and through 19630, during studio's lease (from 21:37:52Z). 19630 alone held 33 Postgres connections, 1 ArcadeDB and 1 Valkey. Nothing reached ClickHouse; its container came up only after (e)'s ClickHouse cases had run.
- **What it wrote.** I can't read the stack without the lease. From the code: the instances' start-up (schema bootstrap, the scheduler and workers) and a test case with a new dataset. Whatever the scheduler did while they ran can't be ruled out. The "Synthetic list" glass found at 21:21:25Z stays unattributed. It is written by tests the guard does refuse, and into `osprey`, not `ospreyflow`, so I think it isn't mine, but nothing proves it either way.
- **The rulings and fixes:**
  - A runner script never sets the lane or a leased port: `pt.sh` has neither now, and the rehearsal script is deleted. I export them by hand, under the lease.
  - Before a stack-free run, I check the run's own environment, not the script's text.
  - The orchestrator is fixing the guard, as its file. It will hand itself to every Python child, turn uvloop off under it, and guard 18123. I'll rebase before the next run.
  - The figures from (a)–(e) measure nothing of the stack. Each is re-run under my own lease after the guard lands, `test_statelessness` and the `services/api` run included.

## The lane's reviewer (lane-reviewer, on this branch before ready-to-merge)

Each finding was fixed, red first:
- a re-screening wrote into a member through a rule naming that member: monitors are now scoped by what the case reads (`scope_a_monitor`);
- a mark was derived into a member before the stamping knew its case was a composite: the stamping now places every case before it derives;
- the route census listed six routes of twenty: it now finds them by discovery (`LOADING_PREFIXES`, `NOT_BY_THE_ROUTE`).

## Commits (on main at 15de302)

fc9dea3 396f62b 7c85971 4b49e48 337285a c5c5594 6776fb9 8b391ff a5c8188 1c1e16e 9703550 94dbc2b 269d11c 50a69e7 c14565b 77cba95 46950f1 27e4239 4b23395 31ba22b f83e05d c67ca63 91364b5 ae89567 601490e f01a05c 85229b9 cb06486 98c6bee 8d080aa 9a34b24 735b7b8 83b905c 94ffe7b c385e3a 0ac4093 033e14a 7553b7b 4b97571 2a4c936 8642f84 7b88eb8 6cd3b57 8d04929 0802768 081da67 adabe54 f6bba10 c631875 ed83cf9 9e516f7 449dead 19bffba 4a453a8 cf6bc5a bff988e, and this report with the friction row.

## With the orchestrator

- `ci-wiring.patch` is the orchestrator's to land.
- The ADR reservation rows are left as on main, for the orchestrator to flip.
- The port guard's subprocess fix is the orchestrator's.

## Ratify, outside the case map

- `services/api/`: `app` (non-case parts), `alert_queue`, `datasets`, `document_content`, `document_reader`, `email_extraction`, `entity_pictures`, `kyc_sweep`, `link_changes`, `model_routing`, `questions`, `review`, `rule_evaluation`, `scheduler`, `screening_refresh`, `worker_main`, `working_set/service`.
- `services/resolve/trigger.py`.
- `scripts/`: `case_seed`, `stamp_datasets`, `migrate_cases_to_one_dataset`.
- `apps/workspace/`: `keyboard/case-datasets.spec.ts`, `keyboard/case-datasets-harness.tsx`, `a11y/every-harness.spec.ts`.
- `spec/`: 01, 02, 03, 04 and 06.
- Other phases' tests:
  - `scenarios/test_phase{3_working_set,6a_glass_surfaces,7_stage6c_watch_routes,8_exit_criterion_end_to_end,8_exit_over_the_wire}.py` and `scenarios/test_ledger_monitoring_storyline.py`;
  - `resolve/test_trigger.py`;
  - `services/api/test_{app,case_domains,change_stream,dataset_scope,datasets,datasets_store,document_reader,email_extraction,evaluation,explore_routes,add_by_identifiers_route,sources_withheld_routes,screening_refresh,place_routes,route_rights,review_routes,statelessness}.py`;
  - `working_set/test_{branch_by_filter,delta_projection,manual_resolution,manual_resolution_access_control,manual_assertion_uses_the_stores_link_id}.py`;
  - `test_{case_seed,stamp_datasets,stamp_records}.py`.
- New tests: `test_composite_schedules.py`, `test_composite_monitors.py` and `test_branch_layer.py`.

## Open minors

- **7b:** corrections' last word does not judge a node's incident links.
- **8:** a layer write that reuses a member's id would merge into it.
- The disabled *Create case* button's contrast.
- The in-memory store tolerates unregistered ids.
- An empty dataset can be left when a case fails to be made.
- Model candidates stay unit-wide.

## Hand check

Run `cd OspreyFlow_Core/apps/workspace && npx vite --port 5185`, then open `/keyboard/case-datasets-harness.html` and `?brand=govuk&choice=existing`. Run by the lane: dark, light and GOV.UK are correct; keyboard 5/5; axe 8/8.
