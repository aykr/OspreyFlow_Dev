# P10 part 1 · red record (CLAUDE.md rule 15)

Head `1d82a727` on `lane/admin-p10` (the lane-reviewer's first-round fixes on `0c45089d`). Tests in
`OspreyFlow_Build/tests/services/api/test_auth_entra_claims.py` (54 cases, plus `test_auth.py`'s 11 unchanged), all
through the real `PrincipalResolver.resolve` (real RS256, loopback JWKS, PyJWT's own checks).

**Red before the code.** The file was written first and failed at collection with `ImportError: cannot import name
'ClaimMapping' from 'principal_auth'`.

**Each behaviour red at its real call site.** `p10/p10_plants.py` edits `packages/principal_auth/__init__.py` on the
line where the behaviour lives, runs the cases meant to catch it, and restores the file. The control is the whole Entra
file plus `test_auth.py` (65 cases), green before and after. **30 plants, 51 case runs, all red, none missed:**
`gates/p10_plants_1d82a72.txt`. The first round's output (16 plants at `0c45089`) is kept as
`gates/p10_plants_0c45089.txt`.

**Each red is for the reason its case names, not a message mismatch.** In the first round two reds were only a
message mismatch: `[no-tid]` was still refused by the tenant check, and `both missing [mixed]` was still refused for
the unit. The lane-reviewer found both. Fixed:
- `tid` is checked once, by the tenant check (PyJWT no longer also requires it). Under that check's plant, a token
  with no `tid` or another tenant's `tid` now resolves.
- `[mixed]` was replaced in the claim-default plant by a mixed-mapping token that has the unit group but no clearance
  attribute. Under the plant it resolves.
- The overage, `hasgroups` and groups-not-a-list cases take groups only for handling codes. Under each plant the
  token resolves, with no codes.
- The checks PyJWT does (issuer, audience, expiry) are each planted off at the resolver's `options`.
- Another tenant's whole token (its issuer and its `tid` together, the shape Entra really issues) is defended twice,
  so it is planted as one fault with both checks removed. Under it the token resolves.
- Under the wrong-type plants for handling codes and roles the token now crashes with a `TypeError`, not a 401, which
  is the defect the case names.
