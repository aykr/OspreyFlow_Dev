# Draft, for `spec/06_DECISIONS.md` as ADR-114 Amendment 40 (reserved, main e7e398e; rule 11)

Written on the test server, 11 November 2026, and brought to the build after the orchestrator's
review of c5209b1 (the same day, on the Mac).

### ADR-114, Amendment 40 (11 November 2026) — The upgrade path's carries as built: one atomic writer for deployment.env, the refresh's lock, stage and pending record, every verb's lockout words; a value in the shell does not count as held (Am 39 decision 2 stands)

Status: as built by the platform-b lane (CARRIES rows 100–106), after its own lane reviewer's round
and the orchestrator's review of c5209b1. Amendment 39 is unchanged except where this settles it.
**Its decision 2 stands, as the orchestrator ruled** (11 November): a required value counts as held
only from `deployment.env`, never from the shell; CARRIES row 104's "or from the shell" is withdrawn.

1. **One writer for `deployment.env`** (`harness/atomic.py` `replace_whole`): a temporary file beside
   the real target, its mode set first, flushed, the old file's owner kept under sudo, renamed over the
   target, the folder flushed; **a symlink is followed** (the link kept, its target replaced); a
   failure leaves the old file whole and nothing beside it. **Every writer of the live file uses it**:
   `write_private`, `apply`'s move into place (which copied it with `copytree`), `store_volumes`'
   put-back, refresh's move into place (made `600`, as every other writer makes it), and since the
   orchestrator's review `register_sign_in` (every `start --build`, restore and apply), restore's
   carried values (`SUPERSET_SECRET_KEY` among them) and `update`'s rollback put-back. A scan of every
   module under `harness/`, `scripts/` and `cli/ospreyflow/` fails for any other raw write naming an
   env file or copying a folder's files by name; the fresh copies into a new stage or rollback point,
   and refresh's own edits of its private stage, are listed with their reasons. A file a container
   mounts on its own is still written in place (it must keep its inode) and holds no secret. A
   symlinked file is held, and put back after a refused stores' move, through its link.
2. **One refresh or update of a deployment at a time, for the whole of it** (`harness.update`'s
   `one_change`, shared by both): the lock (beside the deployment's resolved folder, opened
   read-only so one left by a run under sudo stops no later run, made `644` on the open file whatever
   the umask) is held by `start --build` from the files pass through the build, the stores' move,
   `up` and the restarts, and by `update` from before its backup through the files step, the pull,
   the stores' move, `up`, the restarts and any rollback. `update` hands its open lock to its
   `--files-only` child by descriptor (`OSPREYFLOW_REFRESH_LOCK_FD`), believed only when it is that
   very file and flocks. A second run is refused in words; a lock this account cannot open is said in
   words naming it and `sudo rm`; a stage that a run under another account left and this one cannot
   remove is refused in words naming it.
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
   `logs`, `status`, `uninstall`, `map`, `grading`, `models`, and the harness-delegating `backup`,
   `restore`, `update`, `demo add` and `repair-sign-in`), naming the missing values (never a value),
   whether the shell's empty value is what Compose takes, the way out (`ospreyflow apply --name
   <deployment>`, which keeps or mints every value; a backup set from before the value existed does
   not hold it) and how to stop the containers meanwhile by the project's label
   (`docker ps -q --filter label=… | xargs -r docker stop`, which runs nothing when none is up);
   `switch` stops another such deployment by its label. **Not refused there:** `doctor` (it must run
   to say what is wrong), `start --build` (it hands to refresh, which refuses such a file in its own
   words), `update --check` and `--make-bundle` (neither asks Compose), `demo list`.
6a. **The operator sees refresh's and update's refusals**: the CLI's redactor hides a line naming
   `password|secret|token`, and these name the variables Compose requires. A line in our own words
   (`refresh: …`, `ospreyflow: …`) is shown when every such word in it is a variable's name in prose
   (upper case, followed by a comma, a full stop, a closing mark, the end of the line or a joining
   word), never followed by `=`, `:`, a quote or a value; any other line naming a secret stays hidden.
   The gateway refusal says "keeps every value deployment.env holds", no longer "every secret".
7. **The chart's values-derived keys are quoted**: the `checksum/*` annotations, ConfigMap data keys
   and a file's `subPath` (a key reading as a number, bool or null broke the render or the workload).

**Tests** (`process/lanes/platform-b/plants.md`, "Carries", "after my own lane review" and "after the
orchestrator's review"): `tests/harness/test_atomic_writes.py`, `tests/harness/test_env_writers_whole.py`,
`tests/test_refresh_carries.py`, `tests/harness/test_compose_lockout.py`,
`tests/cli/test_compose_lockout.py`, `tests/cli/test_refusal_words_reach_the_operator.py`,
`tests/harness/test_update_apply.py`'s lock cases, `tests/test_refresh_before_the_gateway.py`'s
handed-lock cases, `tests/test_refresh.py`'s `--files-only` and symlinked put-back cases, and
`tests/harness/test_helm_chart.py`'s two quoting cases (point 7, platform's under P7 from the
orchestrator's ruling: dropped at the rebase wherever P7 covers the same quoting).

**Not done, recorded:** `fcntl` and `os.geteuid` are POSIX-only (`scripts/refresh.py`), as `os.fchmod`
already was in the harness; a native-Windows refresh is not supported by this. A values file whose
environment holds a key PyYAML writes bare but Helm reads as a bool (`Y`, `N`) is the render's own
question, not the chart's. Carried from the orchestrator's review: a file a service mounts on its own
is written in place in name order among the renames, not before them all (Amendment 39 decision 5's
order; none holds a secret); the CLI's and the preflight's other two env readers are not yet one; a
`.deployment.env.*.writing` left by a `SIGKILL` part way through a write is staged with the rest (in
the `700` stage, removed with it) rather than removed; `harness.compose_env.locked_out` has no
product caller of its own (it is the source the CLI's copy is held to by the parity test).
