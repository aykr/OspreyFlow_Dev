# Platform-b · handoff, 11 November 2026, 06:40 UTC (the owner's laptop going offline)

**First, on the server from 07:08 (ADR-142 Amendment 8):** P11 part 1, on `lane/platform-b-p11` from main. That is the two engine kinds in Admin › Models: the client's OpenAI-compatible gateway, and Bedrock by IAM role with no stored key. Test against recorded fixtures. Read its BRIEF when the orchestrator writes it. Then come back to the carries below.

## lane/platform-b-carries: where it stands

Branched from main ba14a00, the upgrade fix's merge. Everything below is committed; nothing is uncommitted.

| Item | State | Commits |
| --- | --- | --- |
| Chart: `checksum/*` annotations unquoted (the merger's find, asked first) | **done**: red on the server, `| quote` on both lines in `deploy/helm/ospreyflow/templates/workloads.yaml`, 20/20 chart tests green on the server; audit found no other unquoted hash | 682d25f (test), fc16bb0 (fix) |
| 1. Move into place: atomic `write_private` (600 temp file, fsync, the old owner, rename) | **done**: red first, green | 5fb3b31 |
| 1. Move into place: restart flags kept across a crash (`state/refresh-pending.json`); a moved file keeps its owner | **done**: red first, planted | 1ed8b27 |
| 2. Staged refresh: stale stage and glob; one refresh at a time (`flock`); symlinked files through their link; values from the shell or `export` lines | **done**: red first, planted | 1ed8b27 |
| 3. The lockout's words: apply's port lookup and `ospreyflow stop` refuse in words, before Compose, naming the missing value, the backup set, and a `docker stop` by project label | **done**: red first, planted | b0bb8cb |
| Lint tidy of the touched Build tests (I001, RUF028, ISC004) | **done** | e4b24b0 |
| Red record | `plants.md`, "Carries" | the last commit |

**Still to do on this branch, after P11 part 1:**
1. **The upgrade guide's line.** CARRIES row 106 asks the upgrade guide to say that two v0.4.12 updates within one hour are refused (safe; the words lead out). That's the docs lane's guide: send it as a request, not an edit.
2. **Spec (rule 11).** Add to ADR-114 Amendment 39's text, or a new amendment if it is already written on main (it is written, ba14a00), so a new amendment under a reserved number from the orchestrator:
   - the pending-restarts record;
   - the one-refresh lock;
   - symlinks written through;
   - shell and `export` values;
   - `write_private`'s atomicity.
   The lockout's words probably belong to ADR-137, apply. Ask the orchestrator which numbers.
3. **REPORT.md** for this step (at most 20 lines), and a friction row in `process/friction/` ending "Hash: recorded at merge."
4. **Ownership.** Say in REPORT that this step touched:
   - `harness/render.py` (`write_private`), `harness/compose_env.py` (new), `harness/apply.py`;
   - `cli/ospreyflow/{run.py,main.py}`;
   - `scripts/refresh.py`, `deploy/helm/.../workloads.yaml`;
   - the tests named above.
   Ask the orchestrator to ratify the CLI and render files.
5. **"built at <hash>" goes to the merger** (uds:/tmp/cc-socks/43227.sock), with your own lane-reviewer started at the same time. Then fix both reviews' findings, rebase onto main, gate once on the server (`stack_lease.sh offline platform-b -- sh -c 'make -k test SKIP_JS=1; cd ../OspreyFlow_Core && make test-js'`, then `make -k ci`), and send ready. It lands after the v0.5.0 tag.

**Known on the server:**
- Three orphans of the stopped 0739128 run still hold slot 7's ports: vite on 5893 (pid 1013683) and 5894 (pid 1014161), and `harness.webapp` on 7919 (pid 1013813). Neither the orchestrator nor this lane may stop server processes. A harness-a11y run at slot 7 fails "already used" until the owner stops them; the orchestrator's workaround is `OSPREY_PORTS_SLOT=14` for that one target.
- The known host failures in `make test`: test_render_memory, the gpu skip, valkey 59993.

**Rules, for the session:**
- Docker never on the laptop.
- One server run per lane.
- Ruff format from `OspreyFlow_Core` (its config), never from the repository root, which reflows to 88.
- Heredocs holding `$(…)` or `${…}` are blocked by the shell safety check: write such files with the file tools.
