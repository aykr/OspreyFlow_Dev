# studio-b · L1.7a part 1 · publish commits with dulwich, not git · gated at 51600c6 (base main 15d0d24, with b0a77e5)

1. **Exit → tests** (`test_recipe_repository.py`; ADR-140 Amendment 17 names one per point; 36 plants, all red, reasons checked, `l1.7a/red_plants.py`; green 51):
   - Real git reads it: `test_publish_writes_a_commit_real_git_reads` and its history and old-repository cases (fsck --strict).
   - No binary: `test_publish_never_execs_a_binary`, with every config-driven program planted. The hooks, signer and filter each fire their own plant; the rest are named as inert in dulwich.
   - Refusals: ids, links, a foreign `.git` (gitfile, link, commondir), a real writer racing `HEAD`, one 30 s deadline over both locks, first use made aside. Licence: Apache-2.0, red on the GPL-only row.
2. **Decisions taken:** a hand-built commit, no porcelain; the platform as author; old repositories opened as they are; the image test inverted, "git absent" to platform; a `.git` not the root's own refused.
3. **Gates at 51600c6** (`gates/51600c6.*`, each failure explained):
   - make test: 9,691 passed, 2 failed; vitest 2,813 passed, 1 failed. All three are host-bound.
   - make -k ci: red only for Docker.
   - Live, stack b (`l1.7a/LIVE_RECORD.md`): 74 passed, 7 failed (main's), 34 skipped. Slow seed: 2 passed, 2 failed, neither from the publish. `GitCommitError` appears 0 times.
4. **Reviews:** five lane-review rounds and the orchestrator's two, every must-fix fixed. One minor accepted: no test asserts `_initialise`'s cause.
5. **Commits:** `git log 15d0d24..51600c6` (48), then records only.
6. **Requests:** apply `L1.7a_git_leaves_image.diff` (platform) and `L1.7a_licence_register.diff`. The 7 live failures are carried to studio's L1.7.
7. **Carries into the next step:** restore or read at HEAD after a refused publish; sweep an aside only when it holds just `.git`; fix "under the lock" in Am 17 for first use; record the seed as "skipped"; widen the queued-wait test's window.
8. **Left:** part 2 (L1.8 tips) after L2.7, then L1.10, then L1.9. **Running:** nothing; no lease held.
