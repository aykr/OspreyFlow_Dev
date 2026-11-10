# studio-b · L1.7a part 1 · publish commits with dulwich, not git (base main 15d0d24; L1.8's report is at a8e7f9a)

1. **Exit → tests** (`tests/services/api/test_recipe_repository.py`; 8 plants all red, the code restored, `l1.7a/red_plants.py`):
   - Real git reads it: `test_publish_writes_a_commit_real_git_reads` (fsck --strict, clean status). Red with the write removed.
   - History kept: `test_a_second_publish_keeps_the_first_in_the_history`, `…on_top_of_a_repository_real_git_made`.
   - No binary: `test_publish_never_execs_a_binary` (process APIs replaced, PATH emptied, a hook planted) and `test_the_module_names_no_process_api`. Red with a planted `create_subprocess_exec("git", …)`. The image test says nothing execs git.
   - Licence: dulwich 1.2.21 under Apache-2.0; its licence test is red on the GPL-only row. Also covered: locking, the index before HEAD, a refused compare-and-swap, nested and detached repositories, an error with no path.
2. **Decisions taken:**
   - The commit is built by hand; porcelain reads config, and with it hooks and signers.
   - The platform identity is always the author.
   - Old git-made repositories are opened as they are.
   - The image test is inverted; "git absent" goes to platform.
3. **Gates:**
   - make test at c2e3da8: 9,664 passed, 2 failed; vitest 2,813 passed, 1 failed. Each failure is the server's or main's (`gates/c2e3da8.test.*`).
   - make -k ci at f2b4187: red only for Docker (8 image scans, opentofu, chart) (`gates/f2b4187.ci.*`).
4. **Live on stack d** (`l1.7a/LIVE_RECORD.md`): 74 passed, 7 failed, 34 skipped. The same 7 fail on main 15d0d24 without this branch.
5. **Lane-reviewer:** 10 findings, all fixed (ff69107, 80c86b4, 7c713f6, c30a685, c2e3da8).
6. **Commits:** a941dc3 f021d25 61f338e 3f4547c 4c8c546 ff69107 80c86b4 4f732e5 7c713f6 c30a685 c2e3da8 f2b4187, and the gate and report commit after f2b4187 (process only).
7. **Requests:**
   - Apply `L1.7a_git_leaves_image.diff` (platform's) and `L1.7a_licence_register.diff` (spec 00 §7).
   - The AWAITING_OWNER dulwich note.
   - A carry for the 7 live failures on main.
8. **Left:** part 2 (L1.8 tips patches) waits for L2.7; then L1.10 and L1.9. **Running:** nothing; no lease.
