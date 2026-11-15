# Platform lane handoff: v061-admin-forms, paused 15 Nov 2026 until after v0.6.0's package test

**Branch** `lane/platform-admin-forms`, worktree `~/dev/osprey-wt/platform`. Last real commit `fc77f2a`; the
`wip(platform): paused` commit after it holds this file alone (rewrite it away on resuming, delete this file).
Nothing pushed, nothing merged; nothing merges before v0.6.0 is released.

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
