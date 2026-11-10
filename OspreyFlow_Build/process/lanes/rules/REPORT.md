# Rules · UPG · the v0.4.12 → v0.5.0 upgrade rehearsal (interim, 10 November 2026 ~20:00 UTC)

- **Exit: upgrade rehearsed end to end, every step recorded: PARTLY MET.** Run 1 (main 5df2a3e): v0.4.12 →
  main via the install's `harness.apply --build`, then all seven migrations dry run, run and re-run (each re-run
  writes 0), and the screens' routes checked (`gates/upg-rehearsal.txt`, `gates/upg-run1/`). `ospreyflow update`
  itself cannot target an unreleased head (signed release only): its steps were run by hand.
- **Blocking finding:** update's files step (`scripts.refresh --files-only`) leaves a v0.4.12 deployment with no
  gateway secrets, so update fails. platform-b's fix 0b45910 FAILS run 2 (`gates/upg-run2/`): the secrets take two
  passes (the salt is never written), api's `map-settings`/`model-settings` volumes are undeclared, and the old
  litellm keeps `sk-ospreyflow-dev` while the Conduit gets the new key. Run 3 (`gates/upg_run.sh`) waits for its
  next head.
- **Exit: CHANGELOG's steps confirmed or corrected: MET for the migrations** (order, dry runs, no-op re-runs,
  `migrate_rules_to_datasets` after `make_home_cases`, Rule author to assign, owners needing one); NOT for update.
- Commits: e08cb51 (tools, guards and env diff shown red), 45382f6 (record, runs 1 and 2), b1e65db (run 3 driver).

## Decisions taken
- Orchestrator socket 8906 gone, no orchestrator listed: took the one live slot, said so by heartbeat; later
  confirmed right (14277).
- Update cannot reach main's head (no release): v0.4.12 from the signed tag, the clone moved to the head's user-repo
  export, update's steps by hand; the real update owed once v0.5.0 is tagged.
- The whole-deployment rule left pending (approval needs a second admin): exercises "copied as a draft".
- Run 2 without the prison pack (run 1 covered its recipes); its list's version 2 held back for after the upgrade.
- Release-shaped images built under refresh's pinned references in place of a pull (run 3), claimed and removed.

## Requests / questions
- platform-b: the three defects above; apply/stop surviving an uninterpolable compose file; start --build on a
  release-installed deployment (both carried). The v0.4.12 2480 preflight finding is in CARRIES.
- Still running: osprey-upg on ospreyflow-test, kept up at the orchestrator's word; nothing local.
