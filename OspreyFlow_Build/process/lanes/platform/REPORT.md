# Platform · 4b: the cloud-platform RDS, db.t4g.large and max_connections 1000 (13 November 2026), ready to merge

Branch `lane/platform-poc-rds` on main `3f18d71`. Offline; nothing on the server. Merges into v0.5.1, with no R1 re-run, since kind's PostgreSQL is a stand-in.

| Exit (the orchestrator's 4b, as revised by the owner's decisions) | State | Proof |
|---|---|---|
| db.t4g.large in every shape | done (`terraform.RDS_INSTANCE_CLASS`) | `test_the_rendered_rds_sets_max_connections_to_1000_in_its_parameter_group` |
| max_connections 1000 in an `aws_db_parameter_group` (postgres16, pending-reboot) attached to the instance | done | the same test, ×3 fixtures |
| The least, derived in code (Superset and report sync ×2, an upgrade in progress): 918, 82 to spare | done (`connections.py`, counted again in the test) | red first, and red with Superset's or the upgrade's term dropped: `poc-rds/red-1000.txt` |
| INSTALL.md: N, why, MoJ module's `db_parameter` line, when it takes effect | done | `test_the_install_says_how_many_connections…` |
| Admin guide §6a, PDF reprinted alone | 1.92 (1.91 was the first ruling's, superseded the same evening) | `tools.docs_pdf` check exit 0 |
| ADR-114 Amendment 46 | written | `tools.adr_reservations_check` |
| CARRIES row 227 | closed at 1000 | — |
| Gates | cloud-platform, policy, backup, guide and PDF suites: 550 passed; after the rebase, 132 passed; ruff, and mypy on `harness/cloud_platform` | `poc-rds/gates.txt` |

**Also delivered:** part B's table, sent to you (`poc-rds/client-page-table.md`); R1's thin `test_webapp_sign_in` record (a `tail -3`), sent to platform-b (`gates/r1-webapp-sign-in-under-load.txt`).

**Open, the owner's:** Superset and the report sync, ×2 (the page) or ×1 (the poc render). The 918 takes ×2.

**Running:** nothing. **Paused:** Part 3 on `lane/platform-part3` at 28ef2f3 (stage 1 done; stage 2 begun, nothing uncommitted). Nothing pushed.
