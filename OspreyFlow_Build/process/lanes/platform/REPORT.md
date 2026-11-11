# Platform lane · P7b · report (11 November 2026, the Mac; built, the kind run left for after P11 and P12 part 2)

**Ready to merge at `21e7891fafcf8cf7ff84008b913ac925d93e5be9`** (tree `19bd638f`), rebased on main 2733de4 (P11 part 1) at the orchestrator's word,
the two schemas commits at its head; the commit above it holds this report, the server log and the gates' outputs
alone. The rebase touched `spec/06_DECISIONS.md` alone (P11's ADR-135 Amendment 7 and this step's ADR-148 Amendment 5,
both kept); the patch is otherwise line for line 8b46eda0's. Re-run at the head: `tests/cp_policy_check` 140 passed,
`cp-policy-check` 0 violations on all three fixtures, 34 plants 34 red, the renders 0 differences from 2733de4
(`gates/21e7891f.rebase-rerun.txt`, `gates/p7b_reds.21e7891f.log`, `gates/p7_renders_unchanged.21e7891f.log`). The
full `make test` and `make -k ci` below are 8b46eda0's. Nothing of mine is running; nothing pushed.

| Exit criterion | State | Proof |
| --- | --- | --- |
| `cp-policy-check` green on both shapes | Met: development, production and poc, 0 violations | `gates/8b46eda0.ci.txt` (`poc.yaml: 25 manifests, 0 violation(s)`) |
| …red on each planted fault in the poc render | Met: every planted fault test runs on development and poc; 34 plants, 34 red | `test_cp_policy_check.py`, `gates/p7b_reds.957b8805.log` |
| Decommission leaves nothing behind, red first | Check built, each branch red alone (Terraform the render declares, disks by tag, the tenant's kinds, buckets) | `test_cp_decommission_check.py` |
| Install and decommission runbooks run end to end on kind | **Not yet**: with the acceptance run, after P11/P12 part 2 (Am 5 "Left"); proven by tests until then | `test_cloud_platform_poc.py` (parse, rights, order, platform blocks) |
| Acceptance scenarios on kind (poc) | **Not yet**, same reason; packs at or below OFFICIAL-SENSITIVE only | Am 5 point 8 |
| Other renders and the standard shape unchanged | Met: 0 differences beyond the two forgiven (ceiling; `shape: standard` in the config's copy) | `gates/p7_renders_unchanged.957b8805.log` (main moved since by docs alone) |

**Gates at 8b46eda0.** `make test`: 2 failed, 11350 passed: the GPU preflight case (the server has a GPU), and
`test_admin_guide`'s appendix on main's guide, which is green with `P7b_admin_guide.diff` applied (61 passed, checked on
fc32dce). `make -k ci`: one failure, `harness-a11y`'s install page timing out once (33 of 34). Rerun alone at the same head
it passed 34 of 34 (`gates/8b46eda0.harness-a11y.txt`); this branch changes no screen. The workspace scan is clean now.

**Reviews.** Own lane-reviewer: 9 must-fixes and 6 minors, every one fixed or carried (Am 5; friction row). Orchestrator:
five findings folded in (ceiling, refusal words, LimitRange, first render's folder, digest carried forward), two ruled
(no poc OpenSearch; the gateway is P11 part 2's). **Carried:** the standard shape's OpenSearch domain; the gateway for an
engine added in Admin; `scripts/seed_internal.py`'s ceiling from `deployment.env` (the seeds' owner).

**Requests:** ratify the two `packages/schemas` commits and spec/10's appendix with them; mark ADR-148 Am 5's reservation
written; apply `P7b_admin_guide.diff` at merge (docs adds its version row). **Decision taken:** "a scratch volume for
Ingest" as the Ingest root's own claim (the orchestrator agreed). No questions for the owner.
