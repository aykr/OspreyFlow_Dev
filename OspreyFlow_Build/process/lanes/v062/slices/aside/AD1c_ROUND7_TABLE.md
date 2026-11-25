# AD1c, round 7: one row (the conductor, 25 November 2026, 12:06 UTC)

From the round-6 verifier's record (tip `228188cebd`). It names a key, so it is the owner's: fixed, never accepted
narrower. **This round is the one row below and nothing else.**

| # | Open case | Where | Done when |
| --- | --- | --- | --- |
| 1 | **"Plant 5" never shows the "no part of a key in what the code shows" check red.** Its docstring says "the code logs what it read. The abbreviation reaches the log, and the parts check sees it (so it can fail)"; in fact nothing is logged, and no part of a key reaches anything the real output check reads, so the plant cannot turn the check red (rule 15: a plant that a fallthrough or an empty input passes proves nothing). | the plant and the check it is meant to exercise | The plant makes the code under test **really** put a part of a key (the abbreviation the plant names) into what the real check reads (the log record, the command's output, the audit row, whichever that check reads at its real call site), and the check is **shown red** with it, green without it. If the check reads nothing the code can emit, say so: then the check itself is a gap, and make it read what the code really emits. The docstring says what the plant really does. |
