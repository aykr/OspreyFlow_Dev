# studio-b · L1.10 · the deployment's marking ceiling (ADR-148 decision 10) · the plan

Spec: ADR-148 decision 10 (`spec/06_DECISIONS.md`), spec 01's "the deployment's highest" (§ datasets),
spec 03's `above_the_ceiling`. The as-built record is ADR-148 Amendment 2 (reserved on main).

**The setting.** `deployment.highest_marking` in `packages/schemas/deployment.py`. Unset means the handling scheme's
highest. It is checked against the scheme the Conduit loads (UK law enforcement, `run_resources.py`), as
`governance.marking` is (`harness/site.py`), and rendered as `OSPREY_HIGHEST_MARKING`. An unknown value is refused
at render. The Conduit and the ingest engine read it with `services/ingest/ceiling.py`'s `DeploymentCeiling`, and an
unknown value stops the Conduit's start, as an unknown grading scheme does.

**The funnel.** Every load goes through `services/ingest/engine.run_recipe`. The check runs there after the existing
refusals and before raw staging, the first write. Each row's marking is the engine's own `row_marking`; a part that
cannot be read counts as its strictest possible marking, so it fails closed. A row that is rejected for a unit
conflict is not written, and is not judged. One row above the ceiling refuses the whole load
(`AboveTheDeploymentCeiling`, a `RecipeRuleError`, so every caller and the run ledger already handle it). The words
give the limit, never the content. `run_recipe` reads the ceiling from the environment when not given one, so no
caller can leave it out.
- It reaches every load: Studio runs, Run now, the scheduler, connectors and refreshes, staged pipelines (whose step
  tables are written before `run_recipe`, so they get a check of fixed markings first, in `pipeline_run`), held-row
  releases, the seeds through the engine, the site grid and the batch CLI.

**Other entry points, each named, each red first:**
- **Uploads that carry a marking** (`app.py`: a document, a picture): a route check before anything is stored.
- **Outside this lane's files:**
  - promotions and drawn merges (case's `promotions.py`, `drawn_merge.py`): `highest()`'s fallback, and a cap, at the
    ceiling, as a patch or a carry;
  - demo seeds that write the graph directly (`seed_cyber_intrusion`, `seed_fixture_corp`, `seed_paysim`): named;
  - System showing the ceiling (admin's `System.tsx`, `SystemStatus`): a diff for admin;
  - cloud-platform's OFFICIAL-SENSITIVE default: on `lane/platform` (P7), a carry;
  - the drawn item: case-b's (CARRIES row 50).
- **Not loads:** restore (whole stores into an empty deployment) and reference lists (they carry no marking).

## Decisions taken (the owner may overrule)
- One row above the ceiling refuses the whole load, rather than holding or rejecting that row: the decision says
  "refused before anything is written".
- A part whose marking cannot be read counts as its strictest possible marking (fail closed).
- The ceiling defaults to the scheme's highest, so a deployment that sets nothing loads as today.
