# Case lane · P9 (scheduled, encrypted backups of ArcadeDB and ClickHouse to S3 by IAM role) · report, 12 November 2026

Gated head **`7916044`** on `lane/case-p9`, rebased on main `00bb30a` (P7b, 3673660). Gates (`gates/7916044.notes.md`): `make -k ci` **exit 0** (cp-policy-check 0 violation(s) on all four fixtures; harness-a11y in slot 14, 34 passed); `make test` **12339 passed**, 2 failed (the server's GPU, OpenSearch's memory case: known, not this branch's), 2 xfailed strict (the restores' rows awaiting `P9_rows.diff`). Plants **72 of 72 red** (`gates/p9_reds.r4.log`).

| Exit criterion | State | Proof |
| --- | --- | --- |
| Scheduled, encrypted backup to S3 by IAM role, no stored key | **Met** | `tests/cloud_platform_backup/`; kind round 3 (`gates/p9_kind.r3.log`) |
| Kind round trip against a stand-in refusing what S3 refuses; every refusal red first | **Met** | `p9_kind_{roundtrip,reds,restore_refused,osprey_sources,osprey_bound_red}.r3.json` |
| cp-policy-check green, red on a plant | **Met**, on the merged render too (both diffs applied: 60/53/67/67 manifests, 0 violation(s)) | `gates/p9_cp_policy_merged.r1.txt`; `test_backups_chart.py`'s plants |
| Restore timed under a lease | **Met**: 70.8 s end to end, backup 7.1 s, under the case lane's lease on stack c | `gates/p9_kind_roundtrip_timed.r3.json` |
| P7b's rows (61f782d) against P9's pods as built | **Three mismatches found and fixed**: restore-claims lacked `kube-api` (every claims restore refused), restore had an unused ArcadeDB row, the backup's key not allowed; ArcadeDB's password now to the backup's container alone | `test_backups_rows.py`; `P9_rows.diff` (583 passed with it, its 3 plants red) |
| ADR-148 Amendment 7, runbook, friction row | **Met** | `spec/06_DECISIONS.md`, `deploy/RUNBOOK.md`, `process/friction/2026-11-11-case-p9-backups.md` |

**Rulings applied:** A (osprey's RESTORE of ClickHouse's own part accepted as a measured limit, listed for the owner; terms 1–4); ClickHouse's token unmounted, `TOKEN_ALLOWED` unchanged (11 November).
**For the orchestrator to apply, in order:** `P9_render.diff` (refreshed on P7b's render; four files), `P9_rows.diff`, `P9_decommission.diff` (still applies); `P9_carries.diff` (the live-checks row: ClickHouse's IRSA with no default token, to measure on EKS). Still open: ADR_RESERVATIONS row 195 marked written; platform's `_file`, `_q`, `_secret` made public.
**Left (P9b, Amendment 7's Left):** the alert on a failed run; object lock; production's restore beyond one copy; the restore's own service account; the backup user's networks.
**Questions for the owner:** ruling A's limit (osprey can RESTORE a set's ClickHouse part), listed in Amendment 7 point 4.
**Running:** the osprey-p9 kind cluster, up for the orchestrator's review (round 3's render, from before 7916044's changes); torn down on the orchestrator's word, or at the latest by a systemd timer on the server, Friday 13 November 11:25 UK. No stack lease held.
