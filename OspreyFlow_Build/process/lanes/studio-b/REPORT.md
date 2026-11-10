# studio-b · L1.7a part 1 · publish commits with dulwich, not git · gated at 51600c6 (base main 15d0d24, with b0a77e5)

1. **Exit → tests** (`tests/services/api/test_recipe_repository.py`; ADR-140 Amendment 17 names one per point; 36 plants, all red, reasons checked: `l1.7a/red_plants.py`; green 51):
   - Real git reads it: `test_publish_writes_a_commit_real_git_reads`, `…keeps_the_first_in_the_history`, `…on_top_of_a_repository_real_git_made` (fsck --strict).
   - No binary: `test_publish_never_execs_a_binary`, with every config-driven program planted. The hooks, the signer and the clean filter each fire their own plant; the rest are inert in dulwich 1.2.21, as named.
   - Refusals:
     - ids, links and a foreign `.git` (a gitfile, a link, a `commondir`);
     - a real writer racing `HEAD`;
     - one 30 s deadline over both locks;
     - first use made aside, joining a rival's.
   - Licence: dulwich under Apache-2.0, red on the GPL-only row.
2. **Decisions taken:** the commit is built by hand, with no porcelain; the platform's identity is the author; old repositories are opened as they are; the image test is inverted, with "git absent" left to platform; a `.git` that is not the root's own is refused.
3. **Gates at 51600c6** (`gates/51600c6.*`, every failure explained):
   - make test: 9,691 passed, 2 failed; vitest 2,813 passed, 1 failed. All three fail on the host (valkey's port, the GPU preflight, MatrixView.budget).
   - make -k ci: red only for Docker (8 image scans, opentofu, chart).
4. **Live, stack b** (`l1.7a/LIVE_RECORD.md`):
   - The live set: 74 passed, 7 failed, 34 skipped. The same 7 fail on main.
   - The slow seed: 2 passed and 2 failed, neither from the publish. `GitCommitError` appears 0 times.
5. **Reviews:** five lane-review rounds and the orchestrator's two, with every must-fix fixed. One round-5 minor is accepted: no test asserts `_initialise`'s cause.
6. **Commits:** `git log 15d0d24..51600c6` (48), plus this records commit.
7. **Requests:** apply `L1.7a_git_leaves_image.diff` (platform) and `L1.7a_licence_register.diff`; the 7 live failures go to studio's L1.7 (carried).
8. **Carries into the next step** (from the orchestrator's final review):
   - restore or read at HEAD after a refused publish;
   - the aside sweep only for a bare `.git`;
   - Am 17's "under the lock" at first use;
   - the seed recorded as "skipped";
   - the queued-wait test's window.
9. **Left:** part 2 (L1.8 tips) after L2.7, then L1.10, then L1.9. **Running:** nothing; no lease held.
