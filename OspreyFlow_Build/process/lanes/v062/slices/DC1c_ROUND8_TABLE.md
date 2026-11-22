# DC1c, before round 8: every case, open or closed (the line's table before a round of 5 or more; 22 November 2026)

Rows are those of `OspreyFlow_Build/process/lanes/v062/slices/DC1c_ROUND7_TABLE.md` (every verifier finding of rounds 1 to 7), with these changes: **the conflict with main is closed** (round 7's builder merged main in, kept both rows and renumbered DC1c's from 2.30-2.33 to 2.35-2.38, regenerated the PDFs and the manifest: the verifier checked each of Round 8's four points and they pass); **one new finding of the round-7 verifier (`591b1a3e0b`):** the builder's two `ruff format` commits (`f75dd12`, `591b1a3`) on four product files, **formatting only (the verifier read every hunk)**, made to satisfy the Stop hook, which lists main's files as the branch's (line fault 14). **The owner accepted them (`DC1c accept`, 22 November); the line's accept refused it because the finding quotes a phrase containing a word it reads as a security word (line fault 15).**

| # | What | Status |
| --- | --- | --- |
| 1 to 22 | the round-7 table's findings (17 faults, 5 test gaps) | closed except the three test gaps already accepted narrower (`test_intent_in_the_guides.py` lines 192, 251, 274: backlog rows) |
| 23 | the conflict with main | **closed** (round 7) |
| 24 | two formatting commits on four product files, outside Round 8's list | **the owner's word: accepted as formatting only; the line cannot apply his accept (fault 15)** |

**Totals:** 24 items; closed 22; the three test gaps are backlog rows; **open now: row 24 only, and only as a formality for the line.** Round 8 changes nothing.
