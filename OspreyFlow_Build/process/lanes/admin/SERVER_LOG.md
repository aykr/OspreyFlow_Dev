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

At `1d82a727`: 54 cases and 30 plants. The gates were started at `a30de18` and stopped when round 2 came
back, because its fixes changed the files under them. They gave no result, and their partial outputs were
deleted.

**Lane-reviewer, round 2 on `a30de18`: do not merge until items 1 to 5 are fixed.**
- (1) `model_copy` and `model_construct` skipped the validators, so a copy of the default mapping with a
  group source was handled as Keycloak. Fixed: `PrincipalResolver` validates the mapping again from plain
  data, which also detaches it from later changes to the inner dicts. Tested for both shapes and planted.
- (2) An Entra deployment can send the fixed claim names, and without `tenant_id` it is handled as
  Keycloak. Carried to part 2 with its test named (below); the profile is P7's file.
- (3) Not in `spec/`: still waits for a reserved number (below).
- (4) No gate result at the head yet: the gates run below, at the final head.
- (5) "Mapped by settings" is only half done: recorded as carried items with named tests (below).

Minor items, all done except one:
- (6) An app-only token (no `scp`, or `idtyp: app`) is now refused as no person.
- (7) The test docstring says the token shapes are documented, not measured.
- (8) `oid` must be an object id; `sub`'s type is PyJWT's own check (shown by the plants).
- (9) The exchange and default-name plants now fail for their stated reasons.
- (10) The construction check now sees a qualified call, `model_validate`, `model_construct` and a call at
  module level, and is shown red on each.
- (11) `[mixed]` is planted.
- (12) Group-table keys must be group ids, and `groups_claim` must be named.
- (13) Codes and roles share one list reader.
- (14) Not changed here: carried to part 2.

*(Superseded: the record for the head is `P10_P1_RED_RECORD.md` at `54c1700`.)* **Built** at `72d87192`: 66 cases plus `test_auth.py`'s 11 (unchanged, green); 34 plants with 59 case
runs, all red, none missed (`P10_P1_RED_RECORD.md`, `gates/p10_plants_72d8719.txt`). `ruff check`,
`ruff format --check` and `mypy` are clean on the branch's diff (mypy also over `services/api/auth.py` and
`harness/verify.py`). The gates at `5b0e6e1` are recorded below; the orchestrator's review round 1 found them run
without a lease and short of two resolver users, and that the tenant plant was never red (see the round 1 section
at the end).

**Gates at `5b0e6e1`** (main `459ae1d` unchanged, so no rebase). Both were run here directly, without a lease, on
the offline ports, as the brief says.
- **`make test`** (`gates/p10_5b0e6e1.test.txt`): 10,894 passed, 2 failed, 13 skipped, in 1,619 s (serial). Both
  failures come from the environment, and neither test imports `principal_auth`:
  - `test_valkey_config.py::test_the_deployments_own_valkey_is_reached_plainly` reads `VALKEY_PORT=59993` from
    the offline-port environment (got 59993, expected 6379). Part 4's handoff names this case (it must clear
    `VALKEY_DB`/`VALKEY_PORT`).
  - `test_webapp_preflight.py::test_gpu_is_skipped_on_this_platform_never_shown_as_a_pass`: this server has a GPU,
    so the preflight reported `pass` instead of `skip`.
  
  `live-collect` and `test-js` did not run, because make stops at the first failed recipe line.
  - `live-collect` was then run on its own and passed (`gates/p10_5b0e6e1.live-collect.txt`).
  - `test-js` was not run. The diff touches no JavaScript.
- **`make -k ci`** (`gates/p10_5b0e6e1.ci.txt`): one target failed. `trivy-image-workspace` found two HIGH CVEs in
  the nginx base image's `libxslt` 1.1.43-r3, fixed upstream in r4 (CVE-2026-87636, CVE-2026-9947). The image's
  layers were all cached, and the P10 diff touches neither the workspace nor its Dockerfile. Every other target
  passed: lint, typecheck, the other image scans, `harness-a11y`, every check and the bundle. `opentofu-check`'s
  `tofu init` rewrote three `.terraform.lock.hcl` files; they were restored and are not committed.
- **Not run:** a live check. P10 part 1 adds no live file and touches no store; `test_route_rights.py` is
  unaffected (no route changed).

**P10 part 1 built at `5b0e6e1`.** It reached built after two lane-reviewer rounds, with every finding fixed or
carried with its test named. It is an access step, so it keeps two review rounds with the orchestrator when they
are back (ADR-142 Amendment 8, point 7). Before ready-to-merge, part 1 needs:
- the orchestrator's review;
- an ADR-148 amendment number;
- the owner's answer on roles. That answer is for part 2, but it bears on whether part 1's "no roles on Entra"
  stands.

The branch is left as gated.

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
6. *(Superseded by the orchestrator's ruling, Amendment 6 point 6: `Principal.id` is `oid`.)* `Principal.id` stays
   the token's `sub` (Entra's pairwise subject for this app), unchanged; `oid` is required but not used as the id.
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

8. *App-only tokens.* In Entra mode a token with no delegated `scp`, or with `idtyp: app`, is refused. A
   daemon's client-credentials token is no person. If the profile's Glass sends ID tokens rather than
   access tokens, part 2 revisits this (ID tokens carry no `scp`).

**P10 part 2 · carried items, each with the test that must fail first** (left for after P7 merges, because
the files are P7's or need its profile). Until these land, P10 is not done: today no production caller
passes a mapping, so every deployment runs the fixed names.
1. **The profile's claim settings.** The `cloud-platform` profile's settings carry a `claims:` block
   (`ClaimMapping`'s fields), **with `tenant_id` required**, rendered into the Conduit's environment. This
   needs `harness/` profile and `render.py`'s profile entry, which are platform's, so it goes as a diff.
   Test: `test_the_cloud_platform_profile_refuses_to_render_without_a_tenant` (red with the tenant removed).
   This closes review round 2's item 2: an Entra deployment can never run under the Keycloak handling.
2. **`ApiConfig` gains `oidc_claim_mapping`**, read from that environment and validated at start (a bad
   mapping stops the Conduit; it is never silently defaulted). `run_resources.py:302` and
   `harness/verify.py:65` pass it to `PrincipalResolver`. Test:
   `test_a_rendered_claim_mapping_reaches_the_resolver`: a settings value in, an Entra token through
   `app.state.principal_resolver`, red with the pass-through removed.
3. **Keycloak not rendered on this profile.** Test: the rendered profile holds no Keycloak workload,
   and no `OIDC_*` value points at one.
4. **Roles on Entra, and the scheduler's owner resolution.** See the access question above.
   `harness/oidc.py:254` also reads `roles` straight from the ID token, outside `principal_auth` (review
   round 2, item 14). It must come under the same rule, or be shown not to run on this profile.
5. **A real token.** Once the client's development tenant exists, one real token is put through
   `principal_auth`, so the assumed shapes are measured (rule 15).

## P10 part 1 · the orchestrator's review, round 1 of 2, on `5b0e6e1`: not mergeable, fixed in one pass

Fixed against the review's numbers (ADR-142 Amendment 6: one pass, each refusal red first at its real call site):

1. **Blocker: the tenant pin had never been red.** The tenant plant replaced an 8-space `if` with a 4-space one, so
   `principal_auth` failed to import, and `run()` counted "1 error" as caught (`gates/p10_plants_72d8719.txt`
   lines 16, 17 and 22). Fixed in `p10/p10_plants.py` at `54c1700`:
   - `off(line)` keeps the matched line's own indentation;
   - every planted source is `compile()`d first;
   - only exit 1 with "failed" and no "error" counts as red. Exit 2 or 5, or "error", is a harness fault.

   `--self-test` shows each rule red, and shows that the `72d8719` plant does not compile
   (`gates/p10_plants_selftest_54c1700.txt`). **All plants re-run at `54c1700`: 49 plants, 89 case runs, 89 red,
   0 missed, 0 harness faults**, with controls of 104 cases green before and after (`gates/p10_plants_54c1700.txt`).
2. **Gates at the reviewed head: NOT RUN, blocked by the environment.** `stack_lease.sh offline admin -- make -k test`
   failed before running anything: `ssh: Could not resolve hostname ospreyflow-test`. This session runs on that
   server, which has no `~/.ssh/config`, so `lane_stack_hosts.tsv`'s alias does not resolve here. The documented
   override (`OSPREY_OFFLINE_HOST=localhost`) needs an approval this session was not given. Running the gates
   directly, without the lease, is what the review rejected, so I did not.
   - **Pre-check only, not a gate** (run directly on the closed ports at `ba183a9`): 205 passed over these files:
     - `test_websocket_auth`, `test_principal_precheck_reads`, `test_service_identity_and_rollup` and
       `tests/harness/test_organisation_sign_in`;
     - `test_run_resources`, `test_studio_roles` and `test_drawn_watch_alerts`;
     - `test_auth` and `test_auth_entra_claims`.
   - `make test` ignores two resolver users, so they need their own recorded runs:
     - `test_revoked_principal_precheck.py` needs a real Keycloak: `make idp-test`, a throwaway on 8082;
     - `test_evaluation.py` needs a leased stack: `stack_lease.sh remote admin -- …`.
   - **Request to the orchestrator:** make offline runs reachable from this server (an alias or
     `OSPREY_OFFLINE_HOST`), or approve the override. Then, at one head, run `make -k test`, `make -k ci`,
     `make idp-test` and a leased run of `test_evaluation.py`.
   - "The gates follow below" above is corrected.
3. **The principal's id is `oid`** (the orchestrator's ruling; the owner may overrule). For an Entra mapping,
   `Principal.id` is `oid`, refused if absent or not an object id, and unique within the pinned `tid`. Keycloak keeps
   `sub`. Decision 6 above is superseded. Tests:
   - `test_an_entra_principal_is_keyed_by_oid_not_its_pairwise_sub` (two `sub`s, one principal);
   - `test_a_keycloak_principal_is_still_keyed_by_sub`.

   Each is red under its plant.
4. **An Entra token under the Keycloak handling.** Without an Entra mapping, a token carrying `tid` is refused with
   fixed words: "token carries tid: an Entra ID token is refused without an Entra claim mapping".
   Test: `test_an_entra_token_under_the_keycloak_handling_is_refused[our-tenant|other-tenant]`, a default-mapping
   token with `roles: ["osprey-admin"]`. Planted.
5. **The amendment** is retitled "ADR-148, Amendment 6 (11 November 2026)" (`P10_ADR148_AMENDMENT_DRAFT.md`), and 3,
   4, 7 and 8 are applied to it. It stays here until merge.
6. **Carried into part 2, each with its named test.** Each test must fail first, or the reader is shown not rendered
   on the `cloud-platform` profile. No such profile exists on this branch; it is P7's.
   - `harness/webapp_auth.py:135` (`require_admin_role` reads `roles` with no issuer or `tid` check):
     `test_the_harness_admin_check_refuses_an_entra_token_with_an_admin_app_role`;
   - `deploy/superset/superset_config.py:89` (`role_keys` from `claims.get("roles")`):
     `test_superset_reads_no_role_keys_from_an_entra_token`;
   - `harness/oidc.py:254`: `test_the_harness_sign_in_reads_no_roles_from_an_entra_id_token`.
7. **Assumptions written into the draft**, each with a part 2 test against the client's tenant:
   - v1.0 against v2.0 access tokens: `test_a_real_tenant_token_matches_the_configured_issuer_and_audience`;
   - `extn.<name>` against `extension_<appid>_<name>`: `test_the_real_directory_extension_names_reach_the_mapping`;
   - a claims-mapping policy's `?appid=` JWKS: `test_a_claims_mapping_policy_token_verifies_against_the_app_specific_jwks`;
   - also `test_a_real_guest_token_is_refused` and `test_the_glass_sends_an_access_token_for_this_api`.

   The code already takes the issuer and audience from settings and reads v1.0's `appid`.
8. **Decided, built and logged in the draft** (point 8). Each is planted, and each has a control that resolves:
   - **`azp`/`appid` pinned** to a new required setting `client_id`, the Glass's app registration. Whichever field
     is present must match, and a token with neither is refused.
   - **Guests refused**: `acct` 1 (a number or text), or an `idp` different from `iss`.
   - **`scp` must include the configured `scope`** (default `access_as_user`), as a whole word.
9. **Bounds:**
   - a groups list longer than 200 is refused;
   - a handling code or role that is `""`, alone or in a list, is refused;
   - repeats are kept once, as the group path does. This also applies to the Keycloak mapping and is logged in the
     draft;
   - one clearance or unit group granting two values fails to load
     (`test_one_group_cannot_grant_two_clearances_or_units`).
10. **Friction fragment** updated to the re-run's figures (49 plants, 89 runs, 104 control cases).

`ruff check`, `ruff format --check` and `mypy` (`principal_auth`, `services/api/auth.py`, `harness/verify.py`) are
clean on the diff. Commits:
- `5b03c0d`: the code and tests, 93 Entra cases;
- `54c1700`: the harness;
- `ba183a9`: the records.

**P10 part 1 built at `ba183a9`** (code at `5b03c0d`), with item 2's gates outstanding for the environmental reason
above. Waiting for round 2 of the orchestrator's review. Nothing of mine is running.
