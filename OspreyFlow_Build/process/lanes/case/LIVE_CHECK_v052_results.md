# v052-results: the live check, once studio's search route is on main

Prepared 14 November 2026, while v052-results waits to merge after `lane/studio-search`.

**What it runs.** `OspreyFlow_Core/apps/workspace/live/search-results.spec.ts`: four cases against the real
`POST /v1/investigations/{id}/search` on a stack holding Fixture Corp. Playwright already lists the file; it has not
been run.

1. Enter opens the results, and the total on screen matches the route's `total` and `counts_exact` for the same
   body. When the route says `source: fallback`, the limited line shows.
2. Every body the page sends is accepted by the route: all results, a group, and a dataset filter, with no response
   above 299.
3. Show on graph leaves the results and puts records in the working set.
4. A query over 200 characters is refused on screen, never cut (rule 2).

**How it runs.** Take one stack, only after asking the orchestrator (memory: ask before taking a stack). The live tier
starts Vite on 5173 and drives a browser, so the browser has to reach the stack's Conduit, which needs
`CORS_ALLOWED_ORIGINS=http://localhost:5173`. The orchestrator ruled it runs on the server: one stack granted once studio
lands, with Vite and the Conduit both on the stack's host, so nothing crosses the network from the Mac. Record the log and the lease under `gates/`.

**Found before the run, fixed before the merge.** The route refuses a query over 200 characters (`MAX_QUERY_CHARS`) with
FastAPI's 422. Its `detail` is a list, so the page said only "The search could not be done (422)." The orchestrator ruled
on 14 November 2026: fix it now, with no `maxLength` on the box. The page now names the limit and the query's length,
counted by character as the route counts. The jsdom and keyboard cases came red first. Case 4 above asserts the words
against the real route.

**Also to check live.** The route refuses a dataset from another case with a string 422, and the page shows those
words as given. Check that the dataset filters the route offers are only the case's own, so the page cannot send
another case's dataset.
