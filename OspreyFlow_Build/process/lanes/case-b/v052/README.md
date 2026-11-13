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
| `workload(name)` | `{kind, desired, ready, image, requests, limits, probe}` or None |
| `init_container("workload/container")` | `{image, requests, limits, exit_code}` or None |
| `job(name)` | `{kind, schedule, suspended, image, requests, limits, succeeded, steps: {name: {image?, exit_code}}}` or None |
| `image_pushed(repository)` | bool |
| `rds_setting("server_version" \| "max_connections")` | str or None |
| `database_readers(db)`, `store_readers("elasticache" \| "opensearch")` | the workloads with a session or connection |
| `bucket_objects(bucket)` | count of objects |
| `entra_used(registration)` | the stand-in granted that registration a token (the API: a token for its audience) |
| `connects(host)` | a pod of the namespace reaches it on 443 |
| `render_differences()` | `manifest.differences(load(), rendered(config))` |

`KindDeployment` implements it on R1's cluster. **What it needs that is not there yet:**
- **The Entra stand-in's grant line** (platform, `r1_kind_servers.py`): one stderr line per token issued,
  `entra-standin: granted <grant_type> client=<client_id> audience=<aud>`. Without it `entra.*` fail.
- **An OpenSearch stand-in on kind** (3a's shape lists it, no longer pending): `store_readers("opensearch")` raises
  until one exists, so `managed.opensearch` fails rather than passes.
- **The run must exercise what it checks before `verify`:** spec 08 (sign-ins, uploads, loads), a Superset sign-in
  and a report sync (platform-b), one backup and one restore (`r1_kind.py backup|restore`), and one run of each
  held-suspended CronJob (`kubectl create job --from=cronjob/<name>`). A bucket nothing wrote fails, by design.
- `state.json` keys `bucket_prefix` (the Terraform stand-in's) and, if any host is a placeholder, `egress_hosts`.

## Spec 08 on poc: `spec08_poc.py`

`tests/scenarios/test_phase8_exit_over_the_wire.py`, **unchanged**, under a pytest plugin that signs in as the Glass
does at the Entra stand-in (authorization code with PKCE, run from the api pod), skips each case that cannot run on
poc with its reason, and **stops the run** if the module has a case with no disposition or a disposition for a gone
case. The runner makes an empty case and uploads the ingest fixtures (CDR, SMS, seizure record) through
`POST .../ingest/source-files`, the analyst's own door.

**8 of 27 cases run; 19 rest on a seed and are marked "no seed path on poc".** They rest on the `hmp`,
`fixture-corp` and `scenarios` seed datasets, and `harness.apply`'s seed is compose-only. What runs: the door,
the ingest root and the Studio, B1–B3 (and the find-and-open case on their load), A1's grid, redraw and centroid.
What does not: A2–A15 and A1's geocoding, B4–B21 (B13/B14 too: their handset and first SIM are seeded).

`python spec08_poc.py table` prints the dispositions.

## Red first

`plants.py`: 15 plants, each one check broken at its real call site in a copy of the driver; every one turns the
tests red and the unplanted copy stays green (`gates/plants.txt`). It found one gap while being built: no test had a
CronJob present whose runs never succeeded; one does now.

    # from OspreyFlow_Core
    .venv/bin/python -m pytest -c ../OspreyFlow_Build/pytest.ini -p no:cacheprovider ../OspreyFlow_Build/process/lanes/case-b/v052/
    .venv/bin/python ../OspreyFlow_Build/process/lanes/case-b/v052/plants.py
    PYTHONPATH=.:packages:cli .venv/bin/python ../OspreyFlow_Build/process/lanes/case-b/v052/install_verify.py plan [--allow-pending]
