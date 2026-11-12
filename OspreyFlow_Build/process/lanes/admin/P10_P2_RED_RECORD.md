# P10 part 2 · red record (CLAUDE.md rule 15)

Branch `lane/admin-p10p2`. The plants harness is `p10p2/p10p2_plants.py`. Each plant edits the real code where the
behaviour lives, runs the cases meant to catch it, expects them red, and restores the file. The shared files' diffs
(`readers.diff`, `render.diff`, `glass-sign-in.diff`, since the review of 3848c32 `runbook.diff`, and since the second review `resolver-doubles.diff`) are applied first, so a fault in them is planted where it will
merge, and reverted at the end.

What counts as red is as in part 1's harness:
- a planted Python source that does not compile is a harness fault;
- a pytest case is red only on exit 1 with "failed" and no "error";
- a vitest case is red only on exit 1 with "failed" and no collection error.

| Head | Plants | Case runs | Result | Output |
| --- | --- | --- | --- | --- |
| `1d20d94` (the head after the orchestrator's third review of e8d5874, on main 91a029c) | 103: 89 offline, 14 live | 114 offline + 18 live | 132 red, 0 missed, 0 harness faults | `gates/p10p2_plants_1d20d94.txt`; the live eighteen under admin's lease on stack b, `gates/p10p2_live_targeted_1d20d94.txt` |
| `9bf0aa8` (the head after the orchestrator's second review of 67f3d2a, on main 510141b) | 95: 83 offline, 12 live | 106 offline + 15 live | 121 red, 0 missed, 0 harness faults | `gates/p10p2_plants_9bf0aa8.txt`; the live fifteen under admin's lease on stack b at 9bf0aa8, `gates/p10p2_live_targeted_9bf0aa8.txt` |
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

**The second review's plants** (19 new, 7 moved): the keys' cache (fetched at every sign-in), the unknown-kid window, one
thread fetching, the grace and its end, the keys' own executor, a body not JSON and a set with no usable key, the
http-or-https rule; owner resolution's keys unreadable (Keycloak); the run API's 503, RS256, leeway and shared keys; the
re-grant only when nobody can manage people, both ways, and its audit row; the hourly refresh both ways; the
bootstrap's lock (now shown deterministically: `connect` waits while another session holds it); the socket's 1013
before a message; Name an Author's 24 h rule. The account-unread notice's keyboard spec and axe scans were shown red by
hand (playwright, which the harness does not run): `gates/p10p2_mac_41e1d6a.txt`. **Not shown red alone**: owner
resolution's use of the keys' threads (the same error mapping catches it either way; the same `in_keys_thread` is red on
the person path). The first full run had one harness fault: Name an Author's case is in a file `resolver-doubles.diff`
carries, which the harness did not yet apply (no tests ran); it does now, and the whole harness was run again.

**The third review's plants** (11 new, 4 moved), each red for its own reason: the keys' wait without a total bound,
and a stuck fetch never abandoned (a body that trickles, each read inside its own timeout, the whole past it; the
first try of the second missed, because the test's server sped the stuck request up when the next was given no
pause, and was fixed in the test, not the code); the unknown-kid window opened before the fetch (an unreachable
Entra then a 401); a set with no key a token can be checked by; a waiting thread fetching again (twelve concurrent
sign-ins, one request); the run API's keys on the event loop; the grant and its audit row apart; the custom roles'
rights not read; the seed without `PEOPLE_LOCK`; and the window edge added to the no-window plant. **Must-fix 1**:
the event-loop case reads the fetch's own thread and the loop's largest gap, and both its plants are red in the whole
file's run and under `-n auto` (`gates/p10p2_mac_1d20d94.txt`). The account-unread notice's keyboard and axe reds
retaken at 1d20d94, the same file.
