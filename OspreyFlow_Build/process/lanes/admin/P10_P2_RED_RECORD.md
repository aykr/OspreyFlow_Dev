# P10 part 2 · red record (CLAUDE.md rule 15)

Branch `lane/admin-p10p2`. The plants harness is `p10p2/p10p2_plants.py`. Each plant edits the real code where the
behaviour lives, runs the cases meant to catch it, expects them red, and restores the file. The shared files' diffs
(`readers.diff`, `render.diff`, `glass-sign-in.diff`, and since the review of 3848c32 `runbook.diff`) are applied first, so a fault in them is planted where it will
merge, and reverted at the end.

What counts as red is as in part 1's harness:
- a planted Python source that does not compile is a harness fault;
- a pytest case is red only on exit 1 with "failed" and no "error";
- a vitest case is red only on exit 1 with "failed" and no collection error.

| Head | Plants | Case runs | Result | Output |
| --- | --- | --- | --- | --- |
| `d994612` (the head after the orchestrator's review of 3848c32, on main 1cbc164; the code as 87503fe) | 76: 68 offline, 8 live | 88 offline + 10 live | 98 red, 0 missed, 0 harness faults | `gates/p10p2_plants_d994612.txt`; the live ten under admin's lease on stack c at 87503fe, `gates/p10p2_live_targeted_87503fe.txt` |
| `cc684ec` (on L1.9 part 2's main) | 52: 49 offline, 3 live | 68 offline + 3 live | 71 red, 0 missed, 0 harness faults | `gates/p10p2_plants_cc684ec.txt`; the live three under the lease at 2516c4b, `gates/p10p2_live_targeted_2516c4b.txt` |
| `641c403` | 52: 49 offline, 3 live | 68 offline + 3 live | 71 red, 0 missed, 0 harness faults | `gates/p10p2_plants_641c403.txt`; the live three under the lease at 302cf3e, `gates/p10p2_live_plants_302cf3e.txt` |
| `19126d8` | 51 (after the lane review's fixes) | 68 offline | 68 red | `gates/p10p2_plants_19126d8.txt` |
| `96d0513` | 39 (2 live, **not run**) | 52 offline | 52 red; the two live plants were not run here, though this table first said they were (the lane-reviewer's finding 2) | `gates/p10p2_plants_96d0513.txt` |
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

**The live plants** (the store's tenant in every read, the socket's read, the first administrators seeded once) ran
under admin's lease on stack b at 0691cde, bbd5721 and 302cf3e, red each time.

**Not planted, and why.**
- The policy check's group-0 allowance, and the identity door's absence in the templated chart: their tests need
  `helm`, which this Mac has not. They pass in `make -k ci` on the server at 017350d (`gates/017350d.ci.txt`), and
  `test_a_supplementary_group_outside_its_allowance_is_refused` plants group 0 on a workload and is red there by
  design; no plant of the allowance itself was run.
- The keyboard step (`admin.spec.ts`). It runs in a browser slot, with the registry line applied.

**The review of 3848c32's plants** (24 new): item 6's three tenant filters (`rows`, `one`, `update`), each red against
the live cases that read another tenant's row; item 4's way back in (live), the lock-out count, and the runbook's
recovery step; item 5's stale access at each of its four sites (the transfer's refusal, the `stale` set, the alert's
filter and its words, `access_current` itself) and the sign-in recording when access was read (live); item 7's
bearer 1013; item 8's refetch limit, the thread, the 503's two halves; the notes' RS256, leeway, `exp`, `profile`
scope and the set-up console; item 3's notice and its *Try again*. Item 3 was also shown red by hand before the
plant existed (the notice removed: `Unable to find role="alert"`). The first run of the harness had one harness
fault, the stale-alert plant's site moved by the log line added to `recipients_of`; repointed at d994612 and the whole
harness run again.
