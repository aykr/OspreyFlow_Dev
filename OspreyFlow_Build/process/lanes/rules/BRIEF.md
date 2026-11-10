# Rules lane · brief UPG · rehearse the v0.4.12 → v0.5.0 upgrade on the test server, before the publish

Written by the orchestrator, 10 November 2026 evening, for the rules session, **from main** (075e240 or later).
Docs found that `ospreyflow update` runs none of the six one-off migrations an existing v0.4.12 deployment needs, and
nobody has run them on a real v0.4.12 deployment. Tonight's v0.5.0 publish waits for this rehearsal. Size S–M.

**The rule for this step.** On ospreyflow-test only, a throwaway named deployment, **project and volumes prefixed
`osprey-upg-`**, synthetic data only. Never touch `osprey-small`, `osprey-test-*`, `osprey-p7-*`, the leased stacks, or
another lane's images; no `docker image prune`; every `down -v` guarded on the project name (P5b's driver,
`process/lanes/platform-b/gates/p5b_live_update.py`, shows the guards: reuse them); before/after container and
volume lists recorded, failing on what the run itself left. Tear it all down at the end. It counts as one live slot;
tell the orchestrator when it is up and down.

**Do:**
1. Install **v0.4.12** (the commit tagged `v0.4.12` in the user repository, 964a2a9 on main's history) as the named
   deployment `osprey-upg`, through its own `ospreyflow install`, and load a synthetic demo pack (fixture-corp or the
   prison pack) so there are cases, boards and rules to migrate.
2. Update it to **main's head** through `ospreyflow update` as a user would, then run the six one-off migrations in
   the order docs' CHANGELOG v0.5.0 section states, **each with `--dry-run` first**, through
   `docker exec osprey-upg-api-1 python -m scripts.<name>`: migrate_cases_to_one_dataset, migrate_branches_to_views,
   seed_target_models, make_home_cases, migrate_sources, remark_alert_nodes.
3. Check the result: sign-in, Home, a case opens with its views and boards, the alert queue, the Studio's pipelines
   and Runs, Admin's System; and each migration re-run is a no-op.
4. Record every command, its output (masked), the order that worked, and anything that failed, in
   `process/lanes/rules/gates/upg-rehearsal.txt`; tell the orchestrator and docs the exact steps, so the CHANGELOG's
   upgrade section says only what was proven.

**Not in this step:** making `ospreyflow update` run the migrations itself (code; a carry for tomorrow, recorded).

**Exit.** The upgrade rehearsed end to end with every step recorded; the CHANGELOG's steps confirmed or corrected.
