# AD1c, round 9: one row (the conductor, 25 November 2026, 12:52 UTC; on the owner's add-round line)

From the round-8 verifier's record (tip `2571171508`). It names a key, so it is the owner's: fixed, never accepted
narrower. **This round is the one row below and nothing else.**

| # | Open case | Where | Done when |
| --- | --- | --- | --- |
| 1 | **`clear-orphans` can say nothing was removed after it removed tokens.** The removals happen first; if the second read (the one that shows none remain) then fails, its fixed refusal words become `OrphanedTokens.unread`, and every such text ends "Nothing was removed by the scan.", printed straight after "orphaned access tokens removed: <engine>". The owner's key rules: the words say only what happened. No test drives this path. | `clear-orphans` and its words | When the check after the removals cannot be read, the command says **what it removed** (each engine, as the audit names it) **and that it could not confirm none remain**, in fixed words that repeat no error of the database or the gateway and name no token; never "Nothing was removed". Every other path's words unchanged. Red first: a test removes a token, makes the second read fail, and fails today on the words. |
