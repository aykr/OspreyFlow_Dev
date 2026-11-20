# Slice CO2 · CO2 · The Conduit admits the `pages` service's own Entra client, and no other (ADR-152 decision 11, X1)

- **Build id:** CO2
- **Dial setting:** balanced
- **Rounds limit:** 4
- **After:** nothing (BL4, ADR-152, is on main)
- **Status of this brief:** written by the conductor on 19 November 2026 under the owner's standing approval (ruling 8, and his
  word of that day to start stage 3 beside the merge queue), from ADR-152 decision 11 row X1 and a scout of the same day. The
  four choices the ADR leaves open are settled below, each in one line; the owner is told afterwards.

## What

ADR-152 puts a server-rendered `pages` service beside the React workspace. It signs a person in as a confidential OIDC client
and calls the Conduit with that person's bearer, so the Conduit must accept a token issued to `pages`. Today it cannot on
Entra ID: the Conduit admits a token issued to the Glass's client, and to Superset's (on two routes only), and refuses any
other client. On Keycloak nothing changes in the Conduit (any realm client whose token carries the configured audience
passes). This slice is the Conduit half of X1 and nothing more.

1. **ClaimMapping gains `pages_client_id`** (OspreyFlow_Core/packages/principal_auth/__init__.py, the class `ClaimMapping` about
   line 232, `superset_client_id` at about line 266 and its validator at about lines 282-293; `extra="forbid"` at about line
   249, so the field must exist before any config names it). Optional, default none, so every existing configuration stays
   valid. Validated as `superset_client_id` is (a GUID; needs `tenant_id`; not the Glass's `client_id`, not `api_client_id`),
   and, one choice the ADR leaves open: **also not `superset_client_id`** (one token must not mean two route sets).
2. **The admit branch** (`_verified_parts`, Entra branch about lines 957-985; the client set at about line 974; the Glass's
   admit at about lines 975-976, Superset's at about 977-978; the refusal "token was not issued to the Glass's client" at about
   lines 979-980). A token issued to `pages_client_id` is the person it names **on every route their rights allow** (as the
   Glass's is, `routes=None`), held to every other check a Glass token is held to (tenant, scope, not app-only, not a guest
   where the Glass's is refused, one client in the token). Without `pages_client_id` named, a token issued to the pages client
   is refused as any other client's is. A third client is still refused when the pages client is named.
3. **The deployment configuration carries it** (OspreyFlow_Core/packages/schemas/deployment.py: the field beside
   `superset_client_id` at about lines 1113-1119, emitted into `claim_mapping()` only when set, about line 1218). The
   generated TypeScript (OspreyFlow_Core/packages/schemas/generated/OspreyConfig.ts) is regenerated with the repository's own
   command and `make schemas-check` and the type check are run (a change to packages/schemas drifts the generated types, which
   is a build failure). **Not** in this slice: the render's refusal when a `pages` service is on under Entra with no
   `pages_client_id` (there is no `pages` service yet: it belongs to PL3's render or a later slice), the Keycloak realm's
   `osprey-pages` client and its test (tests/harness/test_realm_pages_client.py is named in ADR-152 and is the sign-in
   slice's), and any Admin form (none exists for `superset_client_id`).
4. **The spec and the guide say it** (rule 11). Where the spec or the administration guide describes `superset_client_id`
   (the scout found it in OspreyFlow_Core/docs/administration-guide.md about lines 1205 and 3354 and its copy
   OspreyFlow_Build/spec/10_ADMINISTRATION_GUIDE.md about lines 989 and 3124, and in the runbook text of the harness), say what
   `pages_client_id` is, in the same place and the same style, only where a test or the sentence's truth requires. ADR-152
   already decides the change: do **not** add an amendment heading or a reservation row (a new `### Amendment` heading must
   be in the form `### ADR-n, Amendment m` and reserved, or the reservation check goes red); if the only place that can say it
   is the ADR, add one sentence to the existing text of decision 11 row X1 and no heading.

Binding: process/CLAUDE.md rules 3, 4, 11, 12, 15; spec/06_DECISIONS.md ADR-152 decisions 4 and 11 (about lines 40797-40800 and
40929-40948) and answer 6 (about lines 41237-41242).

## Acceptance test

Two new files (they become the acceptance files), both pure:

- OspreyFlow_Build/tests/services/api/test_auth_entra_pages.py, modelled on test_auth_entra_superset.py in the same folder
  (96 lines; it imports `entra_claims`, the keypair and JWKS fixtures and `_resolver` from test_auth_entra_claims.py; a real
  RSA key signs a v2.0-shaped token and the resolver verifies it against a JWKS URL, so the refusals come from the claims, not
  from a fake). The four tests ADR-152 names, with these exact names:
  - `test_a_token_from_a_realm_client_without_the_audience_mapper_is_refused`: **a control, green today** (the Keycloak path
    refuses a token without the configured audience, `_verified_claims` about lines 1664-1687, `verify_aud` on when
    `oidc_audience` is set). The test **sets `oidc_audience` explicitly**, or it is vacuous; its red is shown by planting the
    violation (rule 15): with the audience check off, a token without the audience is accepted and the test fails.
  - `test_a_token_issued_to_the_pages_client_is_the_person_on_every_route`: red today (the token is refused as another
    client's); also the Glass's token is unchanged, and Superset's token still reaches its two routes only.
  - `test_without_the_pages_client_named_its_token_is_refused`: the same token, `pages_client_id` not set: refused with the
    Glass-client refusal.
  - `test_a_third_client_is_still_refused`: a token issued to neither, with the pages client named: refused.
  - and the pages client's registration is its own, as for Superset's (parametrised): equal to the Glass's id, to the API's,
    to Superset's, and not a GUID: each a ValidationError naming `pages_client_id`; and it needs an Entra mapping
    (`tenant_id`).
- OspreyFlow_Build/tests/harness/test_cloud_platform_pages_client_id.py: through the deployment configuration (as the
  superset cases in test_cloud_platform_entra.py about lines 213-252 do): `pages_client_id` set is emitted into the rendered
  claim mapping, unset emits nothing (no `pages_client_id` key), a malformed one is refused at the configuration; the claim
  mapping the Conduit reads from that env accepts it (the two ends meet: plant the emitted JSON in the shape the Conduit
  reads, rule 15).

Plant the violation in the shape the code meets at its real call site: a signed token as the resolver receives it, with
`azp`/`appid` and `tid` as Entra puts them.

## Checks

Pure only (ports 9), the acceptance files and the neighbours that set `superset_client_id` or read the claim mapping:
OspreyFlow_Build/tests/services/api/test_auth_entra_superset.py, test_auth_entra_claims.py, test_entra_guests.py;
OspreyFlow_Build/tests/harness/test_cloud_platform_entra.py, test_cloud_platform_entra_count.py, test_superset_entra_sign_in.py,
test_realm.py; then the schemas check, run as the checks command runs it: from OspreyFlow_Core,
`python -m tools.schemas_check` with PYTHONPATH=../OspreyFlow_Build, through `uv run` (a worktree has no Core .venv, so
`make schemas-check` does not run there). The line adds every mapped pure test that scans a folder the
slice changes. Run the type check on the regenerated TypeScript too (a change to packages/schemas).

## The four choices the ADR leaves open, settled by the conductor (the owner is told afterwards)

1. `pages_client_id` must differ from the Glass's, the API's **and Superset's** ids.
2. It is validated whenever it is set (not only when a `pages` service is rendered).
3. A render refusal for "`pages` on under Entra with no `pages_client_id`" is **not** here: there is no `pages` service yet.
4. The Keycloak audience test sets `oidc_audience` itself, and its red is shown by planting the fault.

## Out of scope

The Glass (OspreyFlow_Core/apps/workspace) and any TypeScript other than the regenerated schema types; the `pages` service and
its sign-in; the Keycloak realm template and its `osprey-pages` client; the render's refusal; Admin forms; the Makefile and
the CI workflow; any other route's access rule. If a route turns out to need a different rule for the pages client than for
the Glass's, stop and say.
