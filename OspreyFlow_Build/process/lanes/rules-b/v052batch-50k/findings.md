# rules-b v052batch-50k: the 50,000-node batch measurement (ADR-151 Cost)

Run on ospreyflow-test, stack b, under the lease rules-b took at 2026-11-14T13:51:02Z (purpose: "v052batch-50k:
the 50,000-node batch measurement (orchestrator's queue, rules-b first, make idle)"). The run was taken after the
QUEUE showed rules-b first and `pgrep -x make` was empty, and the line was deleted afterwards. Branch
lane/rules-b-v052batch-50k at b551fc7 (on main fefc336, am18 included). The script is `measure50k.py` and the full
log is `run.txt` (secrets masked). Wall time was 196 s and the script exited 0. The stack was brought down and the
lease released afterwards.

An earlier attempt at 13:50:13Z ran nothing: the remote shell starts in OspreyFlow_Build, `cd OspreyFlow_Core`
failed, and the script exited 1 after 1 s. The stack came down and the lease was released at once.

Host at the start (13:51:18Z): load 2.44 / 2.97 / 5.45; free -g: 62 total, 28 used, 13 free, 33 available.
At the end (13:54:33Z): load 2.58 / 2.72 / 4.88; 62 total, 25 used, 17 free, 37 available.

## Shape

There are 10 OFFICIAL hubs. Each hub has 4,999 OFFICIAL leaves and 50 SECRET leaves, all in one dataset. That
writes 50,500 nodes and 50,490 links. An OFFICIAL reader sees 50,000 nodes and 49,990 links.

## Figures

| What | Figure |
| --- | --- |
| Nodes, `upsert_nodes` in chunks of 2,000 | 50,500 in 61.9 s (about 815/s; 255/s before am18) |
| Links, `bulk_load_edges` | 50,490 in 37.9 s |
| The batch end to end (real JobWorker), expand from 10 hubs | reached "Counting the links among 50,000 nodes" at 16.3 s |
| The batch end to end | **failed** at 16.8 s, in `edges_among` (below). The state is `failed` with the failure words, and no view was saved or cut (rule 2 held) |
| `edges_among` as built, 5,000 ids | 9.9 s, 4,990 links |
| `edges_among` as built, 10,000 ids | 19.7 s, 9,990 links |
| `edges_among` as built, 25,000 ids | **ArcadeDB 400 after 0.2 s**: Groovy `ClassTooLargeException` ("Class too large: Script9") |
| `edges_among` as built, 50,000 ids | the same 400 (the batch's own call) |
| Comparison A (RIDs, `hasId(within(rids))` in the traversal), 5k / 10k | 5.1 s / 9.4 s, same link-id set as built both ways (0 / 0) |
| Comparison A, 25k | the same `ClassTooLargeException` |
| Comparison B (RID-start chunks of 1,000, far end's id tested in Python), 5k / 10k | 3.3 s / 4.1 s, same link-id set as built both ways (0 / 0) |
| Comparison B, 25k / 50k | 4.9 s / 6.2 s; 24,990 / 49,990 links. The counts the shape predicts, but there is no as-built answer to set-compare against at these sizes |

Steps 5 and 6 (the view's SECRET count, `pg_column_size`, `get_nodes` over the view) did not run, because no view
was saved. The 4,001-node figures in ADR-151's Cost still stand for them.

## What is slow, and what breaks

`render_edges_among_gremlin` (packages/adapters/graph_arcadedb, called by `edges_among` at adapter.py:1123) puts
every id into the Groovy script as a literal list, twice: `g.V().has("id", within([...]))...outE()...where(inV().has("id",
within([...])))`. Its plan at 5,000 ids (`.profile()`, 9.45 s total) shows:

- `GraphStep(vertex,[])` visits **all 50,568 vertices**. The id filter is not an index lookup; every vertex in the
  store is tested.
- `HasStep(id.within([...]))` on the start takes 4,314 ms (45.7%). The far-end `TraversalFilterStep(EdgeVertexStep(IN),
  HasStep(id.within(...)))` takes 4,625 ms (49.0%), almost all of it in the same `within` (4,395 ms).
- Everything else (access steps, `outE`, dedup) takes under 5%.

So the time is spent on the two `within` tests, which grow with the id list times the store (5k: 9.9 s, 10k: 19.7 s,
linear in ids at a fixed store). Past some size between 10,000 and 25,000 ids, the script no longer compiles at all:
the JVM refuses a class that large. **On main today, then, a batch past roughly 10–25k nodes always fails, and
`open_view` on a view of that size fails as well, since it counts with the same call.** ADR-151's 50,000 view cap
cannot be reached through either path.

## Proposal (not made; for the owner and the orchestrator to decide)

Change `edges_among` to comparison B's shape:

1. Look up the ids' record ids with the adapter's own SQL lookup on the unique id index (`_record_ids`,
   as `get_nodes` already does).
2. Start the traversal from those RIDs in chunks of 1,000:
   `g.V(<rids>).<access>.outE(<types>).<access>.as('e').inV().<access>.as('t').select('e','t').by(elementMap()).by(values('id'))`.
3. Keep an edge only where its far end's id is in the requested set, and dedup by edge id.

Why this keeps the rules:

- Access is still applied inside the traversal on the start, the edge and the far end (rule 3). The Python step only
  narrows to the requested set, which the caller already knows; it is not an access check, and it stays in the
  adapter.
- Nothing is cut (rule 2). Every out-edge of every chunk is read, and an edge between two requested nodes is found
  from its source's chunk.
- Figures: 5k 3.3 s (as built: 9.9 s), 10k 4.1 s (19.7 s), 50k 6.2 s (fails). The link-id sets were exactly equal to
  as built, both ways, at every size where as built answered.

What it needs before it lands:

- The edges_among conformance cases, plus one that crosses a chunk boundary and one with a SECRET far end
  (rule 4, rule 12).
- A set-equality check against a reference at 25k and 50k. The fixture's own expected link ids would do, since
  as built cannot answer there.
- A note on cost: the RID lookup's round trips plus one Gremlin call per 1,000 ids (about 100 calls at 50k).

Comparison A alone does not fix this. It halves the time, but still inlines the whole list and fails to compile at
25k.

Whose file: the graph adapter's (`render_edges_among_gremlin`, `edges_among`). This lane has not changed it.
