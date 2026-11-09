# studio-b lane · report · L1.6 (phase 9: connectors, and the screening-list connector; ADR-140 Amendments 13 and 15, ADR-133 Amendment 9), 9 November 2026

1. **Phase 9's exit: met.** `visit_bookings` is registered from a synthetic NOMIS replica with an incremental watermark, and *Refresh now* reads only the new rows. A SQL source's file then loads only the new row (`test_sql_connector_live.py`). Connections name their secret and never hold it (`test_connector_schemas.py`, `test_connector_routes.py`).
2. **Each template maps its synthetic golden file: met** (7 templates; `tests/connectors/test_list_templates.py`).
3. **A rule offers only subscribed lists, never another dataset's: met at the route** (`test_list_connector.py`, `test_list_connector_routes.py`, `test_subscribed_lists_seam.py`). The rule's picker is the rules lane's (in CARRIES).
4. **Import idempotent per version: met,** proven on the real keeper too (`test_list_rows_parquet_live.py`). **Import replaces L1.4's stand-in: met** (`test_subscribed_lists_seam.py`).
5. **Keyboard (rule 13) and axe: met in the earlier session.** `sources-connectors.spec.ts` (12 ids, `L1.6_action_registry.diff`); `every-harness` covers 10 states × 3 themes. No Glass change since, so not re-run.
6. **ADR-140 Amendment 15** (the owner's ruling 7a): `connectors.private_hosts` in `osprey.yaml` admits named private hosts or networks. Never admitted: this machine, the deployment's own networks and names, or a cloud's metadata services, link-local or inside a range. SQL connects to the checked address; a client's CA can be named. Proven by `test_connector_private_hosts.py` (38 cases, plants P1–P6, N1–N9, M1–M2), and live by `verify-full` through a TLS front (plants L1–L4). **ADR-133 Amendment 9** (ruling 2a) is written; its code is rules' L2.11, by the orchestrator's ruling.
7. **The orchestrator's independent review: no blocker; items 1–5 and 9–12 fixed**, strict option each time, shown red (R1–R12):
   - **Access:** a source author is told a refused read in fixed words, and an unbound connection answers as an unknown one (404).
   - **TLS and addresses:** the API's TLS is tested against a real HTTPS server; reserved and site-local IPv6 are inside; addresses are taken in the resolver's order.
   - **Secrets:** connection secrets are declared in `osprey.yaml` and given to the Conduit alone.
   - **Files and words:** JSON reads never follow a link and are capped while read; a failed certificate check says so.
   - **Shared files:** they left the branch, carried as diffs that apply to main.
8. **My lane-reviewer on that round: 6 must-fix items, all fixed (S1–S6).** The main fix: SQL reaches each checked address over TCP first and signs in at one only, so no second server is sent the password. Also: the API stops at any TLS failure, and the stop-at-a-refusal cases, *Refresh now*'s words, the administrator's words and the JSON read's bounded size are now tested. An earlier review round found 2 blocking and 10 must-fix items (N, M, L plants), all fixed.
9. **Live, under lease studio-b on stack a, 08:20:23Z–08:21:47Z at fbc71bc on main 7f67b1b:** 47 passed, 1 failed (main's own snapshot-revert case, failing identically at main). The three `verify-full` cases passed. No timing figure is claimed.
10. **Gates at 16d9291** (tree `e5c918dd`, `gates/16d9291.*`, explained), on main 7f67b1b:
    - **`make -k ci`:** green, the seven image scans included, except `test-file-coverage-check`. It names only the two live files whose wiring is in `L1.6_ci_makefile.diff`; with the diff applied, the gate reports no drift.
    - **`make test`:** 5 failed, 9369 passed, 6 skipped, 16 errors. 14 errors and 1 failure come from that diff (the live files are collected). The rest are this machine's or Docker Hub's, as at every gate.
11. **Left:** scheduled polling of SQL and API sources (waits on R17); *Admin › Connections*' fields, now with `ca_certificate` (admin's carry); the picker, re-screening, the read-only Lists tab and the list migration (rules' L2.11); pruning an incremental file. The orchestrator's CARRIES: a lookup that blocks the event loop; the SQL byte cap per row.
12. **Requests at merge:**
    - Apply `L1.6_action_registry.diff` (in the merge commit itself: `sources-connectors.spec.ts` imports from it), `L1.6_ci_makefile.diff` and `L1.6_every_harness.diff`.
    - Ratify the files below.
    - Mark ADR-140 Amendments 13 and 15, ADR-146 Amendment 3 and ADR-133 Amendment 9 written.
    - Guide version 1.58 is this branch's unless case-b merges first.
    - **Questions:** none. **Running:** nothing; no lease held.

## Decisions taken (each logged for the owner to overrule)

- **`connectors/**` ownership** (A) read as covering `services/ingest/connectors/**`; ratified by the orchestrator (R2).
- **A connector read lands as a CSV in the dataset's folder** (A, versus a new run path per kind): one run path, watch, watermark and confinement for all sources.
- **Secrets by name from `deployment.env`** (`OSPREY_CONNECTION_SECRET_<NAME>`; A, versus a new secret store).
- **The egress "request" is a refusal naming the operator** (A, versus a request queue): `OSPREY_CONNECTOR_EGRESS` is set only by an operator.
- **SQL: table and columns only** (A, versus an expert query): the sandboxed SELECT is L1.5's.
- **Incremental files keep earlier rows** (A): nothing is lost, and each run's watermark dedupes.
- **The UK Sanctions List gets a template too** (A): OFSI's list closed on 28 January 2026.
- **Deployment-list routes under `load_screening_lists`** (A): reconciled with ADR-146 by its Amendment 3.
- **Subscriptions under the Sources step's gate** (`add_ingest_files` and the source author role, A).
- **Own-list import reads the dataset's own files, with no SHA check** (A): a dataset's data is the user's; rule 9 binds the repository and CI.
- **The stand-in's `import_list` kept as the tests' synthetic seed;** only the CLI is retired (A).
- **Store of record: ruled (a) by the owner.** Lists already in ADR-133's store are migrated by L2.11, not dropped: version 1 of a same-named Studio list, each rule repointed by id, a clashing name refused (A, versus dropping or re-import by hand; ADR-133 Amendment 9 decision 3).
- **Private networks: ruled (a) by the owner.** A connection to a private address is written by name; a literal private address stays refused (A, versus admitting a literal inside a listed network: the schema checks a host before any list is known).
- **The deployment's own networks** are read from the container's route tables and its own names, once a minute (A, versus an operator-supplied exclusion list). Recorded limit: another product's service in the same cluster, inside a listed network, is not seen.
- **A client's CA per connection** (A, versus a deployment-wide CA bundle in `osprey.yaml`): a connection trusts its own client's CA only.
- **Connection secrets declared in `osprey.yaml`'s `connectors.secrets`** (A, versus a separate file only the Conduit reads): render must know the names to blank them for every other service, as ADR-135 does for model keys, and the chart's one Secret cannot be split per workload. An undeclared secret is never read.
- **SQL reaches each address over TCP before signing in** (A, versus moving on after a failed sign-in or a timeout): once a server may have seen the password, no second address is tried. The API moves on only while its connection or handshake has not completed, so nothing has been sent.
- **The fixed words for a source author** name *Test connection* and the audit log, so they know whom to ask; a source's own name is still refused in its own words (`source_name_refused`).

## Files outside the lane's map (ratification asked)

`services/api/connector_reads.py` (the Sources step's read service); `app.py`'s *Test connection* route (R4) and `_MonitoringSchedules`' optional field; `studio_staging.py`, `studio_verify.py`, `pipeline_run.py`, `recipe_run.py`, `run_resources.py` and `reference_list_import.py` (R3's seam); `harness/{render,apply,restore}.py` (the private list rendered; secrets and egress kept across apply and restore); `tests/harness/test_connection_secrets_kept.py`; `tests/services/api/{test_route_rights,test_run_resources,test_recipe_run_path,test_place_routes,test_admin_sections}.py` and `tests/ingest/test_reference_list_rows.py`; `shell/placesByRole.json`; `harness/cluster.py` (connection secrets blanked for every workload but the Conduit); `tools/admin_guide_options.py` (one section line), `docs/administration-guide.md` (generated Appendix A rows, version 1.58, its PDF and manifest entry) and `spec/10_ADMINISTRATION_GUIDE.md` (generated rows); `spec/05_DEPLOYMENT.md` §6.1; `keyboard/actionRegistry.ts`, `a11y/every-harness.spec.ts`, `OspreyFlow_Build/Makefile` and `.github/workflows/ci.yml` (shared; also carried as diffs). `packages/schemas/{sources,deployment,list_connector}.py` and the generated types ride with the step.

## Commits

`git log main..lane/studio-b` (53): the schemas commit first, then templates, the list service, routes, connectors, the Glass, keyboard and a11y, CI, the spec, friction, two review rounds, the seam, Amendment 15 and its review, the verify-full live cases, the guide, and the gate records.
