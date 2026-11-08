# Rules lane · brief L2.10 · one queue, watches, team routing, Raise an alert

Written by the orchestrator, 8 November 2026, after L2.9's merge (`057a10e`), for a **fresh rules session** on
the orchestrator's account. Read `process/lanes/rules/REPORT.md` (L2.9) and ADR-146 with Amendments 1 and 2
first. Rebase onto `main`. Opus, medium. Size L. **L2.10 is one of the docs lane's gating steps.** After it
comes L2.11 (the rule editor). Rules-b (the sister lane) builds L2.12, reporting folded, beside you: its files
are the plan's rules-b row; ask the orchestrator before touching any.

**The lane, the stacks, the merge rule.** Rules' map minus rules-b's; a test stack by `stack_lease.sh acquire
rules "<purpose>" && …` only; Prompt L's rules (never stop on a question; schemas ride with the step; your own
lane-reviewer, then make -k ci and make test at a commit rebased onto main, saved under gates/, with a leased
live run including `test_route_rights.py` and every live file the change reaches). Team routing is a new rule 3
read, so this step gets the orchestrator's independent review.

**Binds.** `process/CLAUDE.md` rules 1–15 (3, 4, 7, 12, 13 and 15 above all); ADR-146 and Amendments 1 and 2
(*Suppress until…* included, R8 a); ADR-145 Amendment 5 (teams, leads, hand-over and cover, as admin's L2.5
built them); ADR-109 Amendments 10–12 (repoints).

**Build** (the plan's row L2.10): one queue (the inbox removed, *what fired it* on every watch alert); the
queue's filters; the inventory *What raises alerts*; watches kept there and made from the Glass (*Watch for
this*, *Save as a watch*); saved patterns on a schedule (G16); **team routing**, the new rule 3 read, tests
first; the lead's hand-off and taken-back marking; *Raise an alert…* to the case or the dataset (R4). And the
row's two carries: an alert repointed by a settle on a read path keeps a working-set copy at the old marking
(purge it, test first); a monitor alert in a composite case's layer must not stop the KYC sweep whole (test
first). From `process/lanes/CARRIES.md`: Ask to search shows `model_limit_reached` if platform's P3 hasn't (check
main). The rule's list picker reading studio-b's offered lists waits for the owner's ruling on which
screening-list store is of record; leave it to L2.11.

**Tests first, each red by a plant at the real call site:** team routing reaches only the team's members who
may read the alert (rule 3), red with the read check removed; a watch made from the Glass alerts only on what
its maker may see; *Raise an alert…* refused to a case or dataset the raiser can't write; keyboard cases (rule
13), registry ids as a diff; axe in dark, light and GOV.UK.

**Exit.** The row's exit; make ci and make test green offline; live cases under a named lease and stack; a
friction fragment. Report in Prompt L's format, then stop.
