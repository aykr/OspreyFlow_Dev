# Platform lane · P7b · report (11 November 2026, the Mac; after the orchestrator's review; the kind run waits for P11/P12 part 2)

**Ready to merge at `f353827bcbed6b580ff2ec19cdbc7d1ef97c852b`** (tree `dfef4603`), on main ff0e07d, the three schemas
commits at its head; the commit above it holds this report, the server log and the gates' outputs alone. Every run went
through `stack_lease.sh offline platform` (no stack, no lease; `OSPREY_PORTS_SLOT=6`). Nothing running; nothing pushed.

| Exit criterion | State | Proof |
| --- | --- | --- |
| `cp-policy-check` green on both shapes | Met: development, production, poc, 0 violations | `gates/f353827b.ci.txt` |
| …red on each planted fault in the poc render | Met: 47 plants, 47 red (the check, the runbooks, the shape, the ceiling, the render folder) | `gates/f353827b.reds-renders-guide.txt` |
| Decommission leaves nothing behind, red first | Check built: Terraform-made Secrets and roles named ours, disks by account, region, namespace and claim, the tenant's kinds; the backups kept by P9's diff at merge (Am 5 point 20) | `test_cp_decommission_check.py` |
| Runbooks end to end on kind; acceptance on kind | **Not yet**: after P11/P12 part 2; until then syntax, order and rights only | Am 5 "Left" |
| Other renders and the standard shape unchanged | Met: 0 differences from ff0e07d beyond the ceiling | same |

**Gates at f353827b.** `make test`: 4 failed, 11629 passed. Each is a known cause:
- the GPU preflight case (the server has a GPU);
- `test_admin_guide`'s appendix, which `P7b_admin_guide.diff` makes green (61 passed);
- `test_render_memory`'s OpenSearch case, main's own (in CARRIES);
- `test_lanes_heartbeat`'s timing, which passed 5 of 5 alone earlier.

`make -k ci`: one failure, `harness-a11y`, two screens timing out under a load average of 15. Rerun alone it passed 34 of 34
(`gates/f353827b.harness-a11y.txt`), and this branch changes no screen.

**Reviews.** My own lane-reviewer: 9 must-fixes; the orchestrator's: 8 must-fixes and minors. All are fixed or carried
(ADR-148 Am 5, points 13-20; friction row).

**Decisions taken:**
- "A scratch volume for Ingest" is the Ingest root's own claim (agreed).
- The kept backups come through case's `P9_decommission.diff` at merge, in place of this branch's flags (agreed: P9,
  then P7b, then the diff; its 66 tests pass on these files). `backup/platform-p7b-with-kept-hooks` is kept until then.

**Carried:** the standard shape's OpenSearch domain; the Admin-added engine's gateway (P11 part 2); the seeds' ceiling
(CARRIES, studio-b); the identity step against a real Keycloak; the kind rehearsal's stand-ins for the platform's blocks.

**Requests:** apply `P7b_admin_guide.diff` at merge with docs' version row; mark Am 5 written. P9's module stays beside
`harness/cloud_platform/`, on five conditions I check at its "built". No questions for the owner.
