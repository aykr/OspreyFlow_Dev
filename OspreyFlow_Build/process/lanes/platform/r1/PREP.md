# R1 · preparation on the Mac (12 November 2026)

The client install's acceptance (`process/lanes/platform/BRIEF.md`): the `cloud-platform` profile in
`shape: poc` on kind, installed by P7b's rendered `INSTALL.md` exactly as written, checked, backed up and
restored by the recovery runbook's cloud-platform section, removed by `DECOMMISSION.md`. Nothing has run on
a cluster yet: the server is the demo's until the orchestrator says otherwise.

## The run, in order (on the server, from `~/osprey-runs/platform`'s `OspreyFlow_Core`)

`G=../OspreyFlow_Build/process/lanes/platform/gates`. No lease is needed for kind (no stack a or b); the
server's Docker is the orchestrator's to give. Never a command near `osprey-small`'s containers or volumes.

| # | Command | What it does | Downloads |
|---|---|---|---|
| 0 | `bash $G/r1_kind.sh tools` | kind 0.27, kubectl 1.32.2, helm 3.16.3, checksummed, under `~/osprey-runs/platform.tools/bin` | yes (owner's yes) |
| 1 | `bash $G/r1_kind.sh up` | `osprey-r1`, one node capped at `R1_NODE_MEMORY` (32g), Calico, `gp2-expand` only, ingress-nginx, registry on 127.0.0.1:5001 | node image, Calico, ingress |
| 2 | `bash $G/r1_kind.sh py platform` | the platform before the install: managed stores, Entra, names, certificates (below) | postgres, valkey (AWS's mirror) |
| 3 | `bash $G/r1_kind.sh py runbook INSTALL` | the install's blocks as written; the record per block | the third-party images |
| 4 | `bash $G/r1_kind.sh py memory` | the node's and every pod's actual memory (the kubelet's summary) | — |
| 5 | `bash $G/r1_kind.sh py check` | the check list (below) | — |
| 6 | `bash $G/r1_kind.sh py backup` | *A backup now*, as the recovery runbook gives it | — |
| 7 | (a change after the set) then `bash $G/r1_kind.sh py restore` | *A restore*, steps 1–4, placeholders filled from step 2's own output | — |
| 8 | `bash $G/r1_kind.sh py runbook DECOMMISSION` | the decommission's blocks as written, its check last | — |
| 9 | `bash $G/r1_kind.sh down` | the cluster, its registry and our images; nothing else | — |

A block that fails stops the run; its record names it. After a fix, `runbook INSTALL --from N` runs again
from block N (the affected part), as the brief asks.

## Every block, what it needs, and its stand-in on kind

**INSTALL.md** (rendered from `gates/r1_kind_osprey.yaml`; `CONFIG` names it, as the runbook allows).

| Block | Step | Needs | On kind |
|---|---|---|---|
| 1 | 1 settings | bash, `.venv`, kubectl, helm, the context's namespace = `$NS` | the context set to `ospreyflow-poc` before the run, as *What it needs* asks |
| 2 | 1 rights | `ospreyflow` on PATH, buildx, `can-i` statefulsets and claims | as written (the runner puts `.venv/bin` on PATH, as block 2's own words say) |
| 3 | 2 (platform) | the Terraform PR applied | **stand-in**: every `kubernetes_secret` and `kubernetes_service_account` the rendered `terraform/*.tf` declares, each value as the apply would give it (an unknown expression stops it); the AWS side at the S3/STS/KMS stand-in (the rendered roles' policies and trust, the buckets, the backups' key); the IRSA webhook |
| 4 | 2 check | the Secrets and the service account | as written |
| 5 | 3 render | the checkout at its tag | as written (unpinned) |
| 6 | 3 (platform) | `aws ecr get-login-password` | **stand-in**: the cluster's registry needs no sign-in |
| 7 | 3 push | Docker with buildx, the registry | as written, to `localhost:5001` |
| 8 | 4 render | — | as written (pinned) |
| 9 | 5 helm | helm 3.16+, rights in the namespace | as written; every rollout to 900 s |
| 10 | 6 check | — | as written |
| — | 6 later | only when no administrator is left | not run (fenced `bash later`, R1) |
| 11 | 7 check | the door's name resolving, its CA trusted | `OSPREY_CURL_OPTS="--cacert …/ca.crt --resolve ospreyflow.r1.test:443:<node>"` (the runbook's own option) |

**DECOMMISSION.md**: blocks 1–5 as written (the last backup by the CronJob's own Job, under the IRSA
stand-in); step 6's two platform blocks → the S3 stand-in's four buckets emptied, the images left with the
registry (gone at `down`); step 7 → what the Terraform made removed but the kept backups bucket and key; step
8's platform blocks → `state.txt` (empty: the kept resources were taken out), `buckets.txt` from the stand-in,
and `volumes.json` (the cluster's volumes, the platform team's listing) in place of the disks; then the
decommission check as written. Step 9 is `bash later`: not run.

**deploy/RUNBOOK.md, cloud-platform section**: *A backup now* (`<namespace>` filled); *A restore* steps 1–3,
then step 4 with `<each one noted>` taken from step 2's own `NAME COPIES` table. The RDS point-in-time
restore is the platform team's: the Postgres stand-in is left as it is, and said so.

## The stand-ins, and what each refuses

- **Entra ID** (the owner's choice, 12 November): a pod answering as `login.microsoftonline.com` (CoreDNS,
  inside the cluster only), the tenant's discovery and keys; another tenant is refused (AADSTS90002). The
  tokens are minted on the server with a key that never enters the cluster. The Conduit is unchanged.
- **S3, STS, KMS**: P9's `s3_standin.py`, which refuses what AWS refuses (SigV4, expiry, web identity trust,
  IAM and bucket policies, SSE-KMS by the key's policy), on 443 at the S3 and STS names, its disk a claim.
- **EKS's IRSA webhook**: a mutating admission webhook for `ospreyflow-poc` alone, failing closed: the
  projected token and role for an annotated service account, the stand-in's endpoints, and the stand-in
  CA beside the public roots for every pod. Nothing else in any pod is changed.
- **RDS, ElastiCache**: P7's (Postgres 16 with TLS forced and a master user that is no superuser; Valkey
  with TLS and a password).

## What "checked" means (`r1_kind.py check`, then backup and restore, then the decommission)

1. The Conduit answers through the Glass's door, over TLS, by name.
2. Sign-in refuses another tenant's token, another audience's, an expired one, an app-only one and a
   guest's (401 or 403 each).
3. The first administrator signs in by the tenant's token; `/v1/me` holds `osprey-admin` and the token's
   clearance; *Admin › People* lists them; they give themselves analyst and data engineer there.
4. **A case**: made with a new dataset.
5. **A rule**: a hotlist on a synthetic number, before the load.
6. **A load**: a two-row CSV uploaded to the Ingest root's claim, a recipe made, profiled, mapped
   (`gates/r1_kind_row_template.yaml`), verified, published and run; what it made is found by search.
7. The rule's alert is raised by the load.
8. **A backup set**: both runs of one slot; the set's manifest in the backups bucket.
9. **A restore beside a live store**: after a change made after the set, the restore's Jobs bring ArcadeDB,
   ClickHouse and the Ingest claim back to the set; the change is gone and the load is there.
10. **The decommission's leftovers**: the decommission check passes, naming the backups bucket and key as
    kept and nothing else.

## Memory

The poc render asks about 27 GiB in requests (limits about 33). The node is capped at 32 GiB beside
osprey-small capped at about 24 by the demo lane. `memory` records the node's limit and working set and
every pod's working set from the kubelet, after the install and after the restore.

## Found by reading, before any run (fixed, each red first: `desk-reds.txt`)

1. The decommission named the backups bucket `$PREFIXbackups`, an empty variable to bash: the last backup
   `s3://backups/…`, steps 7 and 9 on bucket `""`; the line's own check could not fail.
2. The Entra registrations were asked for "before step 5" in step 6.
3. The way back in rendered and restarted but never installed the values, so the old list was read.
4. Step 7's `OSPREY_CURL_OPTS` was named nowhere.
5. An invalid escape in the runbooks' f-string (a SyntaxWarning, an error in a later Python).
6. **The decommission's step 9 was in the "run each block in order" sequence**: a platform team following
   it to the letter deleted the retained backups bucket and scheduled its key's deletion at the
   decommission. It and the install's way back in are now fenced `bash later`.
7. Install step 2 did not check the certificate Secret `cloud_platform.tls_secret` names.

Known and not R1's (from the guide): the recovery runbook's upgrade backup scales `deployment/report-sync`,
which this profile does not render, and scales the Conduit back to 1 rather than as noted.
