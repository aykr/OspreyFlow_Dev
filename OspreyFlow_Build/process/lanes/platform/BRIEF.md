# Platform lane · brief P5 · the owner's map rulings

Written by the orchestrator, 9 November 2026, after P4's merge (`7a5b2bf`), for a **fresh platform session** on
the orchestrator's account. Read `process/lanes/platform/REPORT.md` (P4), ADR-147 and its Amendment 1, and
`process/lanes/MORNING.md`'s "Your rulings, 9 November" first. Rebase onto `main`. Opus, medium. Size M.
Write ADR-147 Amendment 2 (reserved for you).

**The lane, the stacks, the merge rule.** As P4: platform's map files; a test stack by
`stack_lease.sh acquire platform "<purpose>" && …` only; Prompt L's rules (never stop on a question; schemas ride
with the step; every live test removes what it writes; your own lane-reviewer, then make -k ci and make test at
a commit rebased onto main, saved under gates/, with a leased live run including `test_route_rights.py`, alone on
the machine's load). Map data in the demo and CI is tier 1 only (rule 9); no real tiles fetched in tests.

**Binds.** `process/CLAUDE.md` rules 1–15 (3, 7, 9, 12 and 15 above all); ADR-014–017, ADR-099 Amendments 12
and 15, ADR-147 and Amendment 1; `spec/00_ARCHITECTURE.md` §7 (the licence register).

**Build** (the owner's rulings, 9 November):
1. **Java in the Conduit image (ruling 1, option A).** A licence register entry in `spec/00` §7 for a Java runtime
   under GPL-2.0 with the Classpath exception (only that exception; GPL and AGPL otherwise still never pass), and
   `licence-check` taught it with a red-then-green test (a plain GPL-2.0 Java still refused). The runtime jlinked
   and pinned by digest in the Conduit image, so *Admin › Maps*' Build runs planetiler in the Conduit. Image size
   recorded in the report.
2. **Gazetteer places copied into a case's dataset (ruling 6, option C, not the orchestrator's recommendation).**
   When a case's Author adds a gazetteer, its places are copied into the case's own dataset at load, so the case
   stays one dataset and keeps its loads (no composite). The copies keep decision 3b: their source identifiers
   withheld from every request reader and never matched by search or suggest, keyed on the copy's provenance, not
   on a `gazetteer-*` dataset name. Copies carry the gazetteer's handling; a re-build refreshes them; removing
   the gazetteer from a case removes its copies (never another load's nodes, rule 6). Place search reads the
   case's dataset. Tests: a live copy, its identifiers absent from search/suggest/expand/node detail, each red
   without the fix; a working case still loads after adding the gazetteer.
3. **The gazetteer's unit a build setting (ruling 8).** `recipes/osm_gazetteer.yaml:24`'s `unit-1` becomes a
   parameter of both builds and *Admin › Maps*, refused in words when no such unit exists.

**Exit.** make ci and make test green offline; the leased live set green, alone; a friction fragment. Report in
Prompt L's format, then stop.
