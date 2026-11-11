# Orchestrator handoff, 11 November 2026, 08:40 UTC (the owner restarting the Mac)

The orchestrator's session was `56280fa6-f1a0-4859-9c23-63dcba42885d` (account `~/.claude-ayan`). Resume it with
`claude --resume 56280fa6-f1a0-4859-9c23-63dcba42885d`. Whether resumed or fresh, read this first, then
`process/lanes/MORNING.md` items 24–35, `spec/06_DECISIONS.md` ADR-142 Amendments 6, 7 and 8, and
`process/BUILD_PLAN_PARALLEL_LANES.md` § "Two tracks".

## Where things stand

- **v0.5.0 is published.** It is on the user repository `aykr/OspreyFlow`: main at 2be985a, tag `v0.5.0` (from
  4b8de6c). Local `main` is ahead of `origin/main` by many commits. Push to origin **once at the very end**.
- **`osprey-small` on the test server is frozen at v0.4.12** for the owner's demo on Friday 13 November. Do not
  update, reseed or restart it.
- **No lane session runs on the Mac.** Every Mac lane was paused or closed. The merger's session is closed; its
  `HANDOFF.md` is in `~/dev/osprey-wt/merger` (untracked).
- **Lane sockets from before the restart are gone.** A relaunched session gets a new `uds:/tmp/cc-socks/<pid>.sock`.
  Relaunch lanes with `bash OspreyFlow_Build/scripts/lanes_launch.sh resume <lane> [--account sol]`. case, studio,
  rules and platform are on `sol`.

## The test server's sessions (tmux on ospreyflow-test; repository ~/osprey-p7/repo.git)

| Session | Worktree / branch | State at 08:36 |
| --- | --- | --- |
| P7 (platform) | ~/osprey-p7/wt, lane/platform | **built at 1a63953d** (SERVER_LOG.md). Needs two review rounds, then merge without the owner if green (MORNING 34); then brief the waiting steps |
| case-b P12 part 1 | ~/osprey-srv/case-b, lane/case-b-p12 | **built at a5fa3c1b** (310648a1 plus the service inventory row); one review round |
| studio-b L1.9 part 1 | ~/osprey-srv/studio-b, lane/studio-b-l19 | **built at b29dba44**; an access step, two rounds; uses ADR-140 Amendment 20 (reserved) |
| platform-b | ~/osprey-srv/platform-b, lane/platform-b-p11, then lane/platform-b-carries | P11 part 1 at cec7a5e6 (a credential step, two rounds). Its carries are built to c5209b1; it needs a ruling on "a shell value counts as held" (it contradicts Am 39), amendment numbers for two as-built drafts, and ownership rulings. Session ended |
| admin | ~/osprey-srv/admin, lane/admin-p10, then lane/admin-t1p5 | **P10 part 1 built at 5b0e6e1** (record 6642291f; access, two rounds); now on T1 part 5. Still running |
| rules | ~/osprey-srv/rules (lane/rules-srv), ~/osprey-srv/rules-hyg (lane/rules-hyg) | Stopped. The update check is blocked because the driver must write outside its worktree. Studio's hyg finding is fixed and shown red then green in ~/osprey-srv/rules-hyg, **uncommitted** |

Bring the branches back with `git fetch ospreyflow-test:osprey-p7/repo.git '+refs/heads/lane/*:refs/remotes/srv/lane/*'`.
The independent reviews start from those heads (lane-reviewer agents). Don't write in a server worktree while its
session runs (rule 14).

## Found while away, to act on

1. **The workspace image scan fails:** two HIGH CVEs in `libxslt` 1.1.43-r3 in the nginx base image, fixed in r4
   (admin's gate at 5b0e6e1). It probably affects `main`'s `make -k ci` too, and v0.5.0's published workspace image.
   Rebuild on a patched base and re-scan. Then decide whether a v0.5.1 is needed (ask the owner).
2. **Rules' post-tag update check:** run it from the Mac under a lease (`stack_lease.sh`) on a fresh v0.4.12
   `osprey-upg`, following the CHANGELOG's steps 1–7. Commit the hyg fix from ~/osprey-srv/rules-hyg (or redo it on
   the Mac). Then a fresh merger re-reviews rules-hyg.

## Queue on return (ADR-142 Amendment 8)

- **Land on main** (the merger rebuilds them on today's main first): studio-b L1.10b (e97b7ef on ac8735d), admin T1
  part 4 (b3d3e0a on e97b7ef).
- **For the merger to review:** rules-b T3b (ready at d41df45), docs D2d (built 3b602a5, with nine must-fixes from
  its review), rules-hyg (an access step, two rounds).
- **Merge order:** P7, then P10 and P9 first, then P11, P12 and L1.9, then P7b. One template file per step;
  `values.yaml`, the profile's settings model and `render.py`'s profile entry are platform's.
- **After P7 merges, brief:**
  - case: P9 (cut), a fresh session on `sol`;
  - the part 2s of P10, P11, P12 and L1.9;
  - platform: P7b (ADR-148 Amendment 5, reserved);
  - docs: D2c.
- **Deferred until after the client's install:** P8, P9b, P7a.
- **Paused until the chain merges:** T3b's follow-ups, D2b's captures, rules' lists.
- **Estimates:** the whole client chain merged by about 13–14 November, D2c by 14 November. The client's environment
  is due on 20 November.

## Standing rules (unchanged)

- Push only as ruled.
- No real data.
- Never touch `osprey.yaml` or `data/`.
- `ci.yml` and the Makefile go by diff.
- Nothing on the client's GitHub or AWS.
- No `make dev-up` or airbyte.
- No desktop apps.
- No Docker on the Mac.
- Never prune on the server.
- This session cannot stop processes or change permission settings without the owner. Ask, never work around it.
