# The poc shape's images, repositories and resources, for the client page (13 November 2026)

**Sources:**
- Ours and upstream: R1's block 7 push (`r1/run/20261113T175844Z-INSTALL.log`, at e18c263).
- Repositories: `terraform.ecr_repositories` over the render of the synthetic poc deployment (`tests/fixtures/cloud_platform/poc.yaml`) at f05a33e.
- Resources: `harness/cloud_platform/profile.yaml` (`resources`, `poc.cpu_limits`) as rendered into `values.yaml`.
- The CronJobs and Jobs: `deploy/helm/ospreyflow/templates/backups.yaml`.

**Caveats:**
- Superset and the report sync are not rendered in v0.5.1: the render refuses `reporting` on this profile. Their rows are the profile's own figures, which no render has yet used. Their images were not pushed by R1.
- The profile calls every figure "proposals, not measurements". R1's measured use is in `r1/RUN.md`.

## 1. Images and ECR repositories at v0.5.2 (v0.5.1's nine, plus two)

| ECR repository | Ours or upstream | Source (what `ospreyflow images push` builds or copies) | In v0.5.1 | Used by |
|---|---|---|---|---|
| `ospreyflow/workspace` | ours | built: `apps/workspace/Dockerfile` | yes | workspace |
| `ospreyflow/api` | ours | built: `services/api/Dockerfile` (`CONDUIT_JAVA=omitted`) | yes | api; the backup CronJobs; the restore Jobs' steps but one |
| `ospreyflow/worker` | ours | built: `services/worker/Dockerfile` | yes | worker |
| `ospreyflow/ner` | ours | built: `services/ner/Dockerfile` | yes | ner |
| `ospreyflow/laurium` | ours | built: `services/laurium` (only when Laurium is the extraction engine, as in the poc fixture) | yes | laurium |
| `ospreyflow/superset` | ours | built: `deploy/superset/Dockerfile`, from `apache/superset@sha256:16b50bbef6648912a79e3293d418fefa743ce555d36c5af6b85d859119ed7f88` | **v0.5.2** | superset |
| `ospreyflow/report-sync` | ours | built: `services/report_sync/Dockerfile`, from `python:3.12-slim` | **v0.5.2** | report-sync |
| `arcadedata/arcadedb` | upstream | copied: `arcadedata/arcadedb:26.10.1@sha256:01506549bcb4a6d16af678ee43718850eba605430a3720a6b0398cb0470c710d` | yes | arcadedb; the restore Job's `restore-graph` step |
| `clickhouse/clickhouse-server` | upstream | copied: `clickhouse/clickhouse-server:25.8.33.6@sha256:0152dd511befe6a2c2ef53e930726179669b08116da78500b37c51c96ff5ee77` (Keeper runs inside it on poc) | yes | clickhouse |
| `berriai/litellm` | upstream | copied: `ghcr.io/berriai/litellm@sha256:d295634e09c648dcdb72c4cc2dd226f5fb87823a73e88cbbed6f205e4deb044b` | yes | litellm |
| `postgres` | upstream | copied: `postgres:16.4@sha256:e62fbf9d3e2b49816a32c400ed2dba83e3b361e6833e624024309c35d334b412` | yes | litellm's `litellm-db` init container |

- **What v0.5.1 has:** 9 repositories, 5 ours and 4 upstream. v0.5.2 has 11, 7 ours and 4 upstream.
- **How the render pins them:** each by the digest the client's registry gives its copy, for ours and upstream alike. These are not the upstream digests above.
- **To confirm when they are first rendered:** whether Superset or the report sync adds an init container on another image, for example a database step.

## 2. Pods and containers: counts, requests and limits (poc, as v0.5.1 renders them)

The poc shape runs one of each workload.

| Workload | Kind | Count | Container | CPU request | CPU limit | Memory request | Memory limit |
|---|---|---|---|---|---|---|---|
| workspace | Deployment | 1 | workspace | 100m | 500m | 128Mi | 256Mi |
| api | Deployment | 1 | api | 500m | 2 | 2Gi | 4Gi |
| worker | Deployment | 1 | worker | 500m | 2 | 2Gi | 4Gi |
| ner | Deployment | 1 | ner | 250m | 1 | 1Gi | 2Gi |
| laurium | Deployment | 1 | laurium | 250m | 500m | 1Gi | 2Gi |
| litellm | Deployment | 1 | litellm | 250m | 500m | 512Mi | 1Gi |
| litellm | (init) | — | litellm-db (postgres) | 100m | 500m | 256Mi | 512Mi |
| arcadedb | StatefulSet | 1 | arcadedb | 1 | 2 | 12Gi | 12Gi |
| clickhouse | StatefulSet | 1 | clickhouse (Keeper inside) | 1 | 2 | 8Gi | 8Gi |
| **Total, v0.5.1** (running containers; init not added) | | **8 pods** | | **3.85** | **10.5** | **26.6 GiB** | **33.3 GiB** |
| superset | Deployment | 1 (poc) | superset | 250m | 500m (poc default) | 1Gi | 2Gi |
| report-sync | Deployment | 1 (poc) | report-sync | 100m | 500m (poc default) | 256Mi | 512Mi |
| **Total, v0.5.2** | | **10 pods** | | **4.2** | **11.5** | **27.9 GiB** | **35.8 GiB** |

**Superset and the report sync:**
- Their CPU limits are the poc default (`poc.cpu_limits.default`, 500m), since the profile names none for either.
- The owner ruled one copy of each on poc (13 November 2026), as the render gives it. The connection count takes each shape's own copies (`connections.least_for`): 834 on poc, 918 in production, both under the 1000.

## 3. CronJobs and Jobs (from the chart, in the poc render)

| Name | Kind | When | Container (image) | CPU request / limit | Memory request / limit |
|---|---|---|---|---|---|
| `ospreyflow-backup` | **CronJob** | `15 2 * * *` (deadline 6 h), on ArcadeDB's node | backup (`ospreyflow/api`) | 500m / 2 | 2Gi / 4Gi |
| `ospreyflow-backup-claims` | **CronJob** | the same slot; poc only (the Ingest claim) | backup-claims (`ospreyflow/api`) | 500m / 2 | 2Gi / 4Gi |
| `ospreyflow-restore-<set>` | **Job** | only during a restore, by the recovery runbook | init: verify, fetch-graph, writers (`ospreyflow/api`), each 500m / 2 and 2Gi / 4Gi; init: **restore-graph** (`arcadedata/arcadedb`), **1 / 2 and 12Gi / 12Gi**; then restore-analytics (`ospreyflow/api`), 500m / 2 and 2Gi / 4Gi | (by step) | (by step) |
| `ospreyflow-restore-claims-<set>` | **Job** | only during a restore | init: verify; then restore-claims (both `ospreyflow/api`) | 500m / 2 | 2Gi / 4Gi |

**The restore Job's `restore-graph` step:**
- It asks for ArcadeDB's own 12Gi.
- The recovery runbook's step 2 scales the writers to 0, ArcadeDB among them, and waits for their pods to go before the Job starts. So that 12Gi is free, and a restore needs no more than steady state. This held on kind (R1).
- The render has no other Jobs (`values.jobs` is empty on poc).
