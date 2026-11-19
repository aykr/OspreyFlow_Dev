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
