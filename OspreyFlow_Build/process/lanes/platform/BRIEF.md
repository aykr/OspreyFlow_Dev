# Platform lane · brief P1 · model administration in the Glass's Admin place

Written by the orchestrator, 8 November 2026, for the **platform lane's first session**, on account `sol`
(ADR-142 Amendment 3: a new lane for maps and model administration). Opus, medium. Size L. After it come
P2 (usage and limits), P3 (maps administration, ADR-147) and P4 (the analyst's map), each briefed when
the one before merges.

**The owner's rulings of 8 November 2026** (put to the owner as multiple choice by the orchestrator):
model engines, each job's model and their keys are **managed in the Glass's Admin place**, keys
write-only; the CLI (`ospreyflow models`) **stays** for headless and recovery use, and hand-editing
`osprey.yaml` for providers is no longer the documented way; map provider keys follow the same rule (P3).
This reverses ADR-135's "never in the Admin area, never in a browser page of the Glass", so you write
**ADR-135 Amendment 2**, heading exactly as reserved in `spec/ADR_RESERVATIONS.md`, before the code that
depends on it. Amendment 2 amends; never edit ADR-135 or Amendment 1.

**The lane.** `lane/platform` owns `apps/workspace/src/admin/sections/{Models,Maps}*`,
`apps/workspace/src/{map,site,models}/**`, `services/api/model_routing.py` and the model routes,
`packages/adapters/model_litellm/**`, the set-up console's Models and Geospatial screens and their routes,
and `cli/ospreyflow/models.py` (`process/BUILD_PLAN_PARALLEL_LANES.md`'s map, which lists the map files
for P3). A new Admin section needs its entry in Admin's section list: send it to the orchestrator as a
diff, which commits it just before your merge. `packages/schemas/**` changes go through the orchestrator
as a small shared commit, merged first. Live runs take a test stack (`stack_lease.sh acquire platform
"<purpose>"`, a or b) and pin the ports it prints. **No real hosted provider is called by any test or CI
run, and no real key is ever written anywhere in the repository** (rule 9 and FDE_HANDOVER §2): the
connection test runs against a local fake gateway that refuses as the real one refuses (rule 15).

**What is there today** (the orchestrator's survey, 8 November): `packages/schemas/deployment.py`'s
`ModelsConfig` (`providers`, `defaults`, `sendable_handling_codes`, the per-job pinned lists);
`model_routing.py` (the handling-code and dataset egress gates, ADR-136); keys as
`OSPREY_MODEL_KEY_<NAME>` only in `deploy/generated/<profile>/deployment.env`, read by the gateway alone;
`cli/ospreyflow/models.py` (`models`, `models key`, `remove-key`); *Admin › System* read-only
(`admin/sections/System.tsx`, `GET /v1/admin/system`); the set-up console's Models screen with write-only
key fields (`apps/harness/src/screens/ModelsScreen.tsx`, `harness/install_page.py`). And a likely defect:
the set-up console's egress warning (`harness/screens.py`, `_egress_consequence`) reads the legacy
`hosted_fallback`, so a provider set the new way may never show its egress exception (`spec/05` §2.1).

**Binds.** `process/CLAUDE.md` rules 1–15 (3, 4, 5, 12, 13 and 15 above all); ADR-095 and Amendment 2;
ADR-114 decision 11 and Amendments 6 and 7; ADR-135 and Amendment 1; ADR-136 and Amendment 1; ADR-137;
ADR-112 (rights); `spec/00` §2.4, `spec/04` §4, `spec/05` §2.1.

**Build** (the plan's row P1):
1. **ADR-135 Amendment 2**: the decision, the new right (`manage_models`, an ADR-112 amendment reserved
   through the orchestrator if a new right needs one), where a key written from the Glass is stored, the
   audit record's fields (never the key), and what the CLI still does.
2. ***Admin › Models***: engines added, edited and removed (label, roles, an https base, the privacy
   contract and its reference); each job's model chosen from the closed, pinned lists; a key entered,
   rotated or removed in a write-only field, never returned by any route, never logged, never in an
   audit entry or an error; *Test the connection*; every change audited. The Conduit writes the key only
   where the gateway reads it and restarts the gateway. *Admin › System*'s engine table becomes the
   summary. Every screen in the dark, light and GOV.UK themes.
3. **The egress warning** reads `providers` (red first with the legacy read).

**Ask the owner first** (through the orchestrator, as multiple choice, at most four, recommendation first;
stop that piece and carry on with the rest): where a key written from the Glass is stored (for example:
the Conduit rewrites the gateway's `deployment.env` and restarts it; or a secrets file only the gateway
and the Conduit's key writer mount; or the deployment's secrets store where one is configured), and
whether a key change needs a second person (ADR-133's approvals).

**Tests first, each shown red by a plant at the real call site:** without the right, every Models route
refuses (rule 4), red with the check removed; the key appears in no response body, log line, audit entry
or error, planted with a recognisable test value through the real route and the real logger; the
gateway's configuration holds the key after a write and not after a removal; the connection test reports
the fake gateway's refusal in words; keyboard cases for every Models action (rule 13) with their registry
ids as a diff for the orchestrator; axe in the three themes.

**Exit.** The row's exit; `make ci` and `make test` green offline; a friction fragment. Report in Prompt
L's format, then stop.
