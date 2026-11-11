# P10 part 1 · red record (CLAUDE.md rule 15)

Head `54c1700e` on `lane/admin-p10`, after two lane-reviewer rounds (on `0c45089` and on `a30de18`) and the
orchestrator's review round 1 (on `5b0e6e1`).

Tests are in `OspreyFlow_Build/tests/services/api/test_auth_entra_claims.py`: 93 cases, plus `test_auth.py`'s 11,
which are unchanged. Every case that reads a token runs through the real `PrincipalResolver.resolve`: a real RS256
signature, a JWKS served over loopback, and PyJWT's own checks.

**Red before the code.** The test file was written first. It failed at collection with `ImportError: cannot import
name 'ClaimMapping' from 'principal_auth'`.

**Each behaviour red at its real call site.** `p10/p10_plants.py` edits `packages/principal_auth/__init__.py` on the
line where the behaviour lives, runs the cases meant to catch it, then restores the file. The control (the whole
Entra file plus `test_auth.py`, 104 cases) is green before and after. Results by head:

| Head | Plants | Case runs | Result | Output |
| --- | --- | --- | --- | --- |
| `54c1700` (current) | 49 | 89 | 89 red, 0 missed, 0 harness faults | `gates/p10_plants_54c1700.txt` |
| `72d8719` | 34 | 59 | 56 failed; **3 runs (2 plants) were import errors, not reds** (below) | `gates/p10_plants_72d8719.txt` |
| `1d82a72` | 30 | 51 | all "failed", no import error; the lax harness | `gates/p10_plants_1d82a72.txt` |
| `0c45089` | 16 | | all "failed", no import error; the lax harness | `gates/p10_plants_0c45089.txt` |

**The harness itself was wrong until `54c1700` (the orchestrator's review round 1, item 1).** The tenant plant matched
the 8-space `if claims.get("tid") != mapping.tenant_id:` and replaced it with a 4-space `if False:`. That made
`principal_auth` fail to import. Every case under it reported "1 error", and `run()` counted any non-zero exit as
caught. So "a missing or other tenant's tid accepted" and "another tenant's whole token" (3 case runs) were never shown
red. The tenant pin had no red until this head. Fixed:
- a plant that turns a condition off is built by `off(line)`, which keeps the matched line's own indentation;
- the planted source is `compile()`d before it is written, and a planted source that does not compile is a harness
  fault;
- a case is red only on exit 1 with "failed" and no "error" in pytest's summary. Exit 2 or 5, or 1 with "error", is a
  harness fault.

The fix is shown red itself: `p10_plants.py --self-test` (`gates/p10_plants_selftest_54c1700.txt`) shows each of
these is a fault: "1 error", "1 failed, 1 error", exit 2 and exit 5. It also shows the `72d8719` tenant plant does not
compile, and that `off` keeps 8 spaces and `elif`. Earlier heads' records used the lax harness. Their other reds read
"1 failed", but only `54c1700`'s run is the evidence for this head.

**Each red is for the reason its case names**, not a message mismatch.

- *Lane-reviewer round 1:* two reds came only from a message mismatch, because the token was still refused by a
  second check. Fixed: each refusal now has a case whose plant makes the token resolve.
- *Lane-reviewer round 2 (the plants themselves):* the first run at `2c63e13` left two plants green.
  - `[no-oid]` was still refused by the new `oid` format check.
  - `[numeric-sub]` was still refused by PyJWT, which rejects a non-string `sub`.

  Each was a second defence that could never fire on its own. Now `oid` is checked once, by its format check, which
  also refuses an absent `oid`. `sub`'s type is left to PyJWT, with the case kept as proof of PyJWT's refusal.
  `tid` was settled the same way in round 1.
- *Orchestrator round 1, new behaviour, each with its own plant:*
  - **id by `oid`** (item 3). Planted as `id=sub`, red on the two-`sub`s case. The reverse plant (keying a Keycloak
    token by an `oid` it carries) is red on `test_a_keycloak_principal_is_still_keyed_by_sub`.
  - **`tid` under the Keycloak handling** (item 4). Planted with the `elif` off, the default-mapping token carrying
    `roles: ["osprey-admin"]` resolves, for both our tenant and another one.
  - **The client pin.** Planted off, red on all four. Planted as "`azp` only", red on the token whose `appid` names
    another client and on the v1.0 control.
  - **Scope.** Planted off, red on three. Planted as a substring match, red on `access_as_user_extra`.
  - **Guests.** Planted off, red on three. Planted as "`acct == 1` only", red on `acct: "1"`.
  - **Settings.** The `client_id` and `scope` setting checks are planted.
  - **Lists.** The 200-group cap, the empty-code refusal and the de-duplication are planted. "One clearance group,
    two values" is planted by widening the table's type.
- Where one fault needs two checks removed to show, it is planted as one fault with two edits:
  - another tenant's whole token (issuer and tenant);
  - `both missing [mixed]` (a defaulted claim and a defaulted group).
- The cases that check a group overage, `hasgroups`, a groups claim that is not a list, or the 200 cap take groups
  only for the handling codes. Under each plant the token resolves.
- Some plants fail with an exception instead of a refusal, and that is the defect the cases name:
  - The wrong-type plants for handling codes and roles end in a `TypeError` (a 500), not a 401.
  - So does the app-only plant on its two no-`scp` cases: an `AttributeError` at the scope check.
  - Its `idtyp: app` case, which carries a valid `scp`, resolves.
- The exchange plant maps the exchanged token by the fixed names instead of the deployment's mapping. The exchanged
  token's clearance comes only from its groups, so the case fails because the mapping was not applied.
- The default-names plant goes red at the assertion on the literal names.
- The construction check is also shown red on the three other shapes a second path could take: a qualified call,
  `model_validate`, and a call at module level (`test_the_construction_check_sees_each_other_way_to_build_one`).
