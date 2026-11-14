# v052-4c — ADR-148 Amendment 15, the administrator fallback (platform-b)

Branch `lane/platform-b-4c`, on `lane/platform-b-v052-gate`. Two adversarial reviews, each by a
lane-reviewer briefed without the lane's own conclusions.

- **Round 1:** fixed in 7070060, with a797f67 as the schema commit.
- **Round 2:** fixed in 572565a. Its findings, by number:
  - **1:** the start's wiring is now tested offline (plant v) and live (`test_am15_the_start_itself_…`).
  - **3:** a person with a value set here missing is never `signed_in`, so no lock-out check counts
    them, on any route (plant i).
  - **4:** the seed's values follow its role gate (live).
  - **5:** each start refusal is matched by its own words, the presence check's case included
    (plant iv).
  - **6:** the first administrators' values are checked against the handling scheme at start (plants
    ii and iii) and their shapes at render (plant vi).
  - **7:** the audit rows of the seed's values and of Access sit in their transactions (live).
  - **8:** stale when a value is missing.
  - **10:** an Access that sets nothing is refused.
  - **11:** the Glass has words for `setter_cannot_set` and `no_such_person`.

## Records

- `stepA/B/CD/E-red-first.txt`: each step's plants, all re-run after round 1 with a fresh
  `PYTHONPYCACHEPREFIX`.
- `round2-red-first.txt`: round 2's six plants, red then green, the tree unchanged after.

## Open

- **The live section: run** on 14 November on test stack b under platform-b's lease. The owner acquired, brought up,
  ran, brought down and released it from this worktree's window. The whole live file passed, 32 of 32, and three
  live plants each went red for their own test, with 11 passing again once restored (`am15-live.txt`).
- **Found by the rebase onto main (Amendment 16), and fixed in 4c** (the orchestrator's word, 14 November): a run
  acting as its owner read only the token's columns, so under the fallback every run was refused as "out of date".
  `owner()` now reads the administrator's values through `_owner`. With every value set here, the owner is current;
  with some set here, the token's values still need a sign-in within the day; a value set here but not set yet
  refuses the run.
  - Offline: five tests, and four plants red (`owner-red-first.txt`).
  - Live: `test_am15_a_run_acts_as_its_owner_with_the_values_set_here`, run on stack b (the owner's acquire): the live file
    35 of 35, red with Amendment 16's own read planted, green restored (`owner-live.txt`).
  - ADR-148 Amendment 15 has point 8, and §6a.7 a sentence, mirrored.
- **Round 2's could 9** is carried: the stale-access words (`STALE_ACCESS_WORDS`) advise "sign in
  again", where the fix for a person with a value unset is an administrator setting it. The words are
  shared by three refusals and their tests.
- **Round 2's could 12** is done (9709011). Plant (d) was re-run with its diffs recorded.
  - The readers changed alone stay green, because the fill overwrites them.
  - The whole shape (the readers and the fill) is red for the escalation test.
  - So the two are guards that each cover the other.
- **Round 2's could 13** is done: `process/friction/2026-11-14-platform-b-v052-4c.md` (5de6b9d).

## Waiver: the schema commit's place (Prompt L), the orchestrator's ruling of 14 November 2026

Prompt L asks that a `packages/schemas` change ride with its step "in its own commit at the head of the
branch". This branch does not meet that as written:
- step E's `SignInKind.administrator_sets` (`admin.py`, `generated/SignInKind.ts`) sits in **ea0c7ba**;
- the settings' descriptions naming `{administrator: true}` (`deployment.py`,
  `generated/OspreyConfig.ts`) sit in **bafec55**, with spec and guide hunks;
- `PersonAccessInput` and `EntraSignInConfig.first_administrator_access` sit in the schema-only commit
  **a797f67**, which 572565a now follows.

The orchestrator waived the rewrite: no history rewrite is needed. At the head, the types are
regenerated with no drift: `make -s schemas-check` reports "604 generated types match committed
output".

## Merged with main (Amendments 16 and 17, guide 2.05), 14 November

4c is **merged** with main, not rebased. Amendment 17 (guests) reworked `_person`, the people query and the store's
set-up, so a rebase would have met the same overlap in commit after commit. Each conflict is the union of both sides
(31b73b1). Where the two amendments meet:
- **The setter of Access is read as every read has them,** so a guest refused while guests are not admitted sets
  nothing (rule 3, in the store). This has a test, with its plant red.
- **A run's owner** carries main's guest refusal, ahead of the refusal for a value not set here.

The guide is 2.06, above main's 2.05, and the copies are mirrored.

**Run live after the merge** (`merge-live.txt`, on stack b under platform-b's lease "4c after merge live", 14 November):
- The whole live file passed, 40 of 40. It covers the merged SQL: Access's setter read through
  `PEOPLE_SQL … FOR SHARE OF p`, `standing`'s join with the administrator's columns, and the person upsert writing
  the guest and the administrator's columns.
- The setter's read put back to a plain `SELECT * … FOR SHARE` went red on the real table: the refused guest set
  Access ("DID NOT RAISE AccessBeyondTheSetter").
- Restored: 17 passed.
- main merged again (8a0f8c5) for its own mypy fix.
