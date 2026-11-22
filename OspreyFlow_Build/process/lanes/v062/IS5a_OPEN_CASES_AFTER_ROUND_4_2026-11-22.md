# IS5a, after round 4: every case, open or closed (the owner's rule: a scout lists them before round 5; 22 November 2026)

A read-only scout (nothing run) read the four verifier records and the lane's commit log. Tip at the latest verifier: `2cbae6f2f3`. Paths are under `OspreyFlow_Core/apps/pages/` unless they begin otherwise. "Closed" is by the builder's commit message or because the next verifier did not repeat it; **the scout did not see a red-then-green record for any of them.**

| Round | Kind | File and line | What | Status | Cause |
| --- | --- | --- | --- | --- | --- |
| 1 | fault | `tree-default/studio/releases.njk:83` | The scripts-off "Check again, replacing my draft" button does nothing unless the tick is also set; the main Check button drops the confirmation | closed (b5a357, "replace button works alone") | the builder missed something the brief named |
| 1 | fault | `server/studio.ts:328` | The `whyImport` rights tip was computed and never drawn on the import controls | closed (b5a357) | the builder missed something the brief named |
| 1 | fault | `server/upload.ts:101` | The over-200-files and near-session-end refusals showed the 2 MB words | closed (b5a357) | the builder missed something the brief named |
| 1 | test gap | `package.json:10` | The keyboard and scripts-off cases (SK1-4, SO1-3) run by no slice check; no red-then-green run | closed (538f, "runs on record"); **the wiring into the gate is the owner's, see below** | what the builder cannot fix (the Makefile and `ci.yml` wiring is the owner's) |
| 2 | fault | `server/views/studioWords.ts:307` | The Conduit's 409 refusals (composite, drawn dataset) were replaced with a false "try again" message | closed (538f) | the builder missed something the brief named (parity with `wordsOf`) |
| 2 | test gap | `test/support/fakeConduit.ts:190` | The fake Conduit never gave the real route's 409 refusals | closed (not repeated; test commit 2cedbd2) | the builder missed something the brief named (rule 15: a fake models the refusals) |
| 2 | test gap | `keyboard/studio-releases.spec.ts:147` | The same keyboard-cases gap as round 1; the CI wiring patch still unapplied | closed per the builder; same caveat | the owner's CI wiring |
| 3 | fault | `server/staging.ts:19` | The staged folder was in Valkey, which writes `dump.rdb` to disk, against the brief's "never written to disk" | closed (2cbae6: held folder lives in the pages process's memory) | the builder missed something the brief named |
| 3 | fault | `server/studio.ts:632` | `held.save` after a check was not guarded against `StagedTooLarge`, so a session ending gave a 500 page | closed (2cbae6) | the builder missed something the brief named (repaired for `put`, not `save`) |
| 3 | test gap | `server/views/studioWords.ts:78` | The Needs-you word copies had no test holding them to the shared file | closed (not repeated; test commit 81eb14) | the builder missed something the brief named |
| 4 | **fault** | `OspreyFlow_Core/packages/schemas/deployment.py:1758` | **`pages.enabled` reads unquoted YAML 1.1 `yes`/`on` as true through `yaml.safe_load`, against ADR-152 Amendment 3 point 1; the test passes Python strings, not what the real loader gives** | **OPEN** | the builder missed something the brief named (item 2b of the brief, mine, asked for the setting and a refusal; the validator's own comment says the right thing) |

**Totals:** 11 findings (round 1: 4; round 2: 3; round 3: 3; round 4: 1). Closed 10, open 1. **Open now:** the round-4 fault, the YAML 1.1 words `yes`, `on`, `Yes`, `ON` read as true, with no test that loads the YAML text through the real loader.

**Convergence: partly.** The counts go 4, 3, 3, 1, and round 4 is the smallest, but every round found faults in a new area (wording, persistence, session end, YAML loading), so I would not call it converged until a round finds nothing. **Not read by the scout:** the brief, the builder's reports (none matched), the commit diffs.

**For the owner, not for the builder:** the keyboard and scripts-off cases need wiring into the Makefile and `ci.yml` (the patch the builder wrote is `ci-wiring.patch`, still unapplied); until then they run only by the builder's own command. It is on the morning list.
