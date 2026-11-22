# IS5a, before round 9: every case, open or closed (the line's table before a round of 5 or more; a read-only scout's, 22 November 2026)

Paths are under `OspreyFlow_Core/apps/pages/` unless they say otherwise. Rounds are the verifier's: R1 `b126a3`, R2 `b5a357`, R3 `538f31`, R4 `2cbae6`, R5 `429f7d`, R6 `78aff1`, R7 `995ec8`, R8 `7c64ab`. "Closed" rests on the builder's commit message or on a later verifier not repeating the finding; **the scout saw no red-then-green record for any row.** Round 9 is **the owner's one round for one comment** (file 011).

| # | Round | Kind | File and line | What | Status | Cause |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | R1 | fault | `tree-default/studio/releases.njk:83` | Scripts-off "Check again" does nothing without the tick | closed (b5a357) | brief item missed |
| 2 | R1 | fault | `server/studio.ts:328` | Import rights tip computed, never drawn | closed (b5a357) | brief item missed |
| 3 | R1 | fault | `server/upload.ts:101` | Over-200-files and session-end refusals show the 2 MB words | closed (b5a357) | brief item missed |
| 4 | R1 | test gap | `package.json:10` | Keyboard and scripts-off cases run by no slice check | closed per builder; **CI wiring is the owner's** | outside the builder's reach |
| 5 | R2 | fault | `server/views/studioWords.ts:307` | The Conduit's 409 words replaced by a false "try again" | closed (538f) | brief item missed |
| 6 | R2 | test gap | `test/support/fakeConduit.ts:190` | Fake never gives the real route's 409 | closed (test 2cedbd2) | fake accepts what the real route refuses |
| 7 | R2 | test gap | `keyboard/studio-releases.spec.ts:147` | Same keyboard gap as row 4 | closed per builder | owner's CI wiring |
| 8 | R3 | fault | `server/staging.ts:19` | "Never on disk" false: Valkey writes `dump.rdb` | closed (2cbae6: held in the pages process's memory) | brief item missed |
| 9 | R3 | fault | `server/studio.ts:632` | `held.save` unguarded for `StagedTooLarge`: a 500 page at session end | closed (2cbae6) | brief item missed |
| 10 | R3 | test gap | `server/views/studioWords.ts:78` | Needs-you word copies not held to the shared file | closed (test 81eb14) | no test |
| 11 | R4 | fault | `OspreyFlow_Core/packages/schemas/deployment.py:1758` | `pages.enabled` reads YAML 1.1 `yes`/`on` as true | closed at R5 (429f7d) | tests passed Python strings, not YAML text |
| 12 | R5 | fault | `server/studio.ts:227` | Needs-you reminder and Model link open Pipelines | closed (c120c2) | link target wrong |
| 13 | R5 | fault | `tree-default/studio/frame.njk:34` | Help panel shows raw role ids | closed (not repeated at R6) | ids put into copy |
| 14 | R5 | fault | `README.md:44` | README and header say the folder is in the session store | closed (c120c2) | docs out of step with round 4 |
| 15 | R6 | fault | `server/sessionStore.ts:118` | Staged folder not removed at expiry | closed (995ec8: swept at expiry) | removal only lazy |
| 16 | R6 | test gap | `test/default/studio-releases.test.ts:484` | SR13 expiry check removes the entry itself | closed (not repeated) | observation does the removal |
| 17 | R6 | fault | `server/studio.ts:323` | Rights unknown: page offers Export and Import; React disables them | closed (995ec8: the difference is named) | not named for the owner |
| 18 | R6 | test gap | `test/support/fakeConduit.ts:173` | Fake grants the strip's reads to anyone | closed (995ec8) | fake accepts what the real route refuses |
| 19 | R7 | fault | `OspreyFlow_Core/packages/schemas/deployment.py:2134` | A non-None default adds `pages: enabled false` to every dump, so renders change | closed (7c64ab) | default changed the dump |
| 20 | R7 | test gap | `OspreyFlow_Build/tests/schemas/test_pages_enabled.py:169` | Test searches text; cannot see the render change | closed (not repeated at R8) | test checks text, not output |
| 21 | R8 | test gap | `server/studio.ts:614` | No test that a held folder is bound to its case and dataset | **OPEN: backlog row 13** | no test |
| 22 | R8 | test gap | `modules/studio-frame.ts:27` | No keyboard case for the dataset switch | **OPEN: backlog row 14** | no test |
| 23 | gate, 22 Nov | gate refusal | `server/views/studioWords.ts:6` | A comment names the old path of files PL4d3d moved; `test_no_tracked_file_names_an_old_path` fails (1 failed, 1512 passed) | **OPEN: round 9** | the comment itself |

**Totals:** 22 verifier findings (13 faults, 9 test gaps) plus the gate refusal = 23 items; closed 20; **open now 3**: (a) the comment at `studioWords.ts:6`, **round 9's one thing**; (b) backlog row 13; (c) backlog row 14 (b and c are not for round 9). **Convergence:** faults per round 3, 1, 2, 1, 3, 2, 1, 0; round 8 had no fault, but it added two test gaps.
