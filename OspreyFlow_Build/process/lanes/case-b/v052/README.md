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
| `workload(name)` | `{kind, desired, replicas, ready, updated, available, unavailable, revisions_match, settled, current, tag, image, requests, limits, probe}` or None (`current`: every container of the template, init containers too, on the candidate's reference where the kept render's values pin its repository, and the main one pinned) |
| `init_container("workload/container")` | `{image, requests, limits, exit_code}` or None |
| `job(name)` | `{kind, schedule, suspended, image, requests, limits, succeeded, current, tag, steps: {name: {image?, exit_code}}}` or None (a `<set>` template: its newest successful run, by creation time) |
| `candidate()` | the full commit the run names (`--candidate`), or found (`auto`, `candidate_from_copy`): the one commit our kept render's images carry, in the copy's history with HEAD's own files |
| `release()` | the deployment's `OSPREY_RELEASE_VERSION` (the `ospreyflow-env` ConfigMap, the render's `release_version`): the manifest's version when the candidate's checkout carries its tag, else `dev-<short commit>`, which must be the candidate's |
| `image_pushed(repository)` | bool |
| `rds_setting("server_version" \| "max_connections")` | str or None |
| `shape()` | the deployed configuration's shape (`ospreyflow-files`' `osprey.yaml`) |
| `database_readers(db)`, `store_readers("elasticache" \| "opensearch")` | the workloads with a session or connection; for OpenSearch, each reader whose `SEARCH_PROBE` answers (raises with the reader's words otherwise: the probe prints one JSON line whatever fails, since r1's kubectl keeps stdout alone) |
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
- **OpenSearch** (`managed.opensearch`, 3a's, no longer pending from 1d914fe): platform's domain stand-in
  (lane/platform-v052-searchkind 6998234: the domain's VPC endpoint answered by the S3/STS stand-in, SigV4 for `es`
  checked against the namespace's role, unsigned refused 403 in the domain's JSON words, the rest proxied to an
  OpenSearch 2.17.1 pod) and **rules' search client** (the search_index service's client.py, on lane/rules-v052-index,
  unmerged). `SEARCH_PROBE` runs in the api pod: the client the deployment uses, with its own `OPENSEARCH_*` settings and
  IRSA credentials, counts the alias signed, and the signed client's own transport (hosts, connection class, TLS
  settings, timeout) less its signer counts it unsigned. The reader passes when it signs, the signed count is answered
  with documents and the unsigned one is refused 403 in the domain's words. **Run with rules' real client** and
  opensearch-py 3.2 against `search_domain_fake.py` (a count on the alias signed SigV4 for `es` answered, anything else
  refused as the domain refuses), both ways: `record_search_probe.py`, recorded in `gates/search-probe-real.txt` with
  the probe's hash. Over http, so the TLS settings are carried but not exercised; the stand-in itself is first met on
  the leased run after platform's searchkind and rules' index land. The same case is in the tests, skipped until both
  opensearch-py and the client are in this tree.
- **On main's manifest** (this branch rebased onto it, 13 November): 43 checks planned, the 7 pending all v052-superset
  (none pending since step 3b, 78564d2: the pending case now plants its own, in a copy of the candidate's manifest);
  `managed.opensearch` is planned and fails on a live run until platform's searchkind and rules' index both land (the probe
  was run with rules' real client against a server answering as the stand-in does, both ways: `gates/search-probe-real.txt`);
  `managed.rds.point_in_time_days` is held by the render check (only AWS shows it). The domain's egress placeholder
  is gone from the manifest (1d914fe); a placeholder left in one fails its egress check in words, never probed.
- **The run must exercise what it checks before `verify`:** spec 08 (sign-ins, uploads, loads); platform-b's
  dashboards step (`process/lanes/platform-b/v052/dashboards_check.py run`, lane/platform-b-v052-r1 44ac9d6), after the
  upgrade and before `verify`, which leaves `entra.superset`, `entra.report-sync`, both workloads and Superset's own
  database exercised; one backup and one restore (`r1_kind.py backup|restore`), and one run of each
  held-suspended CronJob (`kubectl create job --from=cronjob/<name>`). A bucket nothing wrote fails, by design.
- R1's kept render (`r1_kind.keep_render`, at `KEPT`): the candidate's image references, which `version` and
  `images.*` are held to; and R1's `state.json` `prefix` (the Terraform stand-in's), which the buckets are named by.

## Spec 08 on poc: `spec08_poc.py`

`tests/scenarios/test_phase8_exit_over_the_wire.py`, unchanged but for two cases split in two at the orchestrator's
request (14 November: the WebSocket's ticket, upgrade and snapshot from its delta, A7's refusal from the table's
survival, each seed-free half running on poc), under a pytest plugin that signs in as the Glass
does at the Entra stand-in (authorization code with PKCE, run from the api pod), skips each case that cannot run on
poc with its reason, and **stops the run** if the module (as written, whatever `-k` selects) has a case with no
disposition or a disposition for a gone case. The runner makes an empty case and uploads the CDR fixture and the seizure record through
`POST .../ingest/source-files`, the analyst's own door.

**14 of 29 cases run; 15 rest on a seed ("no seed path on poc").** The 15 rest on the `hmp`, `fixture-corp` and
`scenarios` seed datasets, and `harness.apply`'s seed is compose-only. What runs: the door, the ingest root and the
Studio, B1–B3 and the find-and-open case on their load, A1's grid, redraw and centroid, and B13 (both) and B14 on
the uploaded seizure record, and two seed-free halves split from seeded cases (the orchestrator's review of
step 6's sheet): the WebSocket through the poc ingress (ticket, upgrade and the empty snapshot; its delta waits on
the seed) and A7's refusal of a hostile field name (the events table's survival waits). B13–B14 were broken on every shape until c6c6044 (their fixture asked `POST
/v1/hotlists` and `GET /v1/alerts`, moved under the case); B12 and B19–B20 had drifted the same way. All five calls are
fixed, and `tests/scenarios/test_over_the_wire_routes_exist.py` holds every call in the module to the Conduit's routes.

`python spec08_poc.py table` prints the dispositions. On the kind cluster, under a lease, from OspreyFlow_Core:
`bash ../OspreyFlow_Build/process/lanes/case-b/v052/spec08_live.sh [pytest arguments]` (r1_kind.sh's own environment;
`r1_kind.sh py` hands its arguments to r1_kind.py's argparse and cannot run it).

## Red first

`plants.py`: 70 plants, each one check broken at its real call site in a copy of the driver, 8 in the route reading (in a copy, beside a copy of its module) and 2 in a copy of spec 08's module (a seeded step moved into a seed-free half); every one turns the
tests red, each record naming the test it failed, and the unplanted copy stays green (`gates/plants.txt`, with the
commit it ran at). Building them found
four gaps (no test had a CronJob whose runs never succeeded; a reader test whose pod order hid the finished-pod
plant; no test of an unobserved generation alone; none of a CronJob template still on the old release).
**The live run.** `verify_live.sh` (from OspreyFlow_Core, on the server, under a lease) runs `install_verify.py verify`
with r1_kind.sh's own environment (its tools, kubeconfig and the kind platform's folder; a test holds the three to
r1_kind.sh's by running both). `r1_kind.sh py` runs r1_kind.py alone, so it is not the way in.

**The candidate's commit.** Our images are tagged with the commit (`render.git_sha`) and the release reads `dev-<short>`
until the checkout is tagged (`release.checkout_version`). The stack_lease copy is its own repository, committed afresh
on top of the last for each run (`stack_lease.sh`, `commit --allow-empty`), so the verify run's HEAD is not the
upgrade's. **`--candidate auto` (the wrapper's default) finds it**: the one commit the kept render's images of ours
carry, which must be in the copy's history with HEAD's own files; a render from other files (v0.5.1's, a lane's head)
has another tree and names no candidate, and the run reports `FAIL version` with the reason. A named `--candidate`
overrides it. **What keeps `auto` matching:** the verify run sends the same files as the upgrade's (the same
worktree, nothing committed or added to it between the two runs, no record of the upgrade written into it first),
and the kept render is this run's (another lane's R1 run overwrites `KEPT`). Simplest: run the upgrade and the
verify in one `stack_lease.sh remote` command. Each way it stops matching fails, never passes. A release of `dev-unknown` (a render with
no git) fails. **Not checked:** that the candidate came by an upgrade at all (a fresh install of it passes alike); the
Helm history is the runbook's to show.
**Rounds 3 and 4's lesson (the reviews of 1f06074 and 8d1aadf, must 1 each):** the version check read our images' tag and held it to the
release, but the render tags them with the commit (`render.py`, `{registry}/{service}:{sha}`), so it failed every
real install while the tests passed, since the fake answered the tag the check wanted. The next fix read the
release alone and the fake answered `v0.5.2`, which the render writes only for a tagged checkout: before the tag it
writes `dev-<short>`. The fake now answers what the render writes before the tag (`dev-<short>` and `:<commit>` tags),
and plants give `dev-unknown`, `unknown`, v0.5.1's release and another commit. The stuck rollout is tested
in the status kubectl reports for it (one copy, maxSurge 1: 2 replicas, 1 updated, 1 ready, 1 unavailable). A walk over
every node of the YAML (not over `entries()`) injects an unplaced key and requires the run to stop.

    # from OspreyFlow_Core
    .venv/bin/python -m pytest -c ../OspreyFlow_Build/pytest.ini -p no:cacheprovider ../OspreyFlow_Build/process/lanes/case-b/v052/
    .venv/bin/python ../OspreyFlow_Build/process/lanes/case-b/v052/plants.py
    PYTHONPATH=.:packages:cli .venv/bin/python ../OspreyFlow_Build/process/lanes/case-b/v052/install_verify.py plan [--allow-pending]
