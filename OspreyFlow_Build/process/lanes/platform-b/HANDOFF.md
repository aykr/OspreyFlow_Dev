# Platform-b · handoff, 11 November 2026, 06:40 UTC (the owner's laptop going offline)

**Step:** today's platform-b carries, on `lane/platform-b-carries` (from main ba14a00). All code is built (complete at e4b24b0); the step-end work is left. **Last commit:** the one adding this file.

**First, on the server from 07:08 (ADR-142 Amendment 8):** P11 part 1 on `lane/platform-b-p11` from main: Admin › Models' two engine kinds (the client's OpenAI-compatible gateway; Bedrock by IAM role, no stored key), tested against recorded fixtures. Then come back here.

**Done, each red first** (`plants.md`, "Carries"):
- **Chart:** the `checksum/*` annotations quoted in `workloads.yaml`; red on the server, then 20/20 chart tests green; no other unquoted hash (682d25f test, fc16bb0 fix).
- **Atomic `write_private`:** a 600 temp file, fsync, the old owner, then a rename (5fb3b31).
- **Staged refresh** (1ed8b27): restart flags kept in `state/refresh-pending.json` across a crash; a moved file keeps its owner; a stale stage never matched as a deployment; one refresh of a deployment at a time (`flock`); symlinked files written through their link; shell and `export` values count as held.
- **The lockout's words** (b0bb8cb): apply's port lookup and `ospreyflow stop` refuse before Compose, naming the missing value, the backup set and a `docker stop` by label; `harness/compose_env.py`, with a CLI copy held to it by a parity test.
- **Lint tidy** of the touched Build tests (e4b24b0).

**Next, after P11 part 1:**
1. **Spec, rule 11:** ask the orchestrator for amendment numbers. Am 39 is written, so a new ADR-114 amendment for the refresh edges and `write_private`, and probably ADR-137 for the lockout's words.
2. **Upgrade guide:** "two v0.4.12 updates within one hour are refused" (CARRIES row 106) is the docs lane's; send it as a request.
3. **REPORT.md** (at most 20 lines) and a friction row ending "Hash: recorded at merge."
4. **Ownership for ruling:** `harness/{render,compose_env,apply}.py`, `cli/ospreyflow/{run,main}.py`, `scripts/refresh.py`, the chart template, the tests.
5. **Then:** "built at <hash>" to the merger (uds:/tmp/cc-socks/43227.sock) with your own lane-reviewer at once; fix both reviews; rebase; gate once on the server; ready. It lands after the v0.5.0 tag.

**Running:** nothing; no lease, no server run alive. **Open questions:** none. **Don't redo:** the chart fix or any carry above (132 tests green locally).

**Server notes:**
- Orphans of the stopped 0739128 run hold slot 7's 5893, 5894 and 7919 (pids 1013683, 1014161, 1013813). harness-a11y at slot 7 fails "already used" until the owner stops them; the workaround is `OSPREY_PORTS_SLOT=14` for that target.
- Run ruff format from `OspreyFlow_Core`, never the repository root.
- Write a heredoc holding `$(…)` or `${…}` with the file tools: the shell safety check blocks it.
