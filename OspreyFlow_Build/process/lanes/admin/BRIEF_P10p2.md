# Admin · brief P10 part 2 · Entra ID's claims wired into the cloud-platform profile

Written by the orchestrator, 11 November 2026, after P10 part 1 merged (eec782d). Binds: `process/CLAUDE.md` rules 1–15,
`process/lanes/PROMPT_L.md`, ADR-142 Amendments 6–8, ADR-148 decision 9 and its Amendment 6 (P10 part 1 as built).
An access step: two review rounds, listed for the owner.

**What.**
- The profile's claim settings: `ClaimMapping` from `cloud_platform` settings (tenant, client, scope, the claim names or
  the group table) into the Conduit's principal resolution, on `cloud-platform` alone.
- Keycloak not rendered on this profile, and the identity step's install path in P7b's runbook pointing at Entra.
- The carried readers of `roles` outside the one construction path, each moved to it or shown not rendered on the
  profile, with a test:
  - `harness/webapp_auth.py:135` (`require_admin_role`);
  - `deploy/superset/superset_config.py:89`;
  - `harness/oidc.py:254`;
  - `services/api/service_identity.py` (Keycloak's `service-account-<azp>`, with no tid pin).
- Part 1's other carries (CARRIES, P10 rows):
  - the guest check's `idp` and `iss` forms;
  - `client_id` and `scope` with no tenant set, refused;
  - the wiring test going red with `client_id` removed.

**Ownership (Amendment 8 decision 3).** `packages/principal_auth/` is yours. `values.yaml`, the profile's settings model,
`render.py`'s profile entry and `harness/cloud_platform/**` are platform's: send diffs. P7b lands before this step, so build
on main after it, and rebase if P7b lands while you work.

**Exit.**
- Sign-in on the cloud-platform render uses Entra's claims through the one construction path; Keycloak isn't rendered.
- Every reader of a role or principal on the profile goes through `principal_auth`, each refusal red first.
- cp-policy-check green with no Keycloak.
- Gates once through `stack_lease.sh offline admin`.
- **The test server is quiet from 12:00 UK time on Friday 13 November** until the owner's demo is over.

Write the as-built record as ADR-148 Amendment 8 (reserved).
