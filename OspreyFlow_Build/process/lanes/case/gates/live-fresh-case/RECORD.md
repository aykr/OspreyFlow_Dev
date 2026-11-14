# live-fresh-case: `live.ts`'s `freshInvestigation` names the seeded case's dataset

On 14 November 2026, on stack g (ospreyflow-test). The lease was taken at 08:19:24Z, under the orchestrator's grant, and the stack was brought down and released afterwards. The runs used `process/lanes/case/live/run_search_results_live.sh` through `stack_lease.sh remote`, with `LIVE_SEED` and `LIVE_SPECS` set per run.

**The defect.** Since ADR-099 Amendment 12, `POST /v1/investigations` refuses a body that names no dataset (`422 {"error":"dataset_refused"}`). `freshInvestigation` sent none, so every live spec that makes a fresh case failed at its first step. The live tier is not in CI, so nothing showed it.

**The fix (5f071e7).** The fresh case names the one dataset the seeded case (`OSPREY_LIVE_INVESTIGATION_ID`) reads. The helper reads it through `GET /v1/investigations/{id}/datasets` and sends `dataset_ids`. A seeded case that reads other than exactly one dataset is refused in words, never guessed between. This keeps the helper's promise as a case reads today: the same records are reachable, and the working set starts empty.

## Red, with main's `live.ts` (at 5bbed10)

| Spec | Seed | Result | Log |
|---|---|---|---|
| `fixture-corp.spec.ts` | Fixture Corp | 5 of 5 failed at `freshInvestigation`: `422 {"error":"dataset_refused"}` | `red.fixture-corp.5bbed10.log` |
| `scenario-a-a12-a15.spec.ts` | HMP fixture | 3 of 3 failed the same way | `red.scenario-a.5bbed10.log` |

## With the fix (at 5f071e7)

- **Every fresh case was created.** No test failed at `freshInvestigation`.
- **A fresh case finds what the seeded case finds.** Asked directly (`diagnosis.fresh-case.log`), a fresh case naming `fixture-corp` reads that dataset only. Its search and suggestions return the same NINO, `corp-res-identical-1`, that the seeded case returns.
- **scenario-a: 1 of 3 passed** (`fixed.scenario-a.5f071e7.log`). A15 went from red at `freshInvestigation` to green. A12 and A13 failed on the spec's own drift from today's Glass, not the helper:
  - A12 waits for the old radial menu (`.radial-menu__list`), which case-b's selection actions (v052-selection, Parts C and E) replaced.
  - A13 asks for the page's one `dialog` and meets two: the keys panel shown by itself on a first visit ("Welcome back") beside "Record an assessment".
- **fixture-corp: 0 of 5 passed** (`fixed.fixture-corp.5f071e7.log`). All five got past `freshInvestigation` and failed on the spec's own drift:
  - Three wait for a suggestion named `Person: <record id>`. Today the box names an option by its value (`GlobalSearch`'s `displayValue`), and the route returns the record (above).
  - The query builder case timed out choosing an entity type.
  - The threshold case did not find its control: Match strictness, since ADR-097 step 3.

## Not run

| Spec | Why |
|---|---|
| `basemap.spec.ts` | Needs a PMTiles basemap build, which the throwaway stack does not have |
| `ingest-folder.spec.ts` | Needs a staged ingest folder |
| `scenario-b-document.spec.ts` | Needs an extraction model, which the stack does not run |

All three call the same `freshInvestigation`, so the fix reaches them, but no run here shows it.

## Also found

The runner's warm-up now prints what the browser saw (5bbed10). At load 26 (08:20Z) the Glass drew nothing for 10 minutes, and the Conduit got no request at all. At load 3 to 4 it drew in about a second. The blank first pages in the earlier runs line up with the host's load.
