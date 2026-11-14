# live-redesign: fixture-corp's three red cases held to today's Glass

On 14 November 2026, on stack g (ospreyflow-test). The lease was taken at 10:45Z, under the orchestrator's grant, and the stack was brought down and released afterwards. The red is main's own code for these cases: `../live-drift/fixture-corp.last.log`, 2 of 5.

| Case | What changed | At 3de11a5 live |
|---|---|---|
| The query builder | Its *Add to the pattern* section starts folded (only *Pattern* opens), and a folded section is hidden. The case opens it and picks *Entity type* within its own group | Passes |
| The pathfinder | Its two ring members go on through the results page's *Show on graph*, which seeds only the result's records. A chosen suggestion is drawn three hops out, which left 7 nodes, not 2. Each `/seed` is held to its record | Passes (length 1) |
| Explain on a merged cluster | The pair goes on the same way, and *Same as* is found under *Expand by link type* | Red, and expected to stay red: see below |
| The NINO lookup, the threshold | Unchanged | Pass |

**Explain stays red, and the cause is a product defect, not drift.** It was measured live at 11:02Z, in run 20261114T110237Z-a31be917. The suggestion and search routes both return `resolution.cluster_id: None` for `corp-res-identical-1`.

The working set sends cluster ids only in a threshold or manual-resolution delta, and only for nodes whose cluster membership changed (`services/resolve/projection.py`'s `diff_clusters`). So a pair already merged at the case's threshold never carries a cluster id on the canvas, and *Explain cluster* is never offered for it. Fixture Corp's identical pair is merged at every detent.

The orchestrator ruled the fix required (rule 6's collapse at query time) and put it on the route as step 3h. The case is not weakened: it is the live check of that step.

**For step 6 on the 25th:** fixture-corp is expected at 4 of 5 until step 3h lands, then 5 of 5.
