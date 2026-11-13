# R1 · the run on kind (13 November 2026)

The `cloud-platform` profile, `shape: poc`, installed on kind by following P7b's rendered INSTALL.md block by block as
written, checked, backed up and restored by the recovery runbook's cloud-platform section, then removed by
DECOMMISSION.md. It ran on the test server (`osprey-r1`, one node capped at 32 GiB) beside osprey-small, which nothing
touched, from 15:40 to 18:12 UK. Preparation, the stand-ins and what each refuses are in `PREP.md`; Entra ID's stand-in
and what it cannot prove are in `ENTRA_STANDIN.md`; each fix's red is in `desk-reds.txt`; the records are in `run/`.

## For the owner, in plain words (most serious first)

Without these fixes, a platform team following the runbooks exactly would have:

1. **Had a dead Conduit after their first upgrade, and been told the install had succeeded** (findings 14 and 15). The
   Conduit opens 48 connection pools, about 50 connections at rest and up to about 200 under load, and an update runs
   the old and new Conduit side by side. A small RDS allows about 87, so the new Conduit stopped at start. And because
   neither the Conduit nor the Glass said when it was ready, every wait in the install passed anyway. Now both say when
   they are ready, and the install asks for a PostgreSQL that allows 750 connections.
2. **Destroyed the backups they had been told to keep** (finding 6). The decommission's last step, which empties the
   kept backups bucket and schedules its key for deletion, sat in the "run each block in order" sequence.
3. **Sent the last backup to the wrong bucket** (finding 1). The decommission named the backups bucket by an empty
   variable, so the last backup went to `s3://backups/…`, and the line's own check could not notice.
4. **Been stuck for ten minutes, then failed, removing the claims after any restore** (finding 12). A restore's Jobs
   outlive `helm uninstall`, and their finished pods kept the disks.
5. **Been unable to pin the images unless this version was published on GitHub and they could reach it** (finding 10).
6. **Found the `ospreyflow` command broken on every verb**: the owner's own on osprey-small too (finding 9). The
   runbook also told them to look for it where it never is (finding 8).
7. **Been unable to take up a decommission in a new shell after step 7** (finding 16).
8. **Been told a restore had finished while the service still answered 503** (finding 13).
9. **Believed a restore that had worked had failed**, from a 40-line Java stack trace in its log (finding 11). The
   recovery runbook now says what a healthy restore's log ends with.
10. **Locked everyone out with no way back in**: the "no administrator left" remedy restarted without installing the new
    list (finding 3).
11. **Registered Entra ID too late** (finding 2), **not checked the certificate's Secret** (finding 7), and **not known
    what `OSPREY_CURL_OPTS` was for** (finding 4).

## The run

| Stage | Result | Record |
|---|---|---|
| Cluster | `osprey-r1`: one node, 32 GiB cap; Calico, `gp2-expand`, ingress-nginx; the registry on 127.0.0.1 only | — |
| Install | every block of INSTALL.md as written (11), at the final head | `run/…175844Z-INSTALL.log` |
| Checks | 28 of 28: the door over TLS by name; nine Entra refusals; the first administrator; a person with no role refused; a case, a hotlist, a load through the Studio (profiled, mapped, verified, published, run), found by search, its alert raised | `run/…180425Z-check.log` |
| Backup | *A backup now*: both Jobs of one slot; ArcadeDB, ClickHouse and the Ingest claim | — |
| Restore | after a change made after the set: the change gone, the set's load and file back, the door answering at once; no stack trace in any step | `run/…180557Z-restored.log` |
| Decommission | from block 1; step 8's check: 0 left behind, the backups bucket kept with the last set (20261113T180600Z) complete; step 9 not run | `run/…181017Z-DECOMMISSION.log` |
| Down | 0 containers left; the server freed at 18:12 | — |

## Memory (the kubelet's working set; the node capped at 32 GiB)

| | After the install | After the restore |
|---|---|---|
| The node | 6.34 GiB | 7.81 GiB |
| ArcadeDB | 1416 MiB | 1175 MiB |
| NER | 630 MiB | 631 MiB |
| ClickHouse | 249 MiB | 606 MiB |
| LiteLLM | 482 MiB | 486 MiB |
| The Conduit (api) | 249 MiB | 247 MiB |
| Laurium | 187 MiB | 195 MiB |
| The worker | 160 MiB | 169 MiB |
| The Glass (workspace) | 13 MiB | 13 MiB |
| Postgres stand-in (RDS) | 163 MiB | 164 MiB |
| ingress-nginx | 186 MiB | 184 MiB |
| kube-apiserver | 415 MiB | 437 MiB |

The pods' requests come to about 26.6 GiB (ArcadeDB 12, ClickHouse 8, api 2, worker 2, laurium 1, NER 1, LiteLLM 0.5,
workspace 0.125) against under 8 GiB in use with this synthetic data. The requests, not the use, decide whether the
deployment fits a node.

## Findings found on kind (8–16), each fixed red first and the affected part run again

| # | What | Fix |
|---|---|---|
| 8 | INSTALL block 2's remedy, `.venv/bin`, never holds `ospreyflow` | dd8ff18: `uv tool install ./cli`, `~/.local/bin` on PATH |
| 9 | `ospreyflow` imported httpx at start, which its package does not declare: every verb failed | 00eb1d4 (merged 614ec43): standard library and PyYAML again (ADR-114 decision 3); `release` and `run` in the checkout |
| 10 | The pinned render asked ghcr.io for ours before taking the registry's copy | 2a12c8f |
| 11 | A restore that worked printed a stack trace (the Job's user cannot write `/home/arcadedb/log`) | 1538c4d, and the runbook's *A healthy restore* |
| 12 | The decommission stuck at step 4 after any restore | 043a35d: step 3 removes the release's Jobs and their pods |
| 13 | The restore's step 4 waited for ArcadeDB alone | 7a8c611 |
| 14 | The Conduit and the Glass had no readiness probe | dd3cc99 |
| 15 | An update's new Conduit refused at start: too few Postgres connections | cae6958: INSTALL asks for `max_connections` ≥ 750 (ADR-114 Am 43's figures) |
| 16 | The decommission's step 1 could not run after step 7 | b57f78f |

Bugs in R1's own driver and stand-ins (not the product's), fixed as found: the Valkey image's path on ECR Public;
`kubectl apply` of joined JSON; the stand-ins' certificate lacking `<svc>.<ns>.svc`; the IRSA stand-in setting
`AWS_ENDPOINT_URL_*`, which EKS never sets; the recipe's handling; two response shapes; the render folder pruned by
each sync; the Terraform stand-in leaving the buckets on its disk; the restored check run against an older set.

## Carried

- **The Conduit's 48 pools** (finding 15 (b)): one shared pool, or pool sizes from settings: the owner's ruling (CARRIES).
- **A misconfigured IRSA shows up as a slow 403 at staging.** pyarrow's AWS SDK falls through to EC2's metadata, with
  long retries, when web identity fails, and then stages with no credentials. Seen with the stand-in's own fault; worth
  knowing when a real platform's role trust is wrong.
- **The worker serves no port** and has no readiness probe.
- **Not modelled:** RDS point-in-time restore (the platform team's), S3's lifecycle rule, and Entra itself
  (`ENTRA_STANDIN.md`; the steps against the real tenant are INSTALL step 8).
