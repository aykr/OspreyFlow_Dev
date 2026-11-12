# admin · P10 part 2 · report (12 November 2026)

Entra ID's claims wired into the cloud-platform profile (BRIEF_P10p2.md), as built in ADR-148 Amendment 8. An access
step: the lane's own review is done; the orchestrator's two rounds follow.

| Exit criterion | Met | Proof |
| --- | --- | --- |
| Sign-in on cloud-platform uses Entra's claims through the one construction path; Keycloak not rendered | yes (render as a diff) | `test_cloud_platform_entra.py` (the rendered environment through `ClaimMapping.from_env` to the resolver, red without `client_id`); `test_no_pod_takes_group_0_and_keycloak_is_not_rendered`; no rendered value names Keycloak or the `id.` host |
| Every reader of a role or principal on the profile through `principal_auth`, each refusal red first | yes | roles from the people store, never the token (`test_auth_entra_claims.py`, `test_entra_people*.py`); the delta socket at connect and each message; the service identity (`test_service_identity_entra.py`); the realm's readers and Superset (`readers.diff`); the Glass from `GET /v1/me`, failing closed, no token claim read (`glass-sign-in.diff`) |
| cp-policy-check green with no Keycloak | yes | P7b's merged render: 0 violations on all four fixtures, its tests and helm's (`gates/017350d.ci.txt`) |
| Gates once through `stack_lease.sh offline admin` | yes | `gates/017350d.{test,ci}.txt` on main e726239 with the ten diffs applied: make -k ci green but a citation (fixed, green on the server at the fixed tree); make test 12,286 passed, the server's GPU, OpenSearch and lanes-launch cases (as other lanes' gates) and that citation |

**Plants:** 52 plants, 71 case runs, all red at the head 641c403 (68 offline; 3 live under the lease at 302cf3e). A plant missed on
its first run found a second guard behind the synchronous path, now its own case.

**Live:** the final check at 302cf3e on P7b's main, stack b, with the ten diffs: 35 failed, each the stack's own as T1 part 4's gate records them; 3,401 passed, the people store's file among them (`gates/p10p2_live_302cf3e.txt`).

**Diffs for the orchestrator** (`p10p2/`): render, runbook, readers, glass-sign-in, actionRegistry, every-harness,
makefile, ci-yml, resolver-doubles, admin-guide (its row 1.83, renumbered at merge).

**Carried (CARRIES):** owner resolution on Entra; Superset and report sync on Entra (refused on the profile until
then); ADR-106 names from the people store; one real token from the client's tenant (Amendment 6's assumptions).

**Decisions taken:** none beyond the orchestrator's rulings (roles in the deployment's store; reporting refused on
cloud-platform; the runbook mine; the disabled message), each recorded in Amendment 8.

Nothing of mine is running; stack b is released.

**Commits:** 33 on `lane/admin-p10p2` over main e726239, the schemas change its own commit at the head.
