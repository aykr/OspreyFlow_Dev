# Draft, for `spec/06_DECISIONS.md` once the orchestrator reserves a number (rule 11)

Written on the test server, 11 November 2026, with the orchestrator offline. Proposed heading (and,
for point 6, perhaps an ADR-137 amendment instead, as the handoff suggested):

### ADR-114, Amendment <n> (11 November 2026) — Amendment 39's carries as built: secrets replaced whole by one writer, one refresh at a time for the whole of it, the restarts owed until done, and a compose file Compose cannot read said in words by every verb

Status: as built by the platform-b lane (CARRIES rows 100–106), after its own lane reviewer's round.
Amendment 39 is unchanged except where this settles it; **its decision 2 is kept as written** (a
required value counts as held only from `deployment.env`), CARRIES row 104's "or from the shell"
being held for the orchestrator.

1. **One writer for `deployment.env`** (`harness/atomic.py` `replace_whole`): a temporary file beside
   the real target, its mode set first, flushed, the old file's owner kept under sudo, renamed over the
   target, the folder flushed; **a symlink is followed** (the link kept, its target replaced); a
   failure leaves the old file whole and nothing beside it. Used by `write_private`, `apply`'s move
   into place (which copied it with `copytree`, rewriting it in place), restore's put-back and
   refresh's move into place. A file a container mounts on its own is still written in place (it must
   keep its inode) and holds no secret.
2. **One refresh of a deployment at a time, for the whole of it**: the lock (beside the deployment,
   opened read-only so one left by a run under sudo stops no later run) is held from the files pass
   through the build, the stores' move, `up` and the restarts; a second is refused in words. A stage
   that a run under another account left and this one cannot remove is refused in words naming it.
3. **The restarts a files pass finds are owed until done** (`state/refresh-pending.json`, written
   whole): kept by `--files-only` for `update`, which clears it once its restarts are done; cleared by
   `start --build` after its own; a stores refusal puts back what an earlier, dead run still owed. At
   worst a service restarts once more than needed; never once fewer.
4. **The secrets' required values are read as Compose reads the env file**
   (`harness.preflight.ports.read_env_file`: `export`, one pair of quotes, an unquoted ` #` comment,
   which also fixes `X= # note` read as `# note`), with the command's own copy held to it by a parity
   test.
5. **`apply` on a compose file Compose cannot read** asks Docker for the deployment's published ports
   by its project's label and renders the file again (Amendment 39 decision 1's way out); it never
   refuses there.
6. **Every verb acting on such a deployment refuses before Compose is asked** (`start`, `stop`,
   `logs`, `status`, `uninstall`, `map`, `grading`, `models`), naming the missing values (never a
   value), the way out (`ospreyflow apply`, which keeps or mints every value; a backup set from before
   the value existed does not hold it) and `docker stop` by the project's label meanwhile; `switch`
   stops another such deployment by its label; `doctor` still runs.
7. **The chart's values-derived keys are quoted**: the `checksum/*` annotations, ConfigMap data keys
   and a file's `subPath` (a key reading as a number, bool or null broke the render or the workload).

**Tests** (`process/lanes/platform-b/plants.md`, "Carries" and "after my own lane review"):
`tests/harness/test_atomic_writes.py`, `tests/test_refresh_carries.py`,
`tests/harness/test_compose_lockout.py`, `tests/cli/test_compose_lockout.py`,
`tests/harness/test_helm_chart.py`'s two quoting cases, `tests/test_refresh.py`'s `--files-only` case.

**Not done, recorded:** `fcntl` and `os.geteuid` are POSIX-only (`scripts/refresh.py`), as `os.fchmod`
already was in the harness; a native-Windows refresh is not supported by this. A values file whose
environment holds a key PyYAML writes bare but Helm reads as a bool (`Y`, `N`) is the render's own
question, not the chart's.
