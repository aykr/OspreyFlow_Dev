# P10 part 1 · red record (CLAUDE.md rule 15)

Head `72d87192` on `lane/admin-p10`, after two lane-reviewer rounds (on `0c45089` and on `a30de18`).

Tests are in `OspreyFlow_Build/tests/services/api/test_auth_entra_claims.py`: 66 cases, plus `test_auth.py`'s 11,
which are unchanged. Every case runs through the real `PrincipalResolver.resolve`: a real RS256 signature, a JWKS
served over loopback, and PyJWT's own checks.

**Red before the code.** The test file was written first. It failed at collection with `ImportError: cannot import
name 'ClaimMapping' from 'principal_auth'`.

**Each behaviour red at its real call site.** `p10/p10_plants.py` edits `packages/principal_auth/__init__.py` on the
line where the behaviour lives, runs the cases meant to catch it, then restores the file. The control (the whole
Entra file plus `test_auth.py`, 77 cases) is green before and after. Results by head:

| Head | Plants | Case runs | Result | Output |
| --- | --- | --- | --- | --- |
| `72d8719` (current) | 34 | 59 | all red, none missed | `gates/p10_plants_72d8719.txt` |
| `0c45089` | 16 | | all red | `gates/p10_plants_0c45089.txt` |
| `1d82a72` | 30 | 51 | all red | `gates/p10_plants_1d82a72.txt` |

**Each red is for the reason its case names**, not a message mismatch.

- *Round 1 (the reviewer):* two reds came only from a message mismatch, because the token was still refused by a
  second check. Fixed: each refusal now has a case whose plant makes the token resolve.
- *Round 2 (the plants themselves):* the first run at `2c63e13` left two plants green.
  - `[no-oid]` was still refused by the new `oid` format check.
  - `[numeric-sub]` was still refused by PyJWT, which rejects a non-string `sub`.
  
  Each was a second defence that could never fire on its own. Now `oid` is checked once, by its format check, which
  also refuses an absent `oid`. `sub`'s type is left to PyJWT, with the case kept as proof of PyJWT's refusal.
  `tid` was settled the same way in round 1.
- Where one fault needs two checks removed to show, it is planted as one fault with two edits:
  - another tenant's whole token (issuer and tenant);
  - `both missing [mixed]` (a defaulted claim and a defaulted group).
- The cases that check a group overage, `hasgroups` or a groups claim that is not a list take groups only for the
  handling codes. Under each plant the token resolves, with no codes.
- The wrong-type plants for handling codes and roles end in a `TypeError` (a 500), not a 401. That is the defect the
  cases name.
- The exchange plant maps the exchanged token by the fixed names instead of the deployment's mapping. The exchanged
  token's clearance comes only from its groups, so the case fails because the mapping was not applied.
- The default-names plant goes red at the assertion on the literal names. It no longer fails while building a
  comparison mapping.
- The construction check is also shown red on the three other shapes a second path could take: a qualified call,
  `model_validate`, and a call at module level (`test_the_construction_check_sees_each_other_way_to_build_one`).
