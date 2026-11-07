# Glass lane · brief L2.8 · the alerts' access fixes first (G2, G3) and the closing count (G9)

Written by the orchestrator, 7 November 2026, after L2.4 part 1's merge (`d035223`) and the owner's
records of 7 November on `main` (`ba8a194`). **Rebase onto `main` first.** Opus, medium. Size S. L2.4
part 2's brief waits beside this one in `BRIEF_L2.4_part2.md`, for L3.1; do this meanwhile, and stop
after it.

**Binds.** `process/CLAUDE.md` rules 1–15 (3, 4 and 12 above all); ADR-146 decision 10 (and decision 6's
*Closing*); ADR-099 decision 5 (refused exactly as missing); `spec/03_CONDUIT_MIDDLEWARE.md` §3.8a; the
gap map's G2, G3 and G9 rows (`spec/glass_redesign/ALERTS_GAP_MAP.md` §5), which give the files and lines.

**Build, each with its test shown red first and kept on record.**
- **G2.** The queue list checks an alert's cited **links and transactions** as well as its nodes, and
  withholds whole an alert any of whose evidence the reader may not see, in the store's query, not
  filtered after retrieval (`services/api/alert_queue.py` 116–127; `alerts.py` 628–630). The test: an
  alert over a link the reader may not see is not listed and its explanation answers exactly as a missing
  alert, red with only nodes checked. A companion for a transaction. Plant the hidden link the way the
  loader writes it, not hand-made.
- **G3.** No alert's **words** reach a reader who may not see its evidence: the inbox (until L2.10 removes
  it) and every list that shows an alert's words withholds them with its evidence (`watch_routes.py`
  205–232). The test is a **worded typology alert** (the shape that names customers and identifiers),
  read from a second case reaching the same dataset as a principal who cannot see the evidence: red with
  the words returned as stored.
- **G9.** A proposed close (`closing`) counts as open on Home, the rail badge and in trends, and a pack's
  status sentence says it ("Proposed for closing, waiting for a second person"), not "Closed without an
  outcome" (`reports/packText.ts` 120–130; `alerts.py` 287–290; `home/homeData.ts` 90–91). One test per
  place, red with `closing` left out.

**The hard part.** G2's check must not tell a reader by count, order or timing that an alert was withheld:
the list's total and its pages are taken after the check (rule 7), and the refused explanation is
indistinguishable from a missing one. Say in the plan how you prove that.

**Files.** The Glass lane's map, plus `services/api/alert_queue.py`, `alerts.py` and `watch_routes.py` for
these fixes only (by agreement for this step; nothing else in them). Lane 3's L3.1 also changes `alert_queue.py` (a composite case's alerts) and merges first; rebase over it when I say it has landed, and keep your change to the check itself. `spec/03` §3.8a and spec 02 in the
same commits if their words change.

**Exit.** The three fixes' tests green and each red on record; a friction row each; the report (at most
twenty lines), with questions for the owner sent to me by message.
