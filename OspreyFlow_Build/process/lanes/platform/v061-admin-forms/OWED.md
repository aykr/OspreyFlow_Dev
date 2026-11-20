# v061-admin-forms: what is owed (carried from HANDOFF.md, retired 15 Nov 2026)

**Done:** the model form's first slice (ADR-135 Am 14 points 1-8), rulings 18-20 (no unchecked add; edit and new
key checked; point 9), the owner's key review and rulings 21-28 (point 10). Offline gates green at fc77f2a:
pytest 728 (fails only Postgres-live and the old rule-editor case), vitest 3615, plants 21/21 + 17/17 + P8 3/3,
keyboard 20/20 and axe 60/60 at slot 9. Records: `process/lanes/platform/v061-admin-forms/` (red-first.txt,
plants_*.py and *_run.txt, ACTION_REGISTRY.diff with 6 ids, EVERY_HARNESS.diff with 4 states).

**Owed, in order, once the orchestrator says the package test has ended** (ask it for the server queue first):
1. Q2, ruling 27: one measured run on the demo's real LiteLLM at its log level with a SYNTHETIC key; search its
   logs and the credentials row; if a credential body is logged, lower that logger in the rendered gateway
   settings, held by a test reading the rendered config.
2. `make test` and `make -k ci` on the server, including the live `test_route_rights.py` cases (Postgres).
3. A live LiteLLM run under a lease (`stack_lease.sh`): check, Add, edit with a moved address, a new key, the
   one-minute cooldown after a refusal, a duplicate credential name (the stand-in does not model its refusal).
4. Then ready-to-merge to the orchestrator; leave the branch as gated until it answers.
5. Then **Part 3, the second demo (ospreyflow.app)**, owner's ruling 16: about 28 h ±5, its own model beside Gemini,
   the shared Ollama kept. Read the brief the orchestrator gives; do not start before it says.

**For the orchestrator at merge:** apply the two diffs; regenerate placesByRole.json; move the deployment.py helper
out of 6bc6eae; the CARRIES row for route-coverage-check's reverse check.

**Do not redo:** the shapes, refusals and plants above; key_moved stays unchecked (ruling 21); the cluster Secret
keeps the key (ruling 28: do not touch cluster_install.py). osprey-small is never this lane's.

## Brought onto main by slice AD1a (20 November 2026): what the merge settled, and what is still owed

**Settled in AD1a (the server half, merge 6f4b918 and after):** the branch merged into `lane/slice-AD1a` with the screen's
files kept at main's; ADR-135 Amendment 14 kept as 14 (reservation row: lane `v062 AD1a`, written); the plants re-run on main's
code, 21 of 21 and 17 of 17 red (`plants_run_on_main.txt`, `plants_review_run_on_main.txt`). "Move the deployment.py helper out of
6bc6eae" needs nothing on main: main already holds `_a_key_in_the_path` identically and the merge added only
`model_looks_like_a_key` and `label_looks_like_a_key` beside it, once. The `CARRIES` row for the route-coverage reverse check
is not needed on main: the check reports 431 routes, none allowlisted, no new drift.

**Still owed, and not AD1a's:**
1. **Q2 (the owner's key review, question 2, ruling 27): one measured run on the demo's real LiteLLM at its log level with a
   synthetic key**, searching its logs and the credentials row. The live step is off (`process/lanes/v062/live_step.yaml`), so
   this is owed, not run; a release is refused until it has run.
2. The live cases of `tests/services/api/test_route_rights.py` (Postgres): three need a store and were not run in AD1a (the two
   pure cases pass, among them `test_every_route_names_the_right_the_table_gives_it` for the three check routes).
3. A live LiteLLM run under a lease (check, Add, edit with a moved address, a new key, the one-minute cooldown, a duplicate
   credential name).
4. **AD1b** (the screen): the two `.diff` files here (`ACTION_REGISTRY.diff`, `EVERY_HARNESS.diff`), `placesByRole.json`, the screen
   files, and P8's browser run (`plants_p8_run.txt`). Main's screen still calls the removed `POST /v1/admin/models/engines`: it
   compiles against the new generated types and its tests pass, but its Add fails at run time until AD1b lands, so AD1a and AD1b
   merge back to back.
5. **AD1c:** Fix D, the defaults and limits routes' words, `redacted()`, P1 for Edit and P9 for a query string.
