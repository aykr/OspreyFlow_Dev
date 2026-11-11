# studio-b · brief L1.9 part 2, S3 and Athena on the cloud-platform profile (ADR-140 Amendment 21) · code 17c243a, rebased on main df8b48e

1. **Hosts declared at install:** `cloud_platform.connector_sources`, set beside `connector_hosts` (s3: bucket, region, folder; athena: workgroup, region, databases, results_location, table_locations).
   - Each declared host is the Conduit's own egress row on 443 and is on its allow-list. Nothing declared renders nothing.
   - Proved by `tests/harness/test_cloud_sources_render.py`.
2. **Admin refuses what was not rendered**, at save, at Test and before every read, in words naming the setting, the re-render, `helm upgrade` and the Terraform.
   - Ten wider connections are refused.
   - An unreadable declaration is refused in words.
   - An SQL or API connection to a declared host is refused.
   - Proved by `tests/services/api/test_cloud_sources_declared.py` (23 cases).
3. **IAM:** `terraform/connector_sources.tf` attaches read-only statements to P7b's namespace role. No new account is made.
   - The render refuses any action outside the read set, a write outside the results location, `*`/`?`, an undeclared bucket, folder or database, and an unconditioned listing (nine plants).
4. **Region and parse refusals:**
   - pyarrow 26.0.0 was measured against AWS's documented answers: it follows neither and raises `HTTP status 301|400`, now in typed words.
   - Athena's two parse answers get one set of words. A table location left out of the declaration is refused by the recorded Athena from the rendered grants.
   - Real S3 and Athena are not measured (CARRIES).
5. **cp-policy-check:** 0 violation(s) on all five fixtures, the new `development-sources.yaml` among them (`gates/17c243a9.ci.txt`).
   - Every other profile renders as on main; the only difference is the empty default in the embedded osprey.yaml copy (`l1.9p2/renders-byte-for-byte.txt`).
6. **Decisions taken:**
   - The orchestrator's rulings: Q1 schemas at head, the rest as diffs; Q2 no results-bucket row; Q3 table_locations are IAM-only; (a) connector_hosts reach api alone; (b) the shared IRSA role is logged, with a CARRIES row; (c) pyarrow measured.
   - Mine, confirmed by the orchestrator:
     - athena:GetWorkGroup, because Test asks it;
     - results_location required, and a folder;
     - the default catalog only;
     - nothing declared refuses everything.
7. **Plants:** 23 in `l1.9p2/red_plants.py`, each red for its stated reason at 47d9954; green is 41. The first reds are `red-1-3`, `red-2` and `red-4a`/`4b`.
8. **Review:** my lane-reviewer found 13 items (4 must-fix: GetBucketLocation under the prefix condition, no gates, no report, guide internals). All are fixed or carried.
9. **Shared diffs for merge** (`l1.9p2/`):
   - `cloud-platform-L19p2.diff`: harness/cloud_platform, profile.yaml, the fifth fixture.
   - `docs-admin-guide-L19p2.diff`: the guide tool, both guides, `test_admin_guide.py`.
10. **Gates at 17c243a9** (both diffs applied): make -k ci exit 0; make test 12,225 passed with 5 failed: main's two known, and three lane-tool tests that pass alone on the server (`gates/17c243a9.explained.md`). Nothing of mine is running.
11. **Carries:** a fourth account for the Conduit (platform team). The live checks on the client's platform: Athena's parse answer, real region refusals, KMS, VPC endpoints.
