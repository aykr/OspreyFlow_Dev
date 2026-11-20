# Slice PL2b · PL2b · Connection limits from settings: a deployment's own Postgres allows what `osprey.yaml` says (L10)

- **Build id:** PL2b (the connection-limit half of the plan's PL2; the Java half is PL2a)
- **Dial setting:** balanced
- **Rounds limit:** 4
- **After:** nothing
- **Status of this brief:** written by the conductor on 20 November 2026 under the owner's word of the same day ("the setting with the
  computed default and a refusal below a floor"), from a read-only scout of the same day. The owner gave no floor number, no profile
  scope and no word on the pools: the choices below are the conductor's, derived from numbers already in the code, and the owner is
  told afterwards. Changing the floor later is one constant.

## What

Today a deployment's own PostgreSQL gets `max_connections` from a computed constant, 660, in `OspreyFlow_Core/harness/profiles.py`
(about lines 200-224: `CONDUIT_POOL_CEILING` 220, `CONDUITS_ALLOWED` 2, `RUNNING_LOADS_ALLOWED` 20, `KEYCLOAK_POOL_MAX` 100,
`GATEWAY_POOL_MAX` 10, `SUPERSET_AND_REPORT_SYNC_MAX` 50, `OPERATOR_RESERVE` 20), rendered by `postgres_command` (about 227-239)
and kept current in an existing file by `postgres_connections_up_to_date` (about 242-271, called from `scripts/refresh.py` about
679-685), with the compose rendering in `harness/render.py` (about 1175-1179). `spec/06_DECISIONS.md` ADR-114 Amendment 43 (about
lines 37135-37225) says "there is no osprey.yaml setting for it yet … which is the way to change it if 660 is wrong". This slice is
that setting.

Choices, **settled by the conductor**:
1. **The field:** `resources.postgres_max_connections`, an optional integer in `ResourcesConfig`
   (`packages/schemas/deployment.py` about 1883-1958), default `None` meaning the computed value exactly as today (660; **no change to
   any deployment that does not set it**, proved by a test on the unchanged output). The nearest precedent is
   `resources.postgres_shared_buffers_gib` (about 1905-1908 and its refusal at about 1952-1957): copy its shape and the tone of its
   words.
2. **The floor: 420**, derived and not new: the same sum with one Conduit instead of `CONDUITS_ALLOWED` (1 × (220 + 20) + 100 + 10 +
   50 + 20). Add it beside the other constants in `profiles.py` as one named constant computed from them, so a change to a pool
   changes the floor. A value below it is refused, in words that give the value, the floor, what the floor is made of and the
   computed default, and say how to fix it. A value that is not a whole number, or is zero or negative, is refused in words as well.
3. **Scope: the deployment's own Postgres, rendered in compose** (the profiles that render one). The `cluster` profile's Postgres is
   the operator's (`external.postgres`) and the `cloud-platform` profile's RDS is set at creation to the owner's 1000
   (`harness/cloud_platform/connections.py` about line 31; `test_cloud_platform_poc.py` pins it). The field set under either profile
   is **refused in words** ("this profile's database is not rendered by OspreyFlow: set max_connections where the database is run"),
   never silently ignored. Cloud-platform code, Terraform and the runbooks do not change.
4. **The pools are not settings** (Keycloak, gateway, the Conduit's `create_pool` literals): the sum's inputs stay constants.
5. **It reaches the file:** `postgres_command` takes the setting; `postgres_connections_up_to_date` and its caller in `refresh.py`
   take it too, so a refresh of an existing deployment applies a changed value (and does not "correct" a set value back to 660).
   Find every other reader of the constant (the scout found `harness/render.py`, `scripts/refresh.py`; look for more) and show by a
   test that none is left on the old number when the setting is set.
6. **The specification first (rule 11):** a new `### ADR-114, Amendment 49` in `spec/06_DECISIONS.md` (the number is free; add its row
   to `spec/ADR_RESERVATIONS.md` in the same change, in the table's form, lane `v062 PL2b`) stating the field, the default, the
   floor and its derivation, the scope and the refusals, and saying it supersedes Amendment 43's "no setting" sentence. Bring
   `spec/10_ADMINISTRATION_GUIDE.md` appendix A (about 3245-3248) and `OspreyFlow_Core/docs/administration-guide.md` appendix A (about
   3475-3478), its version table (add the next free row) and `spec/05_DEPLOYMENT.md` (about 905) to it; and correct the stale "at
   least 750" sentence at `docs/administration-guide.md` about line 57 to the 1000 that line 55 gives. The generated TypeScript for the
   schema is regenerated and the schemas check must pass.

Binding: process/CLAUDE.md rules 11, 12, 15; the committed `OspreyFlow_Core/osprey.yaml` must still validate; no change to
`OspreyFlow_Core/Makefile` or `.github/workflows/ci.yml`; British English.

## Acceptance test

One new file, `OspreyFlow_Build/tests/harness/test_postgres_connections_setting.py`, pure (no store, no network, no container;
render to a string or a temp folder), each case **red first** against the real call site (rule 15: through `ResourcesConfig` /
`OspreyConfig` validation and through `render` and `postgres_command`, not a call to a helper alone):
- unset: the rendered command, the refresh check and every profile's output are **byte-for-byte as today** (660);
- set to 900: the rendered Postgres command carries 900; a refresh of a file holding 660 reports it out of date and one holding 900
  reports it current;
- set to 420: accepted; set to 419: refused, the words naming 420 and 660; zero, negative, a float and a string: refused in words;
- set under the `cluster` profile and under the `cloud-platform` profile: refused in the words above; the cloud-platform manifest's
  1000 unchanged;
- the floor follows the constants (plant: raise `KEYCLOAK_POOL_MAX` in the test's own copy and the floor rises with it);
- the field is documented where the guide's appendix A lists it (read both guides) and the generated TypeScript carries it.
State, in the file's header, which test would fail if the floor were not applied (rule 12).

## Merging main in after PL4b: the design tokens moved (the conductor, 20 November, after the builder stopped on six tries)

PL4b moved `tokens.css` from `OspreyFlow_Core/apps/workspace/src/design/` to **`OspreyFlow_Core/packages/design/tokens.css`**. Your own acceptance file `OspreyFlow_Build/tests/harness/test_postgres_connections_setting.py` builds a fake repository in `tmp_path` (the `_deployment` helper) and **its fake tree does not contain the tokens at the new place**, so the refresh code (`harness/keycloak_theme.py`, which reads the tokens, then `scripts/refresh.py`) raises "the design tokens were not found at …/packages/design/tokens.css". That is the one red the last six tries repeated, and it is **your test's fake tree, not the product**: put `packages/design/tokens.css` in the fake tree the way PL4b did for the neighbouring refresh tests (`tests/test_refresh.py`, `test_refresh_before_the_gateway.py`, `test_refresh_search_rebuild.py`, `tests/harness/test_install_page_build.py`: read how each lays its fake tree out after PL4b and do the same; a copied file or a symlink, as they do). Do not touch the product's path. After that the checks must be green; if any other red remains, say exactly which test and why in your report.

## Checks

Pure only. The **checks command** runs `tests/harness/test_postgres_connections.py`, `tests/harness/test_render_memory.py`,
`tests/harness/test_model_engines.py`, `tests/harness/test_cloud_platform_poc.py`, `tests/test_copy_says_no_client.py`, the schemas
check (`uv run --frozen python -m tools.schemas_check`; a scratch worktree has no `.venv`, so not `make schemas-check`) and the test
that the committed `osprey.yaml` validates (find it: `deployment.py` names it near its top). The **acceptance command** runs the new
file alone. The line adds every mapped pure test that scans a folder the slice changes. Do not run `test_postgres_connections_live.py`
(it needs Docker; it is a CI job), and never `test_apply_env`.

## Out of scope

The cloud-platform's RDS, Terraform and runbooks; the Conduit's pools and the Keycloak and gateway pool sizes as settings; the
installer page and the `ospreyflow` CLI's answers; Valkey and ArcadeDB limits (none exist); the lane stacks' 400
(`stack_lease.sh`); PL2a (the Java notice).
