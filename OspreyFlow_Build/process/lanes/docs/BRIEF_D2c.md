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
