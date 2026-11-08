# Glass lane · brief L2.8b · old records under the new check

Written by the orchestrator, 8 November 2026, after L2.8's merge (`e2846f8`). Rebase onto `main` first.
Opus, medium. Size M. Same file agreement as L2.8: the Glass lane's map, plus `alert_queue.py`, `alerts.py`,
`watch_routes.py`, `rule_holds.py`, `packs.py`, `rule_evaluation.py` and `link_changes.py` /
`entity_pictures.py` for the checks named here only; `app.py` for parameter-and-argument only.

**Binds.** `process/CLAUDE.md` rules 1–15 (3, 4, 12 and 15 above all); ADR-146 decision 10; ADR-109 Amendment 9;
ADR-124 Amendment 17; `process/BUILD_PLAN_PARALLEL_LANES.md`'s L2.8b row, which lists every item.

**Build, each with its test shown red first and kept on record.**
1. The rule audit: `edge_ids` and `event_ids` written into each `rule_fired` entry at raise time; entries
   checked through `read_evidence`; entries written earlier keep the entry but withhold their words when
   they name an alert (fail closed; the orchestrator's call, listed for the owner).
2. Held rows' "it matched: {words}" withheld the same way (`rule_evaluation.py:906`).
3. Pack items rechecked by links and transactions, not nodes alone (`packs.py`, that check only).
4. `scripts.remark_alert_nodes`: Alert nodes written before `7fac778` below their links' marking are re-marked;
   a dry run first that writes nothing; idempotent.
5. G3's route-level live test: read through a second case's route as a principal who cannot see the evidence.
6. A triage conflict after the graph commit must not leave a match superseded with nothing repointed.
7. The other `supersede_edge` callers (`link_changes.py:467`, `entity_pictures.py:358/:519`) repoint the alerts
   citing the old revision, as the true-positive close does.
8. The carried test-shape items: the plants re-made in the real paths' shapes (Q2's SAME_AS through the real
   screening path; G2's rows through the real gate); the `get_edges` fake dropping a link with a hidden end, as
   the port does; one transaction scope for the queue and the inbox; the canvas's `edges_among`; the id paths'
   timing recorded, not claimed.
9. 94aeecf's report line (your make ci after the lease, 23:55:25–23:58:25Z).

**The hard part.** Items 6 and 7 cross two stores (graph and Postgres). Say in the plan how a failure between
them leaves no alert hidden, and which test shows it.

**Live runs take the lease** (ask me). **Exit:** every item's test green and red on record; spec 03 and the
records to match; a friction row; the report (at most twenty lines). Then L2.4 part 2 when L3.1 lands
(`BRIEF_L2.4_part2.md`).
