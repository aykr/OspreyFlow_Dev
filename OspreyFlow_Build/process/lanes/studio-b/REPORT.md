# studio-b · L1.7a part 1 · publish commits with dulwich, and git leaves the image · gated at 22ff1e3 (main ec28c67)

1. **Exit → tests** (`test_recipe_repository.py`; ADR-140 Amendment 17 names one per point; 36 plants, all red, reasons checked, `l1.7a/red_plants.py`; green 52):
   - Real git reads it: `test_publish_writes_a_commit_real_git_reads` and its history and old-repository cases (fsck --strict).
   - No binary: `test_publish_never_execs_a_binary`, with every config-driven program planted. The hooks, signer and filter each fire their own plant; the rest are named as inert in dulwich.
   - Refusals: ids, links, a foreign `.git`, a real writer racing `HEAD`, one 30 s deadline over both locks, first use made aside.
   - git out of the image (ratified): no git in `services/api/Dockerfile`, and `AWAITING_OWNER` empty. `test_runtime_licences.py` passes with git absent, and is red with git planted back, installed or declared (`l1.7a/red-image-before-fix.txt`).
2. **Decisions taken:** a hand-built commit, no porcelain; the platform as author; old repositories opened as they are; a `.git` not the root's own refused; ADR-147 Amendment 2 left as accepted, with Am 17 saying its carry is done.
3. **Gates at 22ff1e3** (`gates/22ff1e3.*`, each failure explained):
   - make test: 10,305 passed, 2 failed; vitest 2,913 passed, 1 failed, all host-bound.
   - make -k ci: red only for Docker; licence-check has 0 runtimes not yet passed.
   - Live at 51600c6, standing (`l1.7a/LIVE_RECORD.md`): 74 passed, 7 failed (main's); seed 2 passed, 2 failed, neither the publish's.
4. **Reviews:** five lane-review rounds and the orchestrator's two, every must-fix fixed; one minor accepted (no test asserts `_initialise`'s cause).
5. **Commits:** `git log ec28c67..22ff1e3`, then records only. The register entry and git's removal are commits, not diffs.
6. **Carries into the next step:** restore or read at HEAD after a refused publish; sweep an aside only when it holds just `.git`; Am 17's "under the lock" at first use; the seed recorded as "skipped"; a wider queued-wait window; the seed baseline on main.
7. **Left:** part 2 (L1.8 tips) after L2.7, then L1.10, then L1.9. **Running:** nothing; no lease held.
