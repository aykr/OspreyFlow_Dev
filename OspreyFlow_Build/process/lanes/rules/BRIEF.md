# Rules lane · brief L2.8d · a corrected node an alert names, and L2.8c's carries

Written by the orchestrator, 8 November 2026, after L2.8c's merge (`befcf56`), for a **fresh rules session**
on account `sol`. Read `process/lanes/rules/REPORT.md` (L2.8c, item 11) and ADR-109 Amendment 11 first.
Rebase onto `main`. Opus, medium. Size S. After it comes L2.9.

**The lane, the stacks, the merge rule.** As L2.8c's brief and Prompt L say: rules' ownership map; a test
stack by `stack_lease.sh acquire rules "<purpose>"`, pinning the ports it prints; before ready-to-merge,
your own lane-reviewer pass, then make -k ci and make test at a commit rebased onto main, saved under
`process/lanes/rules/gates/`, with the commit and its tree sent to the orchestrator.

**Binds.** `process/CLAUDE.md` rules 1–15 (3, 4, 12 and 15 above all); ADR-109 Amendments 10 and 11
(point 7's finding: the journal renames only an alert's own `Alert` node; a node among its
`referent_node_ids` keeps naming the superseded revision, so a correction of a node an alert names
withholds that alert).

**Build:**
1. **The referent rename:** the same journal mechanism over `referent_node_ids`, so an alert naming a
   corrected node stays listed for its readers, and is still refused to a reader who may not read the
   new revision. Record it as an ADR-109 amendment (ask the orchestrator to reserve the number).
2. **L2.8c's carries** (REPORT.md item 11): (a) a conformance case that another link type holding the
   same id is never marked; (b) a test that an Alert node carries only `ALERTED_ON` links; (c) one helper
   for `purge_copies` and `WorkingSetReverter.remove`'s history scrub, and whether history serves old
   copies; (d) `test_written_back_reads_in_full_stages.py`'s `_Store.repointing` moved to the shared
   stand-in; (e) the alert store's DDL and pools per worker replica, against Postgres's concurrent-DDL
   and connection limits; (f) an enrich stage that writes no point opens no record; (g) the review's
   items 11 and 13 as ruled.

**Tests first, each red by a plant at the real call site:** an alert naming a corrected node is listed for
a reader of the new revision and refused to one who may not read it, each red without the referent
rename; each carried item's own test as named above.

**Exit.** Make ci and make test green offline; the live cases under a named lease and stack; a friction
fragment. Report in Prompt L's format, then stop.
