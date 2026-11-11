# ADR-148, Amendment 6 (11 November 2026)

*Entra ID's claims as built (P10 part 1). Drafted by the admin lane on the test server. The number is reserved for P10
in `spec/ADR_RESERVATIONS.md` on main (32dfd55). The draft stays in `process/lanes/admin/` until merge, and the
merger places it in `spec/06_DECISIONS.md` under ADR-148 (CLAUDE.md rule 11).*

Decision 9 says the claims are mapped, not assumed, by named claim or by Entra group table. Built in
`packages/principal_auth` (`ClaimMapping`, `principal_from_claims`):

1. **One source per claim.** Clearance, organisational unit and handling codes each come from **either** a token claim
   **or** a group table, never both. A setting naming both or neither fails to load, and so does an unknown key or a
   group granting an empty value. Different claims may use different kinds of source. A clearance or unit table maps
   a group to **one** value; a list there fails to load.
2. **A mapping other than the fixed names is an Entra mapping.** It names its tenant (`tenant_id`, a GUID) and the
   Glass's app registration (`client_id`, a GUID). Its `scope` setting names the one delegated scope the Glass asks
   for (default `access_as_user`). With `tenant_id` set:
   - the token must carry `oid` and `exp`;
   - its `tid` must equal the tenant;
   - the resolver refuses to start unless `OIDC_ISSUER` and `OIDC_AUDIENCE` are set.

   All Entra tenants share one set of signing keys, so a signature alone proves nothing about the tenant. The issuer
   is the configured one, because v1.0 and v2.0 tokens have different issuer forms (see the assumptions below).
3. **Refused, never guessed.** Each of these is a 401, never a default:
   - a missing clearance or unit;
   - groups granting more than one clearance or more than one unit;
   - a value of the wrong type (a clearance or unit must be a non-empty string);
   - a group overage (`_claim_names` naming the groups claim, or `hasgroups: true`), and a groups list longer than
     Entra's cap of 200, which is no token Entra issues;
   - a handling code or role that is empty (`""`, alone or in a list).

   **A token carrying `tid` under the fixed names (the Keycloak handling) is refused**, with fixed words ("token
   carries tid: an Entra ID token is refused without an Entra claim mapping"). Keycloak never emits `tid`. Without
   this refusal, an Entra token on a deployment with the default mapping would skip the tenant, `oid` and scope
   checks, and an Entra app role named `osprey-admin` would make an administrator.

   For two clearances the answer is refusal, not the lowest: `principal_auth` holds no marking scheme to order them,
   and a person in two clearance groups is a directory error. Two groups granting the same value resolve. Handling
   codes from groups are the union of the mapped groups' codes. A code named twice in a claim is kept once, as the
   group path does. An unmapped group grants nothing.
4. **Roles are not read from an Entra token.** Its `roles` are app roles an Entra administrator assigns, and decision
   9 keeps roles in Admin › People. Where Admin › People keeps roles on this profile, with no Keycloak, is P10 part 2
   (an access decision held for the owner).
5. **The default mapping is the fixed names**, so deployments that set nothing behave as before. Three tightenings
   apply to every deployment:
   - a string of handling codes or roles is one value, not its letters;
   - a claim of the wrong type, or an empty code or role, is a 401 instead of being `str()`-ed, dropped or causing
     a 500;
   - a code or role named twice is kept once.
6. **The principal's id.** For an Entra mapping, `Principal.id` is the token's **`oid`**. That is the orchestrator's
   ruling of 11 November 2026, on its own recommendation; the owner may overrule it. The reasons:
   - Entra's `sub` is pairwise per application (ADR-112 Amendment 3's rejected alternatives already say so), so a second
     client id would split one person into two principals;
   - Graph gives `oid`, so Admin › People can assign roles before a person's first sign-in.

   `oid` is unique within a tenant, and the tenant is pinned (point 2), so `oid` alone names one person. A token
   with no `oid`, or one that is not an object id, is refused. For the fixed names (Keycloak), `Principal.id` stays
   `sub`, which PyJWT requires and refuses unless it is a string.
7. **An app-only token is no person.** In Entra mode a token with no delegated `scp`, or with `idtyp: app`, is
   refused.
8. **Who the token was issued to, and for what** (decided by the admin lane; the owner may overrule):
   - **The client is pinned.** A v2.0 token names its client in `azp`, a v1.0 token in `appid`. Whichever is
     present must equal `client_id`, and a token with neither is refused. Without this, any other application in
     the tenant that obtains a token for this API would be a Glass session. Recommended by the orchestrator.
   - **`scp` must include the configured `scope`**, as a whole word of its space-separated list (`access_as_user`
     is not satisfied by `access_as_user_extra`). Any other delegated scope (`User.Read`, `openid` alone) is a token
     meant for something else.
   - **Guest (B2B) accounts are refused**: `acct` of `1` (as a number or as text), or an `idp` present and different
     from the issuer (Entra emits `idp` only when the user is homed in another tenant or provider). An
     intelligence workspace admits members of the client's own directory by default, and admitting a guest is a
     decision for the deployment, not something a token can make. Admitting guests would need a new setting and a
     new amendment. `acct` is an optional claim the app registration must ask for, so `idp` is the check that works
     without configuration.
9. **The settings are checked where they are used.** Group-table keys must be group ids, `groups_claim` must be named,
   and the resolver validates again whatever mapping it is given, because `model_copy` and `model_construct` skip
   validation.

**Assumptions, each to be measured in P10 part 2 against the client's development tenant** (CLAUDE.md rule 15: the
token shapes above are as Microsoft documents them, not yet measured):

- **v1.0 or v2.0 access tokens.** An app registration with `accessTokenAcceptedVersion` null (the default) is issued
  v1.0 access tokens. Their `iss` is `https://sts.windows.net/{tid}/`, not `https://login.microsoftonline.com/{tid}/v2.0`,
  their `aud` may be the `api://` application id URI rather than the client id, and they name the client in `appid`.
  The code takes the issuer and audience from settings and reads `appid`. Test:
  `test_a_real_tenant_token_matches_the_configured_issuer_and_audience`. It puts a real token through the profile's
  `OIDC_ISSUER` and `OIDC_AUDIENCE` and shows it resolves. It is red with the other version's issuer configured.
- **Directory extension names.** In a JWT, an extension attribute is assumed to arrive as
  `extension_<application id without hyphens>_<name>`. Through a claims-mapping policy it may arrive as
  `extn.<name>` instead. The mapping names whatever the real token carries. Test:
  `test_the_real_directory_extension_names_reach_the_mapping`. It takes the names from a real token's keys, maps them
  and shows the principal resolves. It is red with the other naming form.
- **A claims-mapping policy's signing key.** An application with a claims-mapping policy has its tokens signed with an
  app-specific key, published at the JWKS URL with `?appid=<client id>`. `OIDC_JWKS_URL` must then carry that query.
  Test: `test_a_claims_mapping_policy_token_verifies_against_the_app_specific_jwks`. It is red with `?appid=`
  removed.
- **Guests and `acct`.** Test: `test_a_real_guest_token_is_refused`. It shows a real guest's token carries `idp` (and
  `acct` 1 where configured) and is refused, and that a member's token resolves.
- **Access tokens, not ID tokens.** The Glass is assumed to send access tokens for this API. ID tokens carry no `scp`
  and would be refused as app-only (point 7). Test: `test_the_glass_sends_an_access_token_for_this_api`.

**Carried to part 2**, each with its test named in `process/lanes/admin/SERVER_LOG.md`:

- the profile's `claims:` settings, with `tenant_id` and `client_id` required;
- `ApiConfig` and its callers passing the mapping;
- Keycloak not rendered on the profile;
- roles and owner resolution on Entra;
- three readers of `roles` outside `principal_auth`, with no issuer or tenant check. Each comes under the rule or is
  shown not rendered on the profile:
  - `harness/webapp_auth.py:135`;
  - `deploy/superset/superset_config.py:89`;
  - `harness/oidc.py:254`;
- one real token from the client's development tenant, which settles the assumptions above.

Tests: `tests/services/api/test_auth_entra_claims.py`. Planted faults: `process/lanes/admin/P10_P1_RED_RECORD.md`.
