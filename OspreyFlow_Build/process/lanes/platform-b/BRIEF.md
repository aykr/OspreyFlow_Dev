# Platform-b lane · brief P5b · backups in a folder the administrator names at setup

Written by the orchestrator, 9 November 2026 (the owner: "platform-b on P5b"), for a **fresh platform-b session on
the default account** (`ayan`). A sister lane of platform (ADR-142 Amendment 4), running beside platform's P5.
Read `spec/06_DECISIONS.md` **ADR-114 Amendment 37** first: it is this step, and its tests are named there. Opus,
medium. Size S.

**The lane, the stacks, the merge rule.** Your files are platform-b's row in `process/BUILD_PLAN_PARALLEL_LANES.md`:
`harness/{backup,restore}.py`, `cli/ospreyflow/{answers,doctor}.py` and the backup and restore dispatch in
`cli/ospreyflow/main.py`, and their tests. Platform's P5 is building beside you, in `cli/ospreyflow/maps.py`,
`harness/geospatial.py` and the map routes: never edit those. The administration guide's §13 is the docs lane's:
write its new text as a carry in your report, not in `docs/**`. Test stacks are on the server only (b to g);
Docker and stack a are off on this Mac, so never start Docker. Ask the orchestrator before taking a stack, and
before `make -k ci` or Playwright here. `make test` runs on the server: `stack_lease.sh offline platform-b -- sh -c
'make -k test SKIP_JS=1; cd ../OspreyFlow_Core && make test-js'`. Never call remote or offline while one of your
runs is alive. Prompt L's rules: never stop on a question, except that loosening access, real data, or contradicting
an accepted ADR stops the piece. Your own lane-reviewer, then the gates at a commit rebased onto main, saved under
`process/lanes/platform-b/gates/`. Report to the orchestrator **by message**.

**Binds.** `process/CLAUDE.md` rules 1–15 (2, 9, 12 and 15 above all; rule 9: a backup holds a deployment's data and
any real-data exception); ADR-114 Amendments 33 and 37; ADR-138 (a deployment's sets never mixed with another's).

**Build** (Amendment 37's decisions 1–6): `folders.backups` read for every profile and asked at install, defaulting
to `~/OspreyFlow/backups`; `server.backups` read as the same setting, both given and differing refused; no backup
ever written inside the checkout (`DEFAULT_BACKUP_ROOT` removed, an `--out-root` inside the checkout refused); a
deployment's sets in `<folder>/<deployment name>/`, restore looking there first and still listing a set in the old
places with the move command; `doctor` naming sets left in the checkout or an old place (size, and the one `mv`),
never moving or deleting one; `doctor` warning about a backups folder a sync client copies (`~/Library/CloudStorage`,
`~/Library/Mobile Documents`, `~/Documents`, `~/Desktop`, OneDrive), a warning, not a refusal.

**Tests first, each red by a plant at its real call site** (rule 15): the ones Amendment 37's table names, at the
paths it gives. Rule 15's second worked example applies: a fake filesystem or runner must refuse what the real
one refuses.

**Exit.** Amendment 37's table green; `make ci` and `make test` green offline (the server); a friction fragment
(one row); the §13 text as a carry. Report in Prompt L's format, then stop.
