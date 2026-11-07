# Studio lane · brief L1.2a part A (redo) and L1.2b · events-only withdrawal, then phase 6's exit

Written by the orchestrator, 7 November 2026, for a **fresh studio session**. The previous session's work
is on `lane/studio` at `ef9b35d`; its `REPORT.md` items 1–10 say where everything stands, and items 9–10
say where Part B starts. Read them first. Opus, medium. Parts in order; message the orchestrator
(`ospreyflow-7e`) ready-to-merge after each.

**Binds.** `process/CLAUDE.md` rules 1–15 (rule 3 above all; rule 14 with the leased throwaway stack,
`SESSIONS_RUNBOOK.md` §4); ADR-110 Amendments 6–13; `spec/09_INGEST_STUDIO.md`.

**Part A, redo: the owner's ruling of 7 November, "Only the rows' events".** A full-snapshot refresh with
*withdraw* takes back **only the dropped rows' own events** (their timeline and analytics rows). It never
touches graph elements, links or nodes. A dropped row's links and nodes stay until its load is
reverted. Why: whether a link went depended on other cases' rows, so the run's counts, the live links
and the timeline differed with data the loader cannot read (rule 3).
- `services/ingest/snapshot_withdrawal.py`: no graph change at all; drop both ledger reads that look at
  other cases (`elements_kept_by_other_rows`, `elements_in_other_records`). `services/api/studio_publish.py`:
  withdraw the rows' events by their own key, not by edge ids (they are keyed by edge today; find the
  row's key). Drop `only_this_pipeline` if nothing needs it. Metering counts no withdrawal.
- Rewrite ADR-110 Amendment 15 on the branch (its title too: the reservation row will take your title at
  merge) and spec 09's "A full snapshot with withdraw" paragraph: nodes and links are left with no row
  until a revert, and how records written earlier with a non-empty `withdrawn_node_ids` revert.
- **The proof, rule 15's shape:** the real ArcadeDB adapter (`arcadedb_adapter`) and two real principals of
  different cases; the same recipe run in the other case; through `run_recipe_as` and
  `run_published_recipe`. Compare everything the loader is told, including after the row comes back
  (`edges_created`), plus the live nodes, the live links and the timeline events, with and without the
  other case's row and link. Red with link withdrawal restored and with each ledger read restored, kept
  on record (`process/lanes/studio/L1.2a_RED_RECORD.md`, in the pattern of `L1.2_RED_RECORD.md`). Rewrite
  `tests/ingest/test_snapshot_withdrawal.py`, `test_snapshot_withdrawal_tells_nothing_live.py`,
  `test_source_refresh_snapshot_live.py` to the rule.
- Minors: `metering.py:12-13`; the live test's docstring; the `Withdrawal` docstring; delete
  `process/lanes/studio/L1.1_ci_makefile.diff` (superseded by `L1.2a_ci_makefile.diff`; add the live files
  this part adds to that diff).

**Part B (L1.2b): phase 6's exit.** As `REPORT.md` items 9–10 say: the Prison Intelligence reports
pipeline built from scratch in guided mode (the committed map's eleven elements and ten links) by the
harness walk and by `DEMO_GUIDE.md` chapter 4's steps; an expert-mode edit of it; one live walk of the
running product on the throwaway stack under the lease, naming it.

**Part C waits** for L3.1's merge, and I will tell you (the owner's load-into rule for pipelines; see
`BRIEF.md` history at `ee56678`).

**Every live run takes the lease** (`OspreyFlow_Build/scripts/stack_lease.sh acquire studio "<purpose>"`),
the throwaway stack included; nothing reaches 2491, 55433 or 6379 without it. Questions for the owner go
to the orchestrator by message, as multiple choice. Copy every hash you send from git output.
