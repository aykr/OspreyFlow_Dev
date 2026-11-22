# PL7a2a: every open case before round 6 (22 November 2026, 16:10 UTC)

**The owner's rule (21 November 2026): no round from 5 on starts without a table of every open case.** Written by the conductor from the round-5 verifier's record (tip `8a6afb6`) and the round-5 table (`slices/PL7a2a_ROUND5_TABLE.md`, which holds the nine cases of rounds 1 to 4 and what each needed). **Nothing was run by the conductor; "answered" below means the round-5 verifier read the branch and raised nothing on it, not that the conductor checked.**

| Case | Raised in | Kind | Status at `8a6afb6` |
| --- | --- | --- | --- |
| The six cases of rounds 1 to 3 (token pin, `--check` naming a difference, bare hosts, chart templates, the image registry pin, the staged `deployment.env`) | rounds 1 to 3 | fault and gaps | Fixed at `9d2a1cf` (round-5 table); not raised again |
| The chart's "off" filter looking at nested `enabled: false` keys | round 4 | fault in behaviour | Answered in round 5: the verifier raised nothing on it |
| The "on by default" red case planting only a bare `pages:` | round 4 | gap in a test | Answered in round 5: not raised again |
| The module docstring contradicting `stage_deployment`'s real behaviour | round 4 | fault in behaviour | Answered in round 5: not raised again |
| **New in round 5: the guarded-block scanner (`_guarded_block_end`) does not do what its docstring says.** Its docstring says it returns `None`, the cautious side, when it cannot tell where a guarded block ends; but an inline `{{- if .Values.global }}x: 1{{- end }}` on one line opens a block the scanner counts and never counts the close of, so on the verifier's trace it returns line 6 where the answer is line 4, and the text after the inline block, and the outer `{{- end }}`, drop out of the stored view. Against today's reference it shows red (the lines are in the stored copy); once anyone runs the documented `--write` the reference stores the over-trimmed view, and the lines that render while the page service is off are no longer pinned: the opposite of what the slice is for. | round 5 | **fault in behaviour** | **Open** |

**Open: 1 case, and it is a fault in behaviour.** The verifier's own fix: return `None` for any line inside the block that holds an action opening or closing a block anywhere other than as the whole line, and add a red case for each of the two forms (an inline open and close on one line, and a close that follows text); the guard cases of the render test today use only opens and ends on lines of their own, and the one-line case tests only the guard line itself.

**The conductor's read:** round 6 should finish it (one function and two red cases), though this is the sixth round, and the faults are now each smaller than the last (round 4 had two, round 5 one). The owner's standing accept does not cover it: it covers gaps in a test only.
