# Docs · brief D2c · the Cloud Platform deployment guide

Written by the orchestrator, 11 November 2026, when P7 merged (c73e4f1). Binds: `process/CLAUDE.md` rules 1–15,
`process/lanes/PROMPT_L.md`, ADR-148 and its amendments as merged, and ADR-142 Amendment 8 decision 9.

**What (BUILD_PLAN_PARALLEL_LANES.md, "D2c").** A deployment guide for the `cloud-platform` profile, true of `main` as
merged and filled as each client-chain step lands. It covers:
- the namespace and resource requests: requests and limits per component, about 27 GiB and 3.7 CPU in development,
  70 GiB and 9.7 CPU in production (P7's figures);
- the secrets each component reads, by name;
- images to ECR (`ospreyflow images push`);
- the egress list, and that `managed_nets` should be narrowed;
- Entra ID's claims (after P10);
- backups and restore (after P9);
- the volume-expansion and upgrade runbooks (P9b's, later: mark them *coming*);
- the open questions for the platform team, as ADR-148 Amendment 1 lists them: ModSecurity's body limits, the
  ResourceQuota, Calico's version, Gatekeeper's supplementalGroups, certificate coverage, node-local DNS.

**Where Laurium runs (Amendment 8 decision 9).** Once P12 settles it, record its container, image and repository. List
what the owner must correct on the page shared with the client, which shows Laurium inside the Conduit and Workers.

**Exit.**
- Every sentence traceable to merged code or a merged ADR. Nothing unbuilt described as present: mark it *coming*.
- The docs gates and `test_docs_pdf` green.
- A version row for each change, and the PDF remade.

Send "built" for each filled part. It merges in parts, without the owner, under Amendment 8 decision 7.

**Queued for the next part (orchestrator, 11 November 2026).** Write these only once their own step has merged:
- **P10 part 2 (admin), for §6a.8's Coming list:** "Reports (report sync and Superset dashboards) on the Cloud
  Platform: they signed in through Keycloak, so they are not rendered there until a later step gives them Entra ID's
  sign-in. Setting reporting.sync or reporting.superset on this profile is refused at render with words saying so."
- **P7b, carried to docs:** spec 10 §6a.5 and the admin guide's secrets table (about lines 1144–1145 and 1200)
  still describe one allow-egress and Superset, the Glass and the recogniser reading `ospreyflow-secrets` whole.
  P7b replaced both with per-workload rows and named keys.
- **P12 part 2, carried to docs:** §10.1 says nothing of Admin › Models' read-only extraction-engine row, or of how
  to change the engine (osprey.yaml, re-render, the platform team applies).
- **L1.9 part 2 (studio-b), after it merges:** "Admin guide, cloud-platform: declare S3 buckets and Athena
  workgroups under cloud_platform.connector_sources (bucket/region/folder; workgroup/region/databases/
  results_location/table_locations). Each needs its networks in egress_nets. Re-render, helm upgrade and apply
  connector_sources.tf, and Admin › Connections then accepts S3 and Athena connections within them, refusing others
  in words. Connector hosts now reach the Conduit only."
