# Admin lane · server log · 11 November 2026 (laptop offline, about 07:15 to 11:00 UTC)

Working on the test server in `~/osprey-srv/admin`, no orchestrator to message. Order (the owner's swap):
P10's first part on `lane/admin-p10` (from main `459ae1d`), then T1 part 5 on `lane/admin-t1p5`.

## P10 part 1 · Sign-in claims from Entra ID (ADR-148 decision 9)

**Plan (written before code).** Spec read: ADR-148 decision 9 ("mapped, not assumed … one
claims-construction path stays; only its source names become settings; roles stay assigned in Admin ›
People"), ADR-142 Amendment 8 point 3 (shared render files are platform's; P10 sends diffs),
`01_DOMAIN_MODEL.md` §2.2 (unrecognised clearance is default-deny), CLAUDE.md rules 3, 4, 12, 15.

- `OspreyFlow_Core/packages/principal_auth/__init__.py`: a frozen settings model, `ClaimMapping`, naming for
  each of clearance, organisational unit and handling codes **either** a token claim (an Entra directory
  extension attribute) **or** a table from group id to value, plus the groups claim's name, the claims a
  token must carry (`oid`, `tid` for Entra) and the tenant id. Its default is today's fixed names, so every
  existing call site and test is unchanged. One function, `principal_from_claims(claims, mapping)`, builds
  every `Principal`; `PrincipalResolver.resolve` (and so `resolve_for_owner`) calls it and nothing else.
- Tests first, in a new file `OspreyFlow_Build/tests/services/api/test_auth_entra_claims.py`, through the real
  `PrincipalResolver.resolve` with RS256 tokens shaped as Entra v2.0 issues them (synthetic GUIDs only).
  Each refusal planted at its real call site and shown red.

**Built** at `0c45089d` (37 cases; `test_auth.py`'s 15 unchanged and green; 16 plants red,
`P10_P1_RED_RECORD.md`). `ruff check`, `ruff format --check` and `mypy` clean on the branch's own diff
(`packages/principal_auth`, the new test file; mypy also over `services/api/auth.py`, `harness/verify.py`).

**Decisions taken** (the owner may overrule):
1. *Groups granting more than one clearance: the lowest, or refused?* `spec/` is silent. **Refused** (and the
   same for two organisational units): `principal_auth` holds no marking scheme to order clearances by, so
   "the lowest" would mean importing the scheme into the sign-in path or guessing; a person in two clearance
   groups is a directory error the operator should see. Two groups granting the *same* value resolve.
   Handling codes from groups are the **union** of the mapped groups' codes (each group is a grant).
2. *One field from both a claim and a group table?* **No: exactly one source per field**, validated (a
   setting naming both, or neither, fails to load; so does an unknown key such as `clearence`). Different
   fields may use different kinds (the "mixed" mapping).
3. *What marks an Entra mapping?* `tenant_id`. With it set the token must carry `oid`, `tid` and `exp`, `tid`
   must equal the tenant, and a resolver whose `OIDC_ISSUER` or `OIDC_AUDIENCE` is unset refuses to be built.
   The issuer itself stays the configured `OIDC_ISSUER` (v1.0 and v2.0 tokens have different issuer forms;
   the profile names the one its app registration issues).
4. *Group overage* (Entra omits `groups` past 200 in a JWT and names a Graph source in `_claim_names`):
   **refused** with a message naming the overage, never read as "no groups". No Graph call is made.
5. *Value types.* A clearance or unit claim must be a single non-empty value (a list, object, boolean or
   `""` is refused); handling codes are a list of strings or one string as **one** code. This also applies
   to the default mapping, and tightens two old behaviours: `list("RS")` used to grant codes `R` and `S`, and
   a list clearance used to be `str()`-ed. No existing test relied on either.
6. `Principal.id` stays the token's `sub` (Entra's pairwise subject for this app), unchanged; `oid` is
   required but not used as the id.

**Questions held for the orchestrator** (none blocks this part):
- **Roles on Entra.** ADR-148 decision 9 keeps roles "assigned in Admin › People as today", but today that
  writes Keycloak user attributes (`services/api/identity_admin.py`), and with no Keycloak the resolver still
  reads the token's `roles` claim, which in an Entra token carries the app roles an Entra administrator
  assigns. Unchanged here (not loosened), but a P10 part 2 decision: where roles live on this profile, and
  whether the `roles` claim is read at all there. This is an access question (Prompt L's first kind).
- **Spec gap (rule 11).** Decisions 1 to 5 belong in an amendment to ADR-148; I have no reserved number, so
  the text waits for one (requested here).

**Left for after P7 merges** (P7's files): the `cloud-platform` profile's claim settings and their render
into the Conduit's environment (`harness/` profile and `render.py`'s profile entry, platform's, by diff),
`services/api/config.py` reading them into `ApiConfig` and `run_resources.py` passing the mapping to
`PrincipalResolver`; and "Keycloak not rendered on this profile".
