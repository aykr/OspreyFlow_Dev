# admin lane · report · L2.6, the Audit section and Operations' ageing (8–9 November 2026)

Resumed again on 9 November from the branch alone, with no `HANDOFF.md` and no `wip(admin)` commit. The branch
already held rounds 1–3 and round 3's live set, but its report and gates dated from before round 3. It was
rebased onto main 3be89a7 (44 commits, no conflict), keyboard and axe were rerun, and a fourth lane review
covered the commits no reviewer had read. Its fixes are in, and the gates were rerun at the head.

| Brief item | State | Proving test (each red by a plant at its call site, `L2.6_RED_RECORD.md`) |
| --- | --- | --- |
| 1. Audit read by unit (O2) | met | `test_audit_section_store.py` U1, U2, U7 (live) |
| 1. The rule audit for the Administrator | met | `test_audit_section_routes.py` W2–W4, R1–R2; `test_place_routes.py` P1, P2 |
| 1. Filters by who, what and when | met | W8, F1, U2, U6; keyboard K1 |
| 1. Withheld words stay withheld; no account id | met | W1, W6, G4, G5, I1–I9 |
| 2. Operations' ageing (O3) | met | A6, A7; keyboard K2 |
| 3. *Promotions overdue* (R7) | alert built; the record left for L3.4 | A1–A5, U5, S1–S6, `test_promotion_sweep_live.py` |
| Keyboard (rule 13) | met | 61/61 `keyboard/admin*` with `registry.diff` applied, at 5a3eeb4 |
| Axe in dark, light and GOV.UK | met | 72/72 admin scans, at 5a3eeb4 |

1. **Audit by unit (O2): met.** The stream is read by unit in its `WHERE` clause, and a case's entries only by the unit's `osprey-admin` (ADR-052 §4). Every filter narrows the read.
2. **Rule audit: met.** One case at a time, read only through `readable_rule_audit` behind its own route, which needs `read_rule_audit` and the administrator's role. Its exception from ADR-146 Am. 2 point 3 is pinned to that one route and its three checks. The engines' history needs `manage_models` and is paged with its true total.
3. **Withheld words: met.** No account's id reaches the Glass: who acted is served by name, and the shown words are an allowlist. **New in round 4:** the actions that show their words are a named list of their own (`test_only_the_named_actions_ever_show_their_words`), so moving an action into *People and roles* or *Datasets* fails a test (G4, G5).
4. **Operations' ageing (O3): met.** *What ages*, N days (1–90, default 3, audited) and the promotions waiting, read as the reader and within the reader's unit.
5. ***Promotions overdue*: the alert is built.**
   - Raised once at N days, by the database, from admin's own job in the lifespan.
   - Sent to reviewers and the unit's administrators cleared to the dataset's marking, never to the proposer.
   - **Left for L3.4** (`promotion_ageing.WaitingPromotions`): the promotion record, `waiting_for_review`, `all_waiting`, and setting `app.state.waiting_promotions`.
   - **Left for L2.7:** *Needs you* reads `alerts_for`.
6. **Gates** (`gates/`, every failure explained at each file's head):
   - `make -k ci` at 05ec788: green except for trivy, which could not download its vulnerability database, and the test-file wiring that `ci-wiring.diff` supplies. At 341a110 lint found a 101-column comment, now fixed.
   - `make test` at 341a110, offline: 9479 passed. All 28 failed and 49 errors are explained:
     - Docker not running during the run (helm, Caddy/TLS, render-memory, organisation sign-in, workspace proxy). Docker came up before the `ci` rerun, where opentofu and the chart passed;
     - the live store test (19 errors) and the live sweep test (1 failure) on closed ports, wired by `ci-wiring.diff`, and its wiring check (1 failure);
     - `test_place_routes.py`'s two cases until `places.diff` is applied: 104/104 with it applied;
     - this machine's own `osprey.yaml`, Valkey port and `graphify-out`;
     - main's `test_phone_extraction_fixture.py`, a live object-store test on a closed port.
   - 341a110 and 05ec788 differ only by that comment.
   - The live set at afc54b6 (`gates/afc54b6.live.txt`, stack a, admin lease) stands. Since then the store code (`audit.py`) is unchanged, and `audit_section.py` changed only in two actions' kinds, which no live case reads.
7. **Reviews:**
   - Round 1: 18 items. Round 2: 10 items. Round 3: the orchestrator's independent access review, and a lane review of it.
   - Round 4, at 5a3eeb4, over the commits after round 3's review. Fixed:
     - `grading_change`, the operator's change of grading scheme, was filed as an analyst assertion;
     - nothing pinned which actions show their words;
     - `read_connector_source` was a read, not a load;
     - the red record's U17 wording;
     - the live sweep test's docstring promised more than it checks;
     - a 150-column docstring.
   - The review's items 1 and 2 (`places.diff` unnamed, no gates at the head) are answered by this report and `gates/`.
8. **Decisions taken** (yours to overrule; all in ADR-145 Am. 6):
   - (a) words withheld except where the reader's own section shows them;
   - (b) an entry naming no case belongs to its writer's unit;
   - (c) case entries are for `osprey-admin` only;
   - (d) the engines' history needs `read_audit` with `manage_models`;
   - (e) the run ledger is not merged into the stream;
   - (f) the sweep is admin's own lifespan job, and L3.4 sets its source;
   - (g) `read_audit` opens Admin;
   - (h) a start never waits on or drops another start's index build;
   - (i) new: `grading_change` is filed under *Reads and refusals* with the platform's script actions, and `read_connector_source` under *Loads*.
9. **Requests at the merge:**
   - Apply `places.diff` (the branch's `test_place_routes.py` is red on two cases without it), `registry.diff` and `ci-wiring.diff`. All three pass `git apply --check` on main 3be89a7.
   - Mark ADR-145 Amendment 6 `written` in `spec/ADR_RESERVATIONS.md`.
   - Ratify `test_place_routes.py`, `a11y/every-harness.spec.ts`, `services/api/audit.py`, `spec/03_CONDUIT_MIDDLEWARE.md` and `test_route_rights.py`.
   - The Audit section touches access, so it needs your independent review of round 4's change. That change only narrows: no action newly shows words.
10. **Questions:** none. **Still running:** nothing. No stack is held, and the lane-reviewer has finished.
