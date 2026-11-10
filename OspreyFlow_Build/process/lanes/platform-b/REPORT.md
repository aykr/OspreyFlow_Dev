# Platform-b · T2 · tooling carries (CARRIES rows 67, 70, 76): report

P5b's owed proof merged earlier today; its report is in main's history.

1. **Per-lane Playwright ports (row 67), here and on the server.** Every config but `live/` (the demo's 5173) and `deck-capture/` serves on today's port plus 100 x `$OSPREY_PORTS_SLOT` (`apps/lanePorts.ts`; Core names no lane and no Build path). The slot comes from `scripts/lane_ports.tsv`, by exact row: `stack_lease.sh` exports it for every server run, with `OSPREY_PORTS_LANE` (not `OSPREY_LANE`); `lanes_launch.sh` would export it for a lane's session (`t2_lanes_launch.diff`, the orchestrator's file). Refused in words: an unlisted lane or sub-lane, a linked worktree with no slot, and a malformed slot. A main checkout keeps today's ports. Each suite's port is shared with its specs (`keyboard/ports.ts`), and a literal port in a spec is caught.
2. **Docker-calling tests (row 70).** Under `<lease dir>/no-local-stacks` a docker call skips at once, naming the call: at collection, in fixtures, in tests, through `env`, `sudo`, `timeout` and any shell segment. A child process's own call meets a refusing stand-in on PATH (refused, not skipped); the guard puts back what it changed.
3. **registryCoverage (row 76).** It reads a `const` declared once. A `let`, a shadowed name, a comment or a template literal is never read as asserted; an unread first argument fails in words naming the fix.
4. **Red first, each, and planted at the real call site** (`plants.md`, T2). Both reviews' findings are fixed: Core standing alone; sub- and sister lanes; detached heads and non-`lane/` branches; the registry shapes; the guard's wrapper shapes and cleanup; the specs' literals.
5. **Out of the brief's map:**
   - Ratified by the orchestrator: `tests/conftest.py`'s `pytest_plugins`, `keyboard.spec.ts`, `setup-screens.spec.ts`, `installPage.ts`, and the `stack_lease.sh` export line (now also the slot).
   - New, for ruling: `apps/lanePorts.ts`, both `keyboard/ports.ts`, `scripts/lane_ports.tsv`, `tests/test_lane_ports.py`, `sign-in.spec.ts` (a comment).
   - As a diff, not committed: `lanes_launch.sh` and its test.
6. **Gates.** `make test` and `make -k ci` offline on the server, and the keyboard and axe suites in a granted slot (the configs changed), at the rebased head; the counts go in the message.
7. **Friction:** `process/friction/2026-11-10-platform-b-t2-tooling.md`. **Route:** none added. **Questions:** none.
