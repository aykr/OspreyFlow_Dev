# P10 part 2 · plan (admin, 11 November 2026)

Brief: `BRIEF_P10p2.md`. Rulings: the orchestrator's of 11 November (roles (a); ownership). Binds ADR-148 decision 9,
Amendment 6, rules 1–15. As-built record: ADR-148 Amendment 8 (reserved).

## Mine (committed on the branch)

| File | Change | Tests first |
| --- | --- | --- |
| `packages/principal_auth/__init__.py` | CARRIES 177: a guest is an `idp` whose tenant is not `tid`, in either Entra issuer form. CARRIES 178: `client_id` or a non-default `scope` refused without `tenant_id`. The scope check typed on its own, so the app-only plant fails for its reason (CARRIES 180). `RoleSource` protocol, `StoredPerson`; `resolve_principal` (async) reads the stored person inside the one construction path: a failed or slow read gives `PrincipalLookupUnavailable` (503), a disabled person a 401, and the roles come only from the store. `resolve` (sync) refuses an Entra mapping. Owner resolution unavailable on Entra. `ClaimMapping.from_env` (`OSPREY_CLAIM_MAPPING`, JSON) | `test_auth_entra_claims.py` (new cases) |
| `services/api/entra_people.py` (new) | `EntraPeopleStore` (DDL `entra_people`: tenant, oid, roles, disabled, name, last claims, first seen), the role source, first administrators seeded if absent, and `EntraPeopleAdmin`, Admin › People's backend on Entra: list, roles, enable/disable, add by oid; invite, reset, access, remove, organisation link and dashboards refused in words | `test_entra_people.py` (offline, a fake that refuses as the store does), `test_entra_people_live.py` (Postgres, rule 4: another tenant's row grants nothing) |
| `services/api/app.py` | `get_principal` and the socket path await `resolve_principal`; 503 on a lookup failure; the backend chosen by the mapping; `POST /v1/admin/people/by-oid` | route rights, access test |
| `services/api/service_identity.py` | Entra: an app-only token of the pinned tenant, its client in `azp`/`appid`, never the Glass's; a `tid` under Keycloak refused | `test_service_identity_and_rollup.py` new cases |
| `services/api/identity_admin.py` | unchanged unless the backend split needs it | |
| `apps/workspace/src/admin/sections/People.tsx` | on Entra: *Add by object id*, no invite, the words "Entra holds the accounts" | vitest, keyboard step (rule 13) |
| `packages/schemas` | `AddPersonByOid`, the deployment's sign-in kind for the Glass; own commit at the head | type drift |

## Shared (diffs in `process/lanes/admin/p10p2/`)

`services/api/config.py` (if needed), `harness/webapp_auth.py` and `harness/oidc.py` (refuse a `tid` token; not rendered
on cloud-platform, test), `deploy/superset/superset_config.py` (Entra: Gamma for everyone, no token roles),
`packages/schemas/deployment.py` (`cloud_platform.claims`), `harness/cloud_platform/**` and `profile.yaml` (Keycloak
not rendered: door, group 0, resources; Entra's host in egress; `OIDC_*` and `OSPREY_CLAIM_MAPPING` rendered; empty
`first_administrators` refused), `render.py`'s entry, `values.yaml`, the cp-policy-check's `GROUP_ZERO_ALLOWED`,
P7b's runbook identity step.

## Order

1. principal_auth carries and role source (red first, plants).
2. Store and People backend; app wiring.
3. service identity.
4. Glass People.
5. Diffs, rebased onto P7b when it lands.
6. ADR-148 Amendment 8, CARRIES (owner resolution, Superset), plants record, friction row, REPORT.
