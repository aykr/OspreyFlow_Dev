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
- At merge, mark ADR-148 Am 1's reservation row as written.
- Main's issues, reported here and not fixed: `create_investigation` sends no dataset, and the seeds default to `unit-1`. B4's seed gives 0 nodes. `render.py`'s `_KEYCLOAK_DATABASE_SQL` lacks the PG16 GRANT for Small on RDS.

## Gates

Filled in at the head below.
