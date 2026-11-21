# Slice SE6b · SE6 · A removed dashboard identity's rows leave the reporting mart (backlog N19, was N19-03); failing test first

- **Build id:** SE6 (privacy; the security builds start whatever the queue holds). **The owner's ruling of 21 November 2026 (file 009, answer 12): its own small slice, with the security builds and ahead of the platform ones; failing test first.**
- **Dial setting:** balanced
- **Rounds limit:** 6 (a security slice; the dial's balanced 8 is not wanted for a change this small)
- **After:** nothing (SE6a is merged).
- **Status of this brief:** written by the conductor on 21 November 2026 from a read-only scout's table (`OspreyFlow_Build/process/lanes/v062/backlog/N16_N22_RENUMBERED_2026-11-21.md`, row N19). **Line numbers are the scout's of that day; re-read every one.** **The key rules and the access-control rules bind every line: no key, token, password or address in any file, log, test output or message (synthetic ones made at run time); an unauthorised principal must not be able to read, count or detect a removed identity's rows; a fault that exposes any of that is never accepted.**

## The fault (read it yourself before you write a line)

Removing a dashboard identity in the Admin does not remove what that identity's pulls left in the reporting mart. The route `OspreyFlow_Core/services/api/app.py` (the dashboard-identity DELETE, about lines 18174 to 18203; the scout found it there, the inventory said 18100 to 18106) revokes the identity's case grants and deletes the identity, and **never touches the mart**. Pruning happens only in `OspreyFlow_Core/services/report_sync/sync.py` (about line 162, `mart.prune` on the configured list), and that list is the environment variable `REPORT_SYNC_DASHBOARDS`, which nothing in Core writes except backup, restore and the cloud (`harness/reporting.py` about 143, `harness/restore.py` about 547). `services/report_sync/mart.py` (about 119 to 130) deletes figures only when called, and `record_failure` (about 109 to 117) keeps rows on a refusal. **Result: the removed identity's figure and pull rows stay in the mart, and Admin and Alpha, who read the whole mart in Superset by the path ADR-148 Amendment 21 accepts, still see them.** It is a retention fault, and an access-control question only inside that accepted exception: say in your report whether, on your reading, anything beyond Admin and Alpha can read those rows (the guest role: backlog N18, `pulls` readable through the guest role, is a separate row and **not** in this slice: do not fix it here, and do not make it worse).

## What (in this order)

1. **The failing test first** (rule 12, the invariant "a removed identity holds no rows in the mart"; rule 15, shaped as the route really calls): in `OspreyFlow_Build/tests/services/api/test_removed_identity_mart_rows.py` (new, pure, a mart fake that **refuses what the real mart refuses**, not only what it grants; read `services/report_sync/mart.py` for the real mart's shapes): register an identity, write figure rows **and pull rows** for its client id into the fake, call the real DELETE route (through the app's own test client, as `tests/services/api/test_admin_routes.py` does around its existing `remove_dashboard` assertion, about line 692), and assert **no mart row remains for that client id, in any table the report-sync writes** (name them from the real schema, do not hard-code a guess). **Red on main today**, because the route never calls the mart: show that red before any product line (the conductor's merge also runs it against the base).
2. **The fix, the smallest that makes the removal reach the mart.** Choose and say which, with why, in the report: (a) the route removes the identity's rows through the mart's own writer (check first that the Conduit holds a connection to the mart; if it does not, do not give it one: use (b)); (b) the removal is recorded where report-sync reads it and the next sync prunes, **and the rows stop being readable at once** (a reader-side filter on removed identities), not at the next sync (an hour of a removed person's rows still readable is the fault, only shorter). **Whichever it is: the prune must take every table the sync writes, a failed prune must not be silent (words and a test), and `record_failure`'s keeping rows on a refusal must never keep a removed identity's rows.** A removal that fails to reach the mart is a refusal the administrator sees, not a success.
3. **The sync-side pruning is exercised by nothing today (no test calls `prune`):** add the test that does (a removed identity absent from the configured list loses its rows at the next sync; and one still listed keeps them), each with its planted fault shown red (remove the prune call; keep the stale rows).
4. **Rule 4, every read path gets an access-control test:** the new read-side behaviour (if you add a reader-side filter) has its own test showing a removed identity's rows are not returned to Admin or Alpha, and that a present identity's rows still are.
5. **Report:** which of (a) and (b), and why; every table the removal now reaches; the test names against the fault each plants; what only a live run on the test stack would show (a Superset board still showing the rows) and that you ran none.

## Acceptance test

`OspreyFlow_Build/tests/services/api/test_removed_identity_mart_rows.py` (new, red first on main; the plants red). **Say which folders it walks** (a scan row is written from that).

## Checks (pure; store ports pinned to 9)

The new test; `tests/services/api/test_admin_routes.py`; the report-sync tests (`tests/services/report_sync/`); `tests/test_doc_citations_check.py`; `ruff check .` in `OspreyFlow_Core`. Before your final report run what the conductor runs again (ruff on every file changed, the scan-map check for the test you add) and the whole pure sweep for the folders you touched.

## Out of scope

N18 (the guest role's read of `pulls`), N16 and N17 (SE6 and the security builds' own rows), N20 and N21 (platform), any Superset configuration change, the whole-mart reader decision (ADR-148 Amendment 21: it is accepted and not reopened here), any change to a key, token or password handling.
