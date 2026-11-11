# Draft · ADR-148, Amendment ‹number to be reserved by the orchestrator› — Entra ID's claims as built (P10 part 1)

*Draft by the admin lane, 11 November 2026, on the test server, for the orchestrator to reserve a number for and place
in `spec/06_DECISIONS.md` (CLAUDE.md rule 11). Not in `spec/` yet because no amendment number is reserved for P10.*

Decision 9 says the claims are mapped, not assumed, by named claim or by Entra group table. Built in
`packages/principal_auth` (`ClaimMapping`, `principal_from_claims`):

1. **One source per claim.** Clearance, organisational unit and handling codes each come from **either** a token claim
   **or** a group table, never both. A setting naming both or neither fails to load, and so does an unknown key or a
   group granting an empty value. Different claims may use different kinds of source.
2. **A mapping other than the fixed names is an Entra mapping, and names its tenant** (`tenant_id`, a GUID). With it
   set, the rules are:
   - the token must carry `oid` and `exp`;
   - its `tid` must equal the tenant;
   - the resolver refuses to start unless `OIDC_ISSUER` and `OIDC_AUDIENCE` are set.
   
   All Entra tenants share one set of signing keys, so a signature alone proves nothing about the tenant. The issuer
   is the configured one, because v1.0 and v2.0 tokens have different issuer forms.
3. **Refused, never guessed.** Each of these is a 401, never a default:
   - a missing clearance or unit;
   - groups granting more than one clearance or more than one unit;
   - a value of the wrong type (a clearance or unit must be a non-empty string);
   - a group overage (`_claim_names` naming the groups claim, or `hasgroups: true`).
   
   For two clearances the answer is refusal, not the lowest: `principal_auth` holds no marking scheme to order them,
   and a person in two clearance groups is a directory error. Two groups granting the same value resolve. Handling
   codes from groups are the union of the mapped groups' codes. An unmapped group grants nothing.
4. **Roles are not read from an Entra token.** Its `roles` are app roles an Entra administrator assigns, and decision
   9 keeps roles in Admin › People. Where Admin › People keeps roles on this profile, with no Keycloak, is P10 part 2
   (an access decision held for the owner).
5. **The default mapping is the fixed names**, so deployments that set nothing behave as before. Two tightenings apply
   to every deployment: a string of handling codes or roles is one value, not its letters, and a claim of the wrong
   type is a 401 instead of being `str()`-ed or causing a 500.
6. `Principal.id` stays the token's `sub`.

Tests: `tests/services/api/test_auth_entra_claims.py`. Planted faults: `process/lanes/admin/P10_P1_RED_RECORD.md`.
