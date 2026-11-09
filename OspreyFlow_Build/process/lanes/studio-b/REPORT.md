# studio-b lane · report · L1.6 (phase 9: connectors, and the screening-list connector; ADR-140 Amendments 13 and 15, ADR-133 Amendment 9), 9 November 2026

1. **Phase 9's exit: met.** `visit_bookings` is registered from a synthetic NOMIS replica with an incremental watermark, and *Refresh now* reads only the new rows. A SQL source's file then loads only the new row (`test_sql_connector_live.py`). Connections name their secret and never hold it (`test_connector_schemas.py`, `test_connector_routes.py`).
2. **Each template maps its synthetic golden file: met** (7 templates; `tests/connectors/test_list_templates.py`).
3. **A rule offers only subscribed lists, never another dataset's: met at the route** (`test_list_connector.py`, `test_list_connector_routes.py`, `test_subscribed_lists_seam.py`). The rule's picker is the rules lane's (in CARRIES).
4. **Import idempotent per version: met,** proven on the real keeper too (`test_list_rows_parquet_live.py`). **Import replaces L1.4's stand-in: met** (`test_subscribed_lists_seam.py`).
5. **Keyboard (rule 13) and axe: met in the earlier session.** `sources-connectors.spec.ts` (12 ids, `L1.6_action_registry.diff`); `every-harness` covers 10 states × 3 themes. No Glass change since, so not re-run.
6. **ADR-140 Amendment 15** (the owner's ruling 7a): `connectors.private_hosts` in `osprey.yaml` admits named private hosts or networks. Never admitted: this machine, the deployment's own networks and names, or a cloud's metadata services, link-local or inside a range. SQL connects to the checked address; a client's CA can be named. Proven by `test_connector_private_hosts.py` (38 cases, plants P1–P6, N1–N9, M1–M2), and live by `verify-full` through a TLS front (plants L1–L4). **ADR-133 Amendment 9** (ruling 2a) is written; its code is rules' L2.11, by the orchestrator's ruling.
7. **Live, under lease studio-b on stack a**, 05:55:05Z–05:57:53Z at 97e5735: 47 passed, 1 failed. The failure (`test_source_refresh_snapshot_live.py`, a returning-rows revert) fails the same at main 451a648, so it is main's own. No timing figure is claimed.
8. **Lane review on the rebased branch:** 2 blocking items (metadata services inside a range; the deployment's own networks) and 10 must-fix (SQL rebinding; the read path untested; mixed and IPv6 cases; the TLS cases' red reason and teardown; stale gates, report and records; Amendment 9's order; a client's CA). All fixed, each shown red (`L1.6_RED_RECORD.md`). Minor items: 13 and 14 fixed; 15 (map_admin's weaker duplicate inside check, platform's file) and 16 (connector prose in the guide, the docs lane's) are requests below.
9. **Gates at 3a5409c** (`gates/3a5409c.*`, explained), rebased onto main 451a648: `make -k ci` green but the seven trivy image scans (Docker Hub 429, no image scanned; `trivy fs` passed). `make test`: 4 failed, 9348 passed, 6 skipped, 2 errors, each this machine's or Docker Hub's, as at every earlier gate. Tree `6c58520a`.
10. **Left:** scheduled polling of SQL and API sources (waits on R17); *Admin › Connections*' fields, now including `ca_certificate` (admin's carry); the picker, re-screening, the read-only Lists tab and the list migration (rules' L2.11); pruning an incremental file.
11. **Requests at merge:** ratify the files below; mark ADR-140 Amendments 13 and 15, ADR-146 Amendment 3 and ADR-133 Amendment 9 written. Add a CARRIES row for platform: `map_admin._is_inside` to call `schemas.sources.address_is_inside` (it misses NAT64, 6to4 and shared space). Add one for docs: prose for the operator's connector settings (`OSPREY_CONNECTOR_EGRESS`, `OSPREY_CONNECTION_SECRET_<NAME>`, `connectors.private_hosts`). **Questions:** none open. **Running:** nothing; no lease held.

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

## Files outside the lane's map (ratification asked)

`services/api/connector_reads.py` (the Sources step's read service); `app.py`'s *Test connection* route (R4) and `_MonitoringSchedules`' optional field; `studio_staging.py`, `studio_verify.py`, `pipeline_run.py`, `recipe_run.py`, `run_resources.py` and `reference_list_import.py` (R3's seam); `harness/{render,apply,restore}.py` (the private list rendered; secrets and egress kept across apply and restore); `tests/harness/test_connection_secrets_kept.py`; `tests/services/api/{test_route_rights,test_run_resources,test_recipe_run_path,test_place_routes,test_admin_sections}.py` and `tests/ingest/test_reference_list_rows.py`; `shell/placesByRole.json`; `tools/admin_guide_options.py` (one section line), `docs/administration-guide.md` (generated Appendix A rows, version 1.58, its PDF and manifest entry) and `spec/10_ADMINISTRATION_GUIDE.md` (generated rows); `spec/05_DEPLOYMENT.md` §6.1; `keyboard/actionRegistry.ts`, `a11y/every-harness.spec.ts`, `OspreyFlow_Build/Makefile` and `.github/workflows/ci.yml` (shared; also carried as diffs). `packages/schemas/{sources,deployment,list_connector}.py` and the generated types ride with the step.

## Commits

`git log main..lane/studio-b` (42): the schemas commit first, then templates, the list service, routes, connectors, the Glass, keyboard and a11y, CI, the spec, friction, two review rounds, the seam, Amendment 15 and its review, the verify-full live cases, the guide, and the gate records.
