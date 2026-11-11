# P10 part 1 · red record (CLAUDE.md rule 15)

Commit `0c45089d` on `lane/admin-p10`. Tests in `OspreyFlow_Build/tests/services/api/test_auth_entra_claims.py`
(37 cases), all through the real `PrincipalResolver.resolve` (real RS256, loopback JWKS, PyJWT's checks).

**Red before the code.** The file was written first and failed at collection: `ImportError: cannot import name
'ClaimMapping' from 'principal_auth'`.

**Each behaviour red at its real call site.** `process/lanes/admin/p10/p10_plants.py` edits
`packages/principal_auth/__init__.py` at the line the behaviour lives on, runs the cases that should catch it,
and restores the file. 16 plants, 27 case runs, every one red; the control green before and after.
Output: `gates/p10_plants_0c45089.txt`.

| Plant | Caught by |
| --- | --- |
| groups granting two clearances or units: any one picked | two clearances; two units; the owner exchange |
| a missing claim-sourced clearance defaulted to cleared | both missing [extension], [mixed]; default mapping ignores Entra attributes |
| a missing group-sourced value defaulted to cleared | both missing [groups]; missing clearance; missing unit; unmapped group |
| an unmapped group grants a code | unmapped group grants nothing |
| a group overage read as no groups | overage refused |
| a groups claim that is not a list | groups not a list |
| another tenant's `tid` accepted | entra refusals [other-tenant] |
| `oid`, `tid`, `exp` not required | entra refusals [no-oid], [no-tid], [no-exp] |
| an Entra mapping on a resolver not checking issuer and audience | refused at construction |
| one handling code split into its letters | single-valued attribute is one code |
| handling codes of the wrong type passed through | wrong type refused |
| a list or empty clearance accepted | empty refused; not a string refused |
| a source with both a claim and a table, or neither | exactly one [neither], [both] |
| a misspelt setting ignored | unknown key refused |
| the exchange builds its principal by a second path | the owner exchange |
| a second `Principal(` in `principal_auth` | one construction |

**Where a red rests on the message, not on a resolved principal** (rule 15's warning, said rather than hidden):
- `[no-tid]` under the "not required" plant: the token is then refused by the tenant check ("another tenant"),
  not by PyJWT, so the case goes red on its `match="tid"`. `tid` is defended twice; removing both is two plants.
- `both missing [mixed]` under the claim-default plant: the unit (from groups) is still missing, so the token is
  refused for the unit and the case goes red on `match="clearance"`. `[extension]` under the same plant goes red
  because the token resolves, which is the reason the case names.
- The overage and groups-not-a-list cases were rebuilt so the plant makes the token **resolve** (groups feed only
  the handling codes), after a first version that would have been refused for a missing unit anyway.
