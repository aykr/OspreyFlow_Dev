# admin · v052-identities (v0.5.2 steps 2-3) · report (14 November 2026): dashboard identities and the report sync on Entra ID

ADR-148 Amendment 10. A dashboard on Entra ID is one app registration, registered by application id. Its role is
Dashboard.Read, and its narrow principal reaches the two dashboard routes alone, through one route gate; it never
submits runs, and the case stream is closed to it. The report sync asks with the API's scope.

**What changed after the lane reviews:**
- A dashboard holds Viewer and nothing more, on Entra as on Keycloak.
- Its name is a unique slug.
- Its grants are revoked before its registration goes (`revoke_everywhere`), so a failed revoke leaves it registered
  and a retry finishes the job.
- The deployment's own applications are refused.
- The read of a dashboard's store is bounded (503).
- Client claims are read as strings only.
- Each own-client defence is held, and planted, on its own.
- Admin › Dashboards has its own `GET /v1/admin/dashboards/sign-in`.

**Proof:**
- 30 offline plants at 7a84543, each pytest with a fresh PYTHONPYCACHEPREFIX, every one red (`v052/plants_7a84543/`).
- Live on stack b at a2c5670: the two live files 65 passed, and three plants red: the case gate opened, the revoke
  deleting nothing, the tenant pin removed (`v052/*_live_a2c5670.txt`). `test_route_rights` 5 passed.
- Live run 1 at 2b42dea found two defects in this lane's own tests, fixed in a2c5670. The full selection was
  stopped on the orchestrator's word: the full suite runs once, at step 6.

**Gates at 4e83010** (on main 424e47a):
- `make -k ci`: exit 0. Round 1 at c47e45d failed `route-coverage-check` on the new route, so the check was shown red
  on it; fixed.
- `make -k test`: 13,474 passed, 2 failed. Both failures and `live-collect` are main's: the Makefile names
  `tests/services/search_index/test_feed_live.py`, which main does not hold.
- Local vitest, `src/admin`: 188 passed.
- Records are in `v052/gates/`.

**Carried, not fixed:**
- The Glass does not show a dashboard's name.
- The 409's key is still labelled `client_id`.
- No migration for 009a889's table (never merged).
- A KeyError is still possible from IdentityAdmin.
- The v1.0 token test is not fully Entra-shaped.

**Shared files:** `packages/schemas/{admin,domain}.py` and their generated TS; `spec/03`, `spec/06` and
`ADR_RESERVATIONS.md`.

**Questions for the owner:** none.

# admin · pg (Step 2 of BRIEF.md) · report (13 November 2026): a deployment's own PostgreSQL allows what its services may hold

`lane/admin-pg` over main `20fab33`, gated at `6074baf`. ADR-114 Amendment 43 (written). Reviewed twice by
my lane-reviewer and by the orchestrator; every must closed, each with its red. Two owner-file diffs travel with the
branch for the orchestrator to apply at merge: `platform-pg.diff` (`scripts/refresh.py` and platform's tests) and
`ci-pg.diff` (`ci.yml`, the `Makefile`, `tools/test_file_coverage_check.py`); the branch holds main's copies of those files.

| Exit criterion (brief) | Met | Proving test (records in `gates/`) |
| --- | --- | --- |
| Choose with evidence: render `max_connections`, bound the pools, or both | render, pools unchanged (Am 43 point 3: `min_size=0` moves only the count at rest, 50 → 0; what two Conduits may grow to, 402, is unchanged by it) | the measured Conduit below |
| The Conduit's share measured, not counted | yes: 48 pools, 50 at rest, 201 at their max (+4 with Entra ID), against the ceiling 220 | `test_postgres_connections_live.py` (a running Conduit's `create_pool` recorded); red with the ceiling at 200 and with InvestigationStore's pools hidden from the record |
| Every profile with its own PostgreSQL rendered (Lite, Small, sized or not); the managed ones carried | yes: 660 on Lite and Small; cluster and cloud-platform's RDS set their own (carried) | `test_postgres_connections.py` (render cases); `pg_render_red.txt` |
| Red: two Conduits against the rendered PostgreSQL, refused before, up after | yes: 659 of 660 held at once | `pg_two_conduits_green.txt`; red at the image's 100, at 250 (Conduit 2 cannot start), at 640 (the reserve) |
| A deployed Small picks it up on `ospreyflow apply` (and `update`, `start --build`) | yes: apply restarts PostgreSQL, Keycloak and the gateway, nothing else; update brings an existing compose file to the number | `test_an_existing_deployment_restarts_postgres_keycloak_and_the_gateway_on_apply`, `test_update_brings_an_existing_compose_file_to_the_number`, `test_refresh.py`'s case in `platform-pg.diff`; `pg_update_{function,path}_red.txt` |
| Say so in the amendment | yes | ADR-114 Amendment 43 point 4 |

**R1's cloud-platform figure agrees.** R1 finding 15 put `max_connections ≥ 750` in the cloud-platform INSTALL.md
(`lane/platform-r1` `harness/cloud_platform/runbooks.py`). Its four constants are equal to `harness.profiles`'s
(`CONDUIT_POOL_CEILING` 220, `RUNNING_LOADS_ALLOWED` 20, `GATEWAY_POOL_MAX` 10, `OPERATOR_RESERVE` 20): 3 × (220 + 20) +
10 + 20 = 750. The totals differ by what each profile runs: cloud-platform runs the job worker as its own image, which
opens the same stores (three Conduit-shaped processes), and has no Keycloak (Entra ID) and, for now, no report sync or
Superset (refused on that profile); a deployed Small's compose has no worker container (the loop runs in the Conduit,
whose pools were measured): 2 × 240 + Keycloak 100 + gateway 10 + Superset and the report sync 50 + reserve 20 = 660.
Not measured by anyone: that the worker image holds what a Conduit holds (750 assumes it). When report sync and Superset
come to cloud-platform, its number gains `SUPERSET_AND_REPORT_SYNC_MAX` (50).

**Gates** (offline on the test server, `platform-pg.diff` and `ci-pg.diff` applied): `make test` at `6074baf`: pytest 13,172 passed, 1 failed, the server's GPU case (`test_webapp_preflight.py::test_gpu_is_skipped_on_this_platform_never_shown_as_a_pass`, known, CARRIES: the host has a real GPU); test-js 3,271 passed. `make -k ci`: exit 0. The docker case (its own job's file) green and its five reds, recorded at `6074baf`. At `0f8b3e7` the same gates failed the test-file coverage check (the docker case's file, live through `asyncpg`, wired in no job): `gates/0f8b3e7.{test,ci}.txt`, fixed at `f1c64fa`. Records: `gates/6074baf.{test,ci}.txt`, `gates/pg_two_conduits_*.txt`. After `6074baf`: the records, Amendment 43 naming the live file and its job (`test_spec_doc_paths.py`, `test_doc_citations_check.py` and the citation check green on the Mac), and this report.

**Decisions taken** (Prompt L): render the number rather than bound the pools (above); the ceiling 220 over the measured
201 + 4 (room for a pool or two without a release); the running loads' lock connections an allowance of 20, not
measured; Keycloak's and the gateway's pools rendered (`KC_DB_POOL_MAX_SIZE` 100, `database_connection_pool_limit` 10)
so the number counts the product's own settings, not their defaults; the docker case in its own file, wired as a
live-service test in its own CI job (the coverage check found the whole file unwired at `0f8b3e7`).

**Commits:** `git log --oneline 20fab33..lane/admin-pg`. **Requests:** apply `platform-pg.diff` and `ci-pg.diff` at merge. **Carried**
(Am 43 point 5, CARRIES): managed PostgreSQL and RDS; the gateway's pool unmeasured; a bound on concurrent loads; the
lane stacks' and CI's 400. **Questions for the owner:** none. **Still running:** nothing.

---

# admin · refresh (Step 1 of BRIEF.md) · report (13 November 2026): a refresh keeps the person signed in and where they were

`lane/admin-refresh` over main `fa5d988`, gated at `6c691e8` (tree `635aef59`). ADR-050 Amendment 3 (written). Reviewed by
my lane-reviewer at `8657a4b` (13 findings) and twice by the orchestrator (`8657a4b`, `4f31898`); every must closed, each
with its red. Step 2 (Postgres connections, ADR-114 Am 43) is on its own branch, `lane/admin-pg`, not part of this merge.

| Exit criterion (brief) | Met | Proving test (records in `gates/`) |
| --- | --- | --- |
| Live IdP session → signed in, no screen | yes | `keyboard/refresh-sign-in.spec.ts` (real App, real `oidc-client-ts` frame); `App.test.tsx`; red on e1f15e4 |
| No session → the screen with its sentence | yes | spec: no session, and each of `login_required`/`interaction_required`/`consent_required`; red with a fake that grants |
| Home stays Home; a case that case; Admin Admin | yes | spec (Admin; kept Admin without rights → Home); `App.test.tsx` (Home with a case open; the case's workspace; a refused case → Home; a case switch over a full-page sign-in); `refreshPlace.test.ts` |
| A silent failure never loops | yes | `signInAtLoad.test.ts` (red without the memo); spec asks once |
| The fake refuses `prompt=none` with no session, as Keycloak does | yes | spec's fake (iss, state, PKCE, redirect_uri, code once; each refusal red-planted) |
| One live case against a real Keycloak | yes, on a throwaway Keycloak 26.0 (no lane stack carries one) | `test_refresh_silent_sign_in_keycloak.py`, the library's captured request; green + plant |
| The shared-key gate passes the round | at the HTTP level only | `test_refresh_silent_round_through_the_key.py` through Caddy 2.11.4, red with `Domain=` dropped; browser frame behaviour unmeasured (Am 3 says so) |
| Keyboard | none new | the Sign in screen is unchanged |

**Gates at `6c691e8`:** spec 30/30 (ten cases × 3), unpiped. `make test`: pytest 13,031 passed, 8 failed — the server's GPU
case (known), six `test_lanes_groups.py` cases and `test_doc_citations_check.py`, all from main's own platform-b files
(new steps not in `groups.tsv`; `ci4/committed-osprey-yaml.md` citing `OspreyFlow_Build/scripts/lanes_launch.sh`), none touched here;
test-js 3,257 passed, MatrixView's first-frame budget failed (known). `make -k ci`: exit 2 on `citation-check` alone (the
same citation). Records: `gates/6c691e8.{test,ci}.txt`.

**Decisions taken** (Prompt L): 10 s timeout for the round at load (the bundle is warm; the person faces a blank page);
`from`/`view`/`investigation` stripped after a silent sign-in, as the redirect's return to the root did (the case stays,
from session storage); only views the landing check corrects are restored; the live Keycloak case on a throwaway container
under `offline`, since no lane stack carries Keycloak; the waits after the round 15 s (the frame loads the dev server's
whole bundle; Home past 5 s in 1 of 20 server runs); the Caddy and Keycloak cases import platform-b's fixtures (a shared
fixture is a CARRIES row for after this merge).

**Commits:** `git log --oneline fa5d988..6c691e8` (13). **Requests:** none open (RDS and the shared fixture are CARRIES rows).
**Questions for the owner:** none. **Still running:** nothing. The orchestrator's socket in PROMPT_L.md (`8906`) is stale;
`6964` answered.
