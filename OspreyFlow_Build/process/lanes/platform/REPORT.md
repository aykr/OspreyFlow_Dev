# Platform lane · P7 · report (11 November 2026, test server; the `cloud-platform` profile, ADR-148)

P7 is built to ADR-142 Amendment 8's bar. That bar is the render, `make cp-policy-check` (green, and red on each
planted fault) and the ordinary gates. The acceptance run on kind is **P7a**, after P9, and was not run. The branch
is rebased onto main 9bcadc6, with the schemas commit at the head. `SERVER_LOG.md` has the session; the built hash
is recorded there. Nothing of mine is running, and the kind cluster is down (0 `osprey-p7-*` containers).

| Exit criterion (BRIEF.md, as Amendment 8 cut it) | State | Proof |
| --- | --- | --- |
| `make cp-policy-check` green on the render | Met at the head | 0 violations (development 32 manifests, production 37), and the check's, the Terraform's and the render's tests all pass (`P7_RED_RECORD.md`, last section) |
| …red on each planted fault, other-uid included | Met | `P7_RED_RECORD.md`: every branch red on its own fault; on the server, the other-uid rule, the group rules, Jobs and CronJobs, and the six newer render tests |
| ArcadeDB, ClickHouse, Keeper start as 10001 | Met (10 Nov) | `gates/p7_stores_uid_proof.2026-11-10.log`, `gates/p7_kind_check.677d473.log` |
| `local-lite`, `small`, `cluster` renders unchanged but the UIDs | Met (10 Nov) | `gates/p7_renders_unchanged.helm.log`: 0 differences; the settings are refused at every other profile, each red |
| `make test`, `make -k ci` at the head | See *Gates* | `gates/<sha>.test.txt`, `gates/<sha>.ci.txt` |
| Acceptance scenarios on kind | **P7a**, not this step | `HANDOFF.md` items 2–4 carry to P7a |
| Friction row | Written | `process/friction/2026-11-10-platform-p7-cloud-platform.md` |

**Lane-reviewer, 11 November, on the rebased branch.** It raised nine points. Fixed:
- 1: `PROFILE_NAMES` lacked `cloud-platform`. main's test `test_the_profile_names_refused_are_the_schemas_profiles` went red in `make test`; the fix rides in the schemas commit.
- 2: Jobs and CronJobs had no red; each now has one.
- 3: §3c claimed a kind proof; it no longer does.
- 4: this report was stale; rewritten.
- 5: Keycloak's group 0 is now recorded in ADR-148 Amendment 1 item 4 and gated by the new group rules.
- 8, in part: the settings test now covers every profile, each with a red.

Not changed:
- 6, ownership: the chart templates beyond `ingress.yaml`, `cli/ospreyflow/main.py` (a rebase conflict, both verbs kept) and `cli/ospreyflow/deployments.py` (one name) are outside platform's map. These are requests below.
- 7: the brief's `stack_lease.sh offline` predates the server prompt, which says to run directly here.
- 8, the rest:
  - The no-Java image is never built in a test; its `included` label says `omitted`.
  - The check templates every fixture into `ospreyflow-dev`, which no rule reads.
  - The first red table was taken before the rebase. The check's tests pass at the head.
- 9: the duplicate Dockerfile-USER parser. Left as it is.

**Decisions taken** (for the owner to overrule): 1–7 as on 10 November (the shared claim until P8; plain-resource
Terraform; egress by networks; `--group-add`; no OpenSearch address; Keycloak group 0 until P10, now in the ADR and
gated; Java by build argument). 8: `PROFILE_NAMES` carried in the schemas commit, since a separate commit below it
would fail its own test.

**Requests to the orchestrator:**
- Accept the chart templates beyond `ingress.yaml`, plus `cli/ospreyflow/{main,deployments}.py`.
- Apply `P7_ci_makefile.diff`, which is regenerated on 9bcadc6.
- Run `make docs-pdf` on the laptop at merge, for the administration guide's 1.71. The edits under `docs/` and
  `spec/10` are needed by main's admin-guide tests; I ask you to accept them as platform's.
- At merge, mark ADR-148 Am 1's reservation row as written.
- Main's issues, reported here and not fixed: `create_investigation` sends no dataset, and the seeds default to `unit-1`. B4's seed gives 0 nodes. `render.py`'s `_KEYCLOAK_DATABASE_SQL` lacks the PG16 GRANT for Small on RDS.

## Gates (test server, offline ports 59991–59994, no lease, no stack; at 3b83c218 on main 9bcadc6)

- **`make test`** (`gates/3b83c218.test.txt`): 3 failed, 10939 passed, 13 skipped. No failure is this branch's code:
  - `test_webapp_preflight::test_gpu_is_skipped_on_this_platform_never_shown_as_a_pass`: this server has a
    working `nvidia-smi`, so the check passes, as it should on a GPU host. main's test assumes no GPU.
  - `test_valkey_config::test_the_deployments_own_valkey_is_reached_plainly`: main's test never clears
    `VALKEY_PORT`, and the prescribed offline port is 59993.
  - `test_docs_pdf::test_the_guides_and_their_pdfs_are_in_step`: this branch's guide edit (the appendix and
    `images push`, which main's admin-guide tests require). The guide's version 1.71 was added after the run
    (52400f6). **The PDF needs `make docs-pdf` on the laptop**: this server's Chromium prints the "fi" ligature,
    and `tools.docs_pdf` then cannot find its "List of figures" page.
- **`make -k ci`** (`gates/3b83c218.ci.txt`): one failure, `trivy-image-workspace` (with its parent rollup
  `core-check`). The workspace image, unchanged by this branch, has two HIGH CVEs, both fixed upstream in
  `libxslt` 1.1.43-r4; the base layer came from the build cache, which was stale. Every other gate passed:
  lint, types, the other image scans, licence, a11y, chart, OpenTofu, schemas, the publication and
  citation checks and lanes-check.
- **`make cp-policy-check`** (the diff's target, in the working tree only; not in `ci` until the owner applies
  it): 0 violations; its tests and the render's, 98 passed.
- **Commits after 3b83c218**: the guide's version row, these records, and the schemas commit moved back to the
  head. Its tree differs from 3b83c218's only in `docs/administration-guide.md` and `process/`.
