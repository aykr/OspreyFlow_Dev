# Step 6's driver (`v052-r1-driver`), built ahead

The install test on v0.5.2's candidate (ROUTE_052 step 6, led by platform-b): install v0.5.1, upgrade to the
candidate, **verify every manifest entry** (`install_verify.py`), **run spec 08** (`spec08_poc.py`), decommission.
Install, upgrade and decommission stay R1's: the rendered runbooks' blocks through `r1_kind.py` (platform's,
imported, never changed here). Offline-built; the live half is run on the day, under a lease.

## The verifier: `install_verify.py`

`plan(manifest)` turns every entry of `harness/cloud_platform/poc_manifest.yaml` into a check, **or stops before
anything runs** (`NotExercised`, "listed but not exercised"): an unknown section, entry or key, a database with no
known reader, a job step nobody named, a bucket nobody writes, or an entry still `pending`. `--allow-pending` is for
dry runs before 3a and 3b land; the install test does not pass it. The check table is the module's docstring.

`verify(manifest, deployment)` runs the plan against anything with `Deployment`'s methods (the interface, for
platform-b's dashboards check and for anyone fitting a new stand-in):

| Method | Answers |
|---|---|
| `workload(name)` | `{kind, desired, replicas, ready, updated, available, unavailable, revisions_match, settled, current, tag, image, requests, limits, probe}` or None (`current`: the template's reference is the candidate's, as the kept render's values pin it) |
| `init_container("workload/container")` | `{image, requests, limits, exit_code}` or None |
| `job(name)` | `{kind, schedule, suspended, image, requests, limits, succeeded, current, tag, steps: {name: {image?, exit_code}}}` or None |
| `image_pushed(repository)` | bool |
| `rds_setting("server_version" \| "max_connections")` | str or None |
| `shape()` | the deployed configuration's shape (`ospreyflow-files`' `osprey.yaml`) |
| `database_readers(db)`, `store_readers("elasticache" \| "opensearch")` | the workloads with a session or connection |
| `bucket_objects(bucket)` | count of objects |
| `entra_used(registration)` | the stand-in granted that registration a token (the API: a token for its audience) |
| `connects(host)` | a pod of the namespace reaches it on 443 (raises when the probe has no answer) |
| `reachable_outside(host)` | the kind node itself reaches it: the egress check's positive control |
| `render_differences()` | `manifest.differences(load(), rendered(config))` |

`KindDeployment` implements it on R1's cluster. **What it needs that is not there yet:**
- **Platform's signing Entra stand-in**, unmerged on lane/platform-v052-standin: `/authorize` and `/token` (R1's on
  main publishes keys and signs nothing, so the Glass's sign-in in `spec08_poc.py` needs it), and its grant line,
  `entra-standin: granted <grant_type> client=<client_id> audience=<aud>` (73f85ee, `r1_kind_servers.py`, in the shape
  `granted_clients` parses). `OSPREY_V052_TOKEN_BY=r1` takes `r1_kind.token()`'s token for a run before it lands, and
  then `entra.glass` fails: a token the driver mints writes no grant line.
- **The Postgres stand-in at 1000 connections**: on main it runs 750; 1d93ea0 on the same branch fills the manifest's
  figure from `connections.POSTGRES_MAX_CONNECTIONS`. Until it merges, `managed.rds` fails.
- **What `entra` does not check:** a registration's `kind`, `redirect`, `grants`, `exposes` and `app_roles`. The
  stand-in enforces platform's own registrations (`r1_kind_entra.yaml`), not the manifest's, and gives whatever roles
  it holds; these are the client administrator's words, held by nothing here.
- **An OpenSearch stand-in on kind** (3a's shape lists it, no longer pending; platform builds it, the orchestrator's
  word): `store_readers("opensearch")` raises until one exists, so `managed.opensearch` fails rather than passes.
- **The run must exercise what it checks before `verify`:** spec 08 (sign-ins, uploads, loads), a Superset sign-in
  and a report sync (platform-b), one backup and one restore (`r1_kind.py backup|restore`), and one run of each
  held-suspended CronJob (`kubectl create job --from=cronjob/<name>`). A bucket nothing wrote fails, by design.
- R1's kept render (`r1_kind.keep_render`, at `KEPT`): the candidate's image references, which `version` and
  `images.*` are held to; and R1's `state.json` `prefix` (the Terraform stand-in's), which the buckets are named by.

## Spec 08 on poc: `spec08_poc.py`

`tests/scenarios/test_phase8_exit_over_the_wire.py`, **unchanged**, under a pytest plugin that signs in as the Glass
does at the Entra stand-in (authorization code with PKCE, run from the api pod), skips each case that cannot run on
poc with its reason, and **stops the run** if the module (as written, whatever `-k` selects) has a case with no
disposition or a disposition for a gone case. The runner makes an empty case and uploads the CDR fixture through
`POST .../ingest/source-files`, the analyst's own door.

**9 of 27 cases run; 15 rest on a seed ("no seed path on poc"); 3 are broken on every shape.** The 15 rest on the
`hmp`, `fixture-corp` and `scenarios` seed datasets, and `harness.apply`'s seed is compose-only. What runs: the
door, the ingest root and the Studio, B1–B3 and the find-and-open case on their load, A1's grid, redraw and
centroid. **B13 (both cases) and B14** seed nothing they assert, but their fixture `seizure_alert` asks
`POST /v1/hotlists` and `GET /v1/alerts`, routes the Conduit now has only under a case and by id: the module has
drifted from the API (a test pins that both routes are still gone).

`python spec08_poc.py table` prints the dispositions.

## Red first

`plants.py`: 39 plants, each one check broken at its real call site in a copy of the driver; every one turns the
tests red and the unplanted copy stays green (`gates/plants.txt`). They found two gaps while being built (no test
had a CronJob whose runs never succeeded; a reader test whose pod order hid the finished-pod plant; no test of an
unobserved generation alone; none of a CronJob template still on the old release). The stuck rollout is tested
in the status kubectl reports for it (one copy, maxSurge 1: 2 replicas, 1 updated, 1 ready, 1 unavailable). A walk over
every node of the YAML (not over `entries()`) injects an unplaced key and requires the run to stop.

    # from OspreyFlow_Core
    .venv/bin/python -m pytest -c ../OspreyFlow_Build/pytest.ini -p no:cacheprovider ../OspreyFlow_Build/process/lanes/case-b/v052/
    .venv/bin/python ../OspreyFlow_Build/process/lanes/case-b/v052/plants.py
    PYTHONPATH=.:packages:cli .venv/bin/python ../OspreyFlow_Build/process/lanes/case-b/v052/install_verify.py plan [--allow-pending]
