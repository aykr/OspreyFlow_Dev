# Platform-b · P5b · backups in a folder named at setup (ADR-114 Amendments 37 and 38): report

1. **Exit, met.** Amendment 37's tests table, and Amendment 38's (decisions 1–9, written here), are green. The tables name every test: `tests/harness/test_backup.py`, `test_restore_finds_sets.py`, `test_update_apply.py`, `test_render.py`; `tests/cli/test_answers.py`, `test_install.py`, `test_doctor.py`, `test_named_deployments.py`; the guided page's `InstallScreens.test.tsx` and `keyboard/setup-screens.spec.ts`. Each was shown red by a plant at its call site (`plants.md`). Axe runs dark and light only, as the install page has no GOV.UK theme (the orchestrator's ruling).
2. **Gates, at this report's commit.** `make test` (offline, on the server) and `make -k ci` (here, closed ports) are in `gates/<sha>.{test,ci,keyboard,a11y}.txt`, with the counts and every failure explained in the ready-to-merge message. Failures the environment causes: the trivy, opentofu and chart targets need Docker, which is off here; `test_webapp_preflight` fails because the server has a GPU; `test_valkey_config` reads the closed port; `MatrixView.budget` is a timing test.
3. **Live run: not achieved, live proof owed** (the orchestrator's decision). There were three attempts on ospreyflow-test (`gates/live-attempts.txt`). The rollback's git checkout step was NOT EXERCISED. Decision 9's live proof is owed, to run once the server has a Docker Hub mirror or login (the orchestrator's carry).
4. **Incident.** Attempt 3's teardown deleted three of another lane's images, because it took a before/after difference of tags. It was reported at once. The driver now removes only the tags it recorded when it made them (`tests/test_live_driver_own_tags.py`). Friction row: `process/friction/2026-11-10-platform-b-deleted-images.md`.
5. **Reviews.** Three lane-reviewer passes and the orchestrator's independent review. Each finding was fixed red-first; they are listed in `plants.md` and Amendment 38. Among them:
   - the checkout guard took the git root, letter case and a link followed by `..`;
   - a profile's name, or the checkout's own name, would have shared a subfolder;
   - `--out-root=~`;
   - the install's own backups checks;
   - the update's settings for a named deployment;
   - a server's backups setting left out.
6. **Left, and why.**
   - Decision 7: two checkouts sharing one folder is unsupported and not yet detected.
   - The guided page passes a relative folder through.
   - The `~/OspreyFlow/backups` spelling is repeated in the CLI and TSX, pinned only on the CLI side.
   - The admin guide's text is a carry for docs: `CARRY-admin-guide-13.md`, sections 1–7, including the `NOT_YET_IN_THE_GUIDE` entry docs removes red-first.
7. **Ratify:**
   - `harness/update.py` and `harness/render.py` (runbook row, 14 lines, ratified);
   - `cli/ospreyflow/main.py` (prompt, doctor and install checks) and `deployments.py`;
   - `apps/harness` Folders and Review screens, and `setup-screens.spec.ts`;
   - `deploy/RUNBOOK.md`, `tests/test_admin_guide.py`'s exemption, and `.gitignore` (ratified).
8. **Routed.** `harness/preflight/ports.py` ignores `deployment.env`, so a named install fails wherever 2480 is held. This is platform-b's next step, before P6 (ratified). The live driver's port workaround comes out with it.
9. **No route added.** P5b adds no route, and no live file reaches one, so `test_route_rights.py` isn't required. Commits: `git log main..lane/platform-b`, in small Conventional Commits naming their files.
10. **Questions:** none. **Running:** nothing of mine, once the gates' own runs end; I'll say so when they do.
