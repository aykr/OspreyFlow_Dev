# Platform lane · P7 · report (11 November 2026, the Mac; round 2 of the orchestrator's two reviews)

**Ready to merge at `0f17781bffdb968de2b6ac379a2d265da19c7ba3`** (tree `64582b90`), on main a7bb34a, the two schemas
commits at its head; the commit above it holds this report, the red record and the gates' outputs alone. Gates run once
there, through `stack_lease.sh offline platform` (no stack, no lease). Nothing of mine is running; nothing was pushed.

| Exit criterion / round-2 item | State | Proof |
| --- | --- | --- |
| `make cp-policy-check` green on the render | Met: 0 violations (31, 36 manifests), 152 passed | `gates/0f17781b.cp-policy-check.txt` |
| …red on each planted fault, each branch alone (R2 1, self-review 2) | Met: **37 plants, 37 red**, each failure's text; RED only if every listed test fails | `gates/p7_reds.0f17781b.log`, `P7_RED_RECORD.md` round 2 |
| Stores start as 10001 | Met (round 1) | `gates/p7_stores_uid_proof.2026-11-11.log` |
| Other profiles' renders unchanged (R2 2) | Met against a7bb34a: 36 artefacts byte for byte; the cluster's Helm text differs in two comments and quoted checksums, parsed identical | `gates/p7_renders_unchanged.668c8939.log` |
| Conduit without Java, default with it (R2 5) | Met: Java now the final stage's base, the upgrade before the code, no `USER root` (ratified, then removed); no-Java built and checked (reaches lifespan, not `/healthz`); default carries java 21.0.13, its three labels, uid 10001 | `gates/p7_conduit_no_java.668c8939.log`, `test_the_final_stage_upgrades_before_the_code_and_as_root` |
| ModSecurity and ResourceQuota (R2 4) | Am 1 item 12 now claims the annotation alone; the 12.5 MiB / 128 KiB raw-body limits stated expected and unmeasured; both questions added for the platform team | `spec/06_DECISIONS.md` ADR-148 Am 1 |
| Acceptance on kind | Not here: P7a (Am 1 "Left") | — |
| Friction row | Updated | `process/friction/2026-11-10-platform-p7-cloud-platform.md` |

**Gates at 0f17781b.** `make test`: 4 failed, 11069 passed. Two are `test_admin_guide` on main's guide, which goes green
with `P7_admin_guide.diff` applied (61 passed, `gates/p7_admin_guide_with_diff.668c8939.log`). One is the GPU preflight
case, failing because this server has a GPU. The fourth is `test_lanes_heartbeat::…do_not_mix_their_lines`, timing under
load: that file passed 5 runs out of 5 alone, and this branch does not touch it. `make -k ci`: only
`trivy-image-workspace` fails, 2 HIGH in libxslt 1.1.43-r3 from the nginx base. That is main's (ORCHESTRATOR_HANDOFF
"Found while away" 1), not this branch's; the api scan shows 0 (`gates/0f17781b.{test,ci}.txt`).

The `668c8939` logs were run at that commit, since rewritten as `6d57930` when the schemas commits moved back to the
head. The changes after it are the cp-policy-check `types` fix, the upload cap's unset case and comments; the reds,
the gates and the label check ran at 0f17781b itself. **Also fixed:** `upload_cap_bytes` read the Conduit's cap as a bare `int` (`0` became nginx's unlimited `0m`), now read as
`max_upload_bytes` does (red first); the cloud-platform heap function named apart; the red script's base archive
(`--base-tar`) for the server's history-less copy. **My lane-reviewer** found 5 must-fixes: the new Dockerfile unbuilt
(built), Calico's default `types` (fixed, red first), the ModSecurity claim (narrowed), the stale red record and no
round-2 gates (both done). **Carried:** the uid proof's hand-copied init SQL and image tag; a Calico
`GlobalNetworkPolicy`'s selector-only source (the render emits none); the reviewer's ownership note: the Dockerfile is
the brief's build argument, its one `USER 10001:10001` line as on main.

**Requests:** apply `P7_admin_guide.diff` and `P7_ci_makefile.diff` (both apply on a7bb34a) and remake the guide's
PDF at merge. **Friction for the orchestrator:** the server's `ospreyflow/<image>:ci` tags are shared by every lane's
`make ci`; another run retagged `ospreyflow/api:ci` between this run's scan and its inspection (`gates/0f17781b.cp-policy-check.txt`).
Main's carries stand (`create_investigation`'s dataset, seeds' `unit-1`, `_KEYCLOAK_DATABASE_SQL`'s PG16 GRANT). No
questions for the owner.
