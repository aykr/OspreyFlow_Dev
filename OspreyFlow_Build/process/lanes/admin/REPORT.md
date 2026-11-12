# admin · P10 part 2 · report (12 November 2026): Entra ID's claims wired into the cloud-platform profile

1. Sign-in on cloud-platform uses Entra's claims through the one construction path, Keycloak not rendered: **met** (render.diff). `test_cloud_platform_entra.py` (the rendered environment through `ClaimMapping.from_env` to the resolver, red without `client_id`; nothing rendered names Keycloak or `id.`).
2. Every reader of a role or principal goes through `principal_auth`, each refusal red first: **met**. Roles from the people store, never the token (`test_auth_entra_claims.py`, `test_entra_people*.py`, rule 3 live); the delta socket at connect and each message; the service identity (`test_service_identity_entra.py`); the realm's readers and Superset (readers.diff); the Glass from `GET /v1/me`, failing closed, with the disabled words (glass-sign-in.diff).
3. cp-policy-check green with no Keycloak: **met**, 0 violations on all five fixtures on L1.9 part 2's merged render (`gates/2516c4b.cp-policy.txt`).
4. Gates once through `stack_lease.sh offline admin` at 2516c4b on main 816ccf7, ten diffs applied: make -k ci green; make test 12,364 passed, failing only the server's GPU case and the guide's PDF (made at merge).
5. Live: the full run at 302cf3e (35 failed, each in other lanes' records: `gates/p10p2_live_302cf3e_baseline.txt`; 3,401 passed); the targeted list at 2516c4b, 74 + 7 passed (`gates/p10p2_live_targeted_2516c4b.txt`); leases named in each.
6. Plants: 52, 71 case runs red (68 offline at cc684ec, 3 live under the lease), `P10_P2_RED_RECORD.md`.

**Diffs** (`p10p2/`): render, runbook (INSTALL.md step 6 Entra's; P7b's identity.py removed), readers, glass-sign-in, actionRegistry, every-harness, makefile, ci-yml, resolver-doubles (25 test files), admin-guide (1.84; the PDF at merge).
**Carried** (CARRIES): owner resolution, Superset and report sync on Entra (refused on the profile until then), ADR-106 names from the people store, one real token from the client's tenant (Amendment 6's assumptions).
**Decisions:** the orchestrator's rulings only (roles in the deployment's store; reporting refused; the runbook mine; the disabled words), each in ADR-148 Amendment 8.
**Commits:** on `lane/admin-p10p2` over main 816ccf7, `packages/schemas` its own commit at the head. Nothing of mine is running; stack b released.
