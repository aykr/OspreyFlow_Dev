# P10 part 2 · red record (CLAUDE.md rule 15)

Branch `lane/admin-p10p2`. The plants harness is `p10p2/p10p2_plants.py`. Each plant edits the real code where the
behaviour lives, runs the cases meant to catch it, expects them red, and restores the file. The shared files' diffs
(`readers.diff`, `render.diff`, `glass-sign-in.diff`) are applied first, so a fault in them is planted where it will
merge, and reverted at the end.

What counts as red is as in part 1's harness:
- a planted Python source that does not compile is a harness fault;
- a pytest case is red only on exit 1 with "failed" and no "error";
- a vitest case is red only on exit 1 with "failed" and no collection error.

| Head | Plants | Case runs | Result | Output |
| --- | --- | --- | --- | --- |
| `96d0513` | 39 (2 live, run under the lease) | 52 | 52 red, 0 missed, 0 harness faults | `gates/p10p2_plants_96d0513.txt` |
| `cbe0da5` (the harness uncommitted) | 38 | 51 | 50 red, **1 missed** (below) | — |

**The one missed, and what it found.** Removing `resolve`'s refusal of an Entra mapping left
`test_the_synchronous_path_refuses_an_entra_mapping` green. The construction path's own guard (no stored person)
refused the same token by another route, so the case could not tell the first guard was gone. The fix is a case for
the second guard alone (`test_the_construction_path_refuses_an_entra_principal_without_its_stored_person`). Each guard
now has its own plant, and the synchronous case's plant removes both.

**Red before the code**, where the cases came first:
- `test_service_identity_entra.py`: 18 failed before `service_identity.py` changed
  (`p10p2/service_identity_red_before_code.txt`).
- The Glass's App cases: all three red against main's `App.tsx` and `userManager.ts`, each failing on the token's
  `SECRET` shown as the clearance (`p10p2/glass_red_against_main.txt`).
- The source check that no token role or access claim is read in the Glass finds main's `userManager.ts`.

**Each red is for the reason its case names.**
- The app-only cases (CARRIES 180) are red by the app-only words. The scope check is now typed on its own, so a token
  without `scp` reaching it is refused for the scope, never an `AttributeError`. That makes the `pytest.raises(match=
  "app-only")` fail as a failure.
- The guest plants restore part 1's string comparison, and separately admit an `idp` naming no Entra issuer. Each is
  red on its own case: the member's v1 form, and the Microsoft account and federated forms.
- The wiring plant leaves `client_id` out of the rendered claim mapping. The wiring test, reading the render's own
  environment through `ClaimMapping.from_env`, is red.

**Not planted, and why.**
- The policy check's group-0 allowance, and the identity door's absence in the templated chart. Those tests need
  `helm`, which this Mac has not; they run in `make -k ci` on the server.
- The keyboard step (`admin.spec.ts`). It runs in a browser slot, with the registry line applied.
