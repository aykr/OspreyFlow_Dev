# Addendum to the morning hold list (written after midnight; fold into `MORNING_HOLD_2026-11-21.md` when no merge is running)

## 7. DC1b (the two websites) stopped at round 4 of 4 with four faults: one line needed (`DC1b	add-round	<date>`)

The verifier checks every changed sentence against DC1a's table and has held the slice to it each round; round 4 found:

1. `overview.py` line about 346: the animated overview's audit scene (shown on both Homes) still has the heading **"Everything is on the record"**, stronger than DC1a found true.
2. `overview.py` line about 340: the same scene still draws an audit entry **"Refused: a read above their clearance"**: DC1a found that only refusals of case access are audited, and that records above a person's clearance are filtered in the store, not refused and recorded; the slice's own corrected sub line contradicts the drawn row.
3. `build.py` lines about 628 and 599: the net Home's "Inside your boundary" panel and the Governance "Data sovereignty" line still say the only traffic out is the install's downloads and an opt-in hosted engine; DC1a found model pulls on every start, a certificate fetch on an https address, and (v0.6.1) the dashboards' usage image. The constraint card and public-sector card were fixed; these two places were missed, and the test does not require the words there.
4. **The deliverable is missing:** the brief requires `DC1B_SENTENCES.md` (every replaced sentence, page, why it was too strong, replacement) plus the whole diff and a rendered copy of each changed page in `Claude outputs/ospreyflow_intent_2026-11-20/DC1b/`; the builder could not write there (the folder is outside its tree), and the list is in neither the commit nor a folder. **I will put the diff, the sentence list and the rendered pages in `OspreyFlow_Build/process/lanes/v062/slices/DC1b_OUT/` (inside my own area) when the slice is verified, for you to copy.**

**Recommendation: one add-round line.** All four are concrete and small (two scene strings, two lines of wording and a test requirement, a file). If you add it, round 5 fixes them and also makes the test require the corrected words in every place the claim appears, so a fifth miss cannot pass.

## 8. DC1c (the README and four guides) is in round 3 of 4 at the time of writing; PL4d2 in round 4 of 4; LR1 on its third merge attempt

No action needed from you yet. If DC1c or PL4d2 stop at the limit they are added here.
