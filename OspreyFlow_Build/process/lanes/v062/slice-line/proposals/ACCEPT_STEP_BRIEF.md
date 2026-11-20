# The accept step: merging a slice the owner has accepted narrower

Written by the conductor on 19 November 2026 for the owner to give to a line-fixes session. Not started.

## Why

The owner accepted GG6 and BL6 narrower, on his word, at their rounds limit (RULINGS.md, 19 November 2026, items 2 and 3).
The line cannot merge either: `merge_slice.py` requires a verifier record with verdict "pass" for the branch's exact tip,
from a session that did not build it, and `resume.py` has five actions (refreeze, add-round, clear-stop, send-back,
correct-command), none of which accepts a stop. The conductor will not write a pass record by hand, and the owner should
not have to ask for another round to get a pass he does not need. The stop message itself asks "accept a narrower
slice, or allow another round?": the second half has a step and the first has none.

## What to build

1. **A resume.py action `accept`**, authority a line in resume.tsv (`<ID> accept <YYYY-MM-DD>`, one use per line, logged in
   owner-changes.tsv with the slice, the tip and the number of findings), the same as refreeze and add-round.
2. **Preconditions** (each refused in words, nothing changed): the slice is stopped at its rounds limit or refused-at-limit;
   its branch tip has a green test record (the Stop hook's) and a verifier record for that same tip whose verdict is
   "findings" (so the owner accepts what a verifier actually saw, not an older tip); the worktree has no uncommitted
   changes; no merge is running.
3. **Effect:** writes an acceptance record for that tip (`accepted-<tip>.json`: the owner's line, the date, every finding of
   the verifier record verbatim, and which are marked fault in behaviour and which gap in a test) and sets the phase to
   `verified` with `accepted: true`. It changes no finding and no verifier record.
4. **merge_slice.py** takes the acceptance record in place of the verifier pass **only for that exact tip**, and still
   requires everything else (red before, green after, the full gate, the live step). The merge record and merged.json carry
   `accepted_findings` (the count and the text), and the board prints "merged, accepted narrower: N findings" and keeps the
   findings in status.js for the conductor's next report.
5. **The scan map and the gate counts** stay complete; the README's "Resuming a slice" table gains the row.

## The standing mode (the owner's ruling 5 of 19 November 2026): no line per slice

The owner's standing word: from a slice's third round on, a gap in a test never blocks. A slice whose verifier finds no
fault in behaviour merges, and each remaining test gap becomes a backlog row, without asking him. So the step needs a
second authority besides a per-slice line, and the owner should have to give it once.

- **The authority** is one line in a file only the owner can write (a new `standing.tsv` beside `resume.tsv`, protected from
  agents by the guard as `resume.tsv` is), for example `accept-test-gaps  from-round 3  <date given>`, read by
  `resume.py accept` and `merge_slice.py`. RULINGS.md is never the authority (the conductor writes it).
- **When it applies** (all of them, else only a per-slice line accepts): the slice's round is at or past the line's number;
  the verifier record for the tip has verdict "findings" and **every** finding is a test gap; there is a green test
  record for the tip; no finding is a fault in behaviour. Anything else is refused in words naming the fault.
- **The marker must be a field, not a prefix.** The verifier's answer schema gains `kind` ("fault" or "test_gap") on each
  finding (the backlog row of 18 November); `run_seat.py` asks for it in the prompt and refuses a finding without it
  (a record with a missing kind counts as a fault). The "FAULT IN BEHAVIOUR:" and "GAP IN A TEST:" prefixes asked for in
  the briefs are read as `kind` for records written before the field existed, and nowhere else.
- **Effect:** the same acceptance record as above, marked `by: standing`, with the findings and the rule's text; the
  merge record carries `accepted_findings` so the conductor writes one backlog row per gap. The conductor tells the
  owner afterwards; it does not ask.
- **Also tests:** the standing line absent: refused; round below the line's number: refused; one fault among the
  findings: refused; every finding a test gap at round 3: accepted; a verifier record whose findings carry no kind: refused.

The two slices that are waiting for this today are GG6 (round 4 of 4, one test gap) and BL6 (round 5 of 5, one test gap).

## Tests that must fail if the step is wrong (rules 12 and 15)

- no line in resume.tsv: refused, nothing written;
- a line for another slice, another action or another date: refused;
- a tip that moved after the acceptance record was written: the merge is refused (the record is for one tip);
- an acceptance record with no verifier "findings" record behind it: refused;
- a slice whose last verdict is "pass": `accept` is refused (nothing to accept);
- a merge with the acceptance record but a red gate: still refused;
- the merge record names the accepted findings (plant a merge and read it back).

## How the owner starts it

The same way as the line-fixes session (LINE_FIXES_BRIEF.md, "How the owner starts you"): a worktree on a new branch from
main, a Claude session in it, and this brief as the instruction; hand back in the OUT folder as that brief says. The
resume.tsv lines for GG6 and BL6 are then `GG6 accept <date>` and `BL6 accept <date>`.
