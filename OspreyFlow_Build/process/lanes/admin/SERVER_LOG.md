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

**First code** at `0c45089d`: 37 cases (`test_auth.py`'s 11 unchanged and green; "15" in an earlier
version of this log was wrong) and 16 plants. A preliminary `make test` was started at it and stopped at
about 15% once the review came back, because its fixes changed the files under it. It gave no result.

**Lane-reviewer, round 1 on `0c45089`: do not merge, items 1 to 6 must fix.** All six accepted, fixed at
`1d82a727`:
- (1) An Entra token's `roles` were read as OspreyFlow roles, so an Entra "admin" app role made an
  administrator, and a test asserted it. Now a tenant-bound mapping reads **no** roles (decision 4 below).
- (2) Entra checks hung on a `tenant_id` nothing required. A non-default mapping now needs it, validated as
  a GUID, and every check uses `is_entra`.
- (3) Two reds were only a message mismatch.
- (4) Issuer, audience and expiry were never planted, and the controls covered 25 of 37 cases.
- (5) The evidence did not match the claims. The reviewer read the tree before my `b749463` commit, which
  holds the red record and the plant script. The wrong count is corrected above.
- (6) The decisions were not in `spec/`. They are drafted as `P10_ADR148_AMENDMENT_DRAFT.md`, waiting for a
  number, and the friction row is written.

Also done from the minor items:
- `hasgroups: true` is refused as an overage.
- A numeric clearance is refused, no longer `str()`-ed.
- A group may not grant `""`.
- A role string is one role.
- The default mapping's tightened types are tested.
- The overage endpoint now uses Entra's documented `graph.windows.net` form.

Not changed:
- The settings' inner dicts can still be mutated (minor; the mapping is built once from settings).
- The owner-exchange case uses the Keycloak-style exchange fixture. It proves the one construction path,
  not Entra behaviour; Entra has no such exchange, and how the scheduler resolves owners on Entra is P10
  part 2's question below.

**Built** at `1d82a727`: 54 cases plus `test_auth.py`'s 11, and 30 plants with 51 case runs, all red
(`P10_P1_RED_RECORD.md`, `gates/p10_plants_1d82a72.txt`). `ruff check`, `ruff format --check` and `mypy`
are clean on the branch's diff (mypy also over `services/api/auth.py` and `harness/verify.py`). The gates
follow below.

**Decisions taken** (the owner may overrule):
1. *Groups granting more than one clearance: the lowest, or refused?* `spec/` is silent. **Refused** (and the
   same for two organisational units): `principal_auth` holds no marking scheme to order clearances by, so
   "the lowest" would mean importing the scheme into the sign-in path or guessing; a person in two clearance
   groups is a directory error the operator should see. Two groups granting the *same* value resolve.
   Handling codes from groups are the **union** of the mapped groups' codes (each group is a grant).
2. *One field from both a claim and a group table?* **No: exactly one source per field**, validated (a
   setting naming both, or neither, fails to load; so does an unknown key such as `clearence`). Different
   fields may use different kinds (the "mixed" mapping).
3. *What marks an Entra mapping?* `tenant_id` (a GUID), **required for any mapping other than the fixed
   names**: a Keycloak deployment maps onto the fixed names with protocol mappers, so a changed name means
   Entra. With it set the token must carry `oid` and `exp`, `tid` must equal the tenant, and a resolver
   whose `OIDC_ISSUER` or `OIDC_AUDIENCE` is unset refuses to be built.
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
7. *Roles from an Entra token?* **None** (the strict option, after the review). Its `roles` are app roles an
   Entra administrator assigns; decision 9 keeps roles in Admin › People. Until part 2 gives roles a home on
   this profile, an Entra principal has no OspreyFlow role, so it can sign in but holds no right.

**Questions held for the orchestrator** (none blocks this part):
- **Roles on Entra (access, Prompt L's first kind; P10 part 2).** Today Admin › People writes Keycloak user
  attributes (`services/api/identity_admin.py`). With no Keycloak on this profile, where are roles kept: in
  Postgres keyed by `sub` or `oid` and joined in at resolution, or as Entra app roles read by name through a
  mapping, which would hand role assignment to the client's Entra administrators? Decision 7 above chooses
  neither and grants none. The same question covers the scheduler's owner exchange (ADR-043), since Entra has
  no impersonation exchange, and `identity_admin`'s calls on this profile.
- **Spec gap (rule 11).** These decisions belong in an amendment to ADR-148. Amendment 5 is P7b's, and I
  have no reserved number, so the text is drafted in `P10_ADR148_AMENDMENT_DRAFT.md`. **Request:** reserve
  ADR-148 Amendment 6 (or the next free number) for P10.

**Left for after P7 merges** (P7's files): the `cloud-platform` profile's claim settings and their render
into the Conduit's environment (`harness/` profile and `render.py`'s profile entry, platform's, by diff),
`services/api/config.py` reading them into `ApiConfig` and `run_resources.py` passing the mapping to
`PrincipalResolver`; and "Keycloak not rendered on this profile".
