# v0.5.0 → v0.5.1 upgrade rehearsal (platform-b, 14 November 2026, 00:48–01:30 UTC)

The orchestrator's last gate before publishing v0.5.1: the update rehearsed on the test server
(`ospreyflow-test`) as a throwaway named deployment, `osprey-upg`. osprey-small was never touched: this
session refused a read-only compose call on it, and that refusal was not worked around. No lane stack
and no lease were used.

- **Root:** `/root/osprey-runs/platform-b-upg`, with its own HOME.
- **Driver:** `upg_run.sh`, the rules lane's `gates/upg_run.sh` adapted. Its guards are kept:
  - the run root's `upg_guard.sh` (on the server, beside the run): compose only as `-p osprey-upg` on the run's own file; volume removal of
    `osprey-upg_*` alone; no prune.
  - the run root's `upg_images.py` with P5b's `OwnImages`, for the image tags.
  - Its teardown refusals.
- **Sequences:** `run2.sh` (resume with `run2.sh <phase>`).
- **Data:** synthetic only (fixture-corp, operation-ledger). Secrets are compared by per-key hashes,
  and a scan of every log for secrets found none.

## What is real and what is the stand-in

The candidate (9197ea6, then 7d76022 on `release/v0.5.1`) is not a signed release, so
`ospreyflow update` cannot target it.

**Real:**
- v0.5.0 itself, installed from the user repository's signed tag.
- `sh install.sh` as a user runs it.
- Each of the CHANGELOG's commands, exactly as written, in the checkout's folder.
- v0.5.0's own update code for its backup and rollback point (`harness.update.real_host().backup`,
  `_keep_rollback_point`).
- Its files step, exactly as it runs it: the old `.venv`'s Python, `-m scripts.refresh --files-only`,
  with the `PYTHONPATH` its command sets (`cli/ospreyflow/main.py:153`) and `OSPREYFLOW_DEPLOYMENT_DIR`.

**Stand-in:**
- The checkout moved to `make publish-user-repo COMMIT=7d76022`'s export, as `git checkout <tag>` would
  move it.
- `uv sync --inexact`, then `ospreyflow stop` and `harness.apply --build`, in place of pin, pull and start.

**Not exercised:** `find_release`, signature checks, `pin_images`, pull, `verify_running`, and rollback.
The orchestrator plans a second run against the signed v0.5.1 once it is published.

## Run 1 (`run1-logs/`, candidate 9197ea6): a missing CHANGELOG step, which blocked the publish

v0.5.0's `install.sh` installs the command with `uv tool install --editable ./cli`, whose only dependency
is PyYAML. After that, `ospreyflow --help` fails with **ModuleNotFoundError: No module named 'httpx'**
(`01-install-v0.5.0.log`). So on every v0.5.0 deployment the command is broken, and with it
`ospreyflow update`. 9197ea6's CHANGELOG did not say how to update without the command.

The orchestrator's candidates were proven on the held install:
- **(c)** `uv tool install --force --editable --with httpx <checkout>/cli` (03): `--help` exits 0;
  httpx was the only module missing. `ospreyflow backup` (05) and `ospreyflow update --check` (05b)
  both start.
- **(a)** `cd cli && ../.venv/bin/python -m ospreyflow --help`, with no `PYTHONPATH` (04): exits 0.

The CHANGELOG was fixed on `release/v0.5.1` at 7d76022.

## Run 2 (`run2-logs/`, candidate 7d76022): the whole update by 7d76022's words, from a fresh v0.5.0

| Phase | What ran | Result |
| --- | --- | --- |
| 01–02 | v0.5.0: `install.sh`, then the install through the checkout's Python | installed; the command fails at `--help`, as the CHANGELOG now says |
| 03 | the baseline | 135 counts (Postgres tables and graph types); max_connections **100**; 16 running, 12 healthy |
| 04 | `uv tool install --force --editable --with httpx ./cli`, then `ospreyflow --help` | exit 0, exit 0 |
| 05 | "Back up first": `ospreyflow backup --name osprey-upg` | exit 0 |
| 06 | v0.5.0's update: its backup, rollback point, the move, its files step | exit 0; compose.yaml, deployment.env, glass.json, litellm.yaml and versions.lock changed |
| 06b | Postgres after the files step | compose.yaml **`postgres -c max_connections=660`**; the server still 100 |
| 07–09 | stand-in: sync, stop, `apply --build` | exit 0 |
| 10a | health | 16 running, 12 healthy (the same as before); version dev-5647e86 |
| 10b | Postgres | **`SHOW max_connections` = 660** |
| 10c | data | all 135 counts the same; one new empty table (`screening_list_markings`) |
| 10d | the keys | 80 of v0.5.0's secrets byte for byte the same; the only change is `OSPREY_RELEASE_VERSION` |
| 10e | the gateway | its master key equals the Conduit's key; the gateway answered 200 |
| 11 | "After the update": `uv tool install --force --editable ./cli` | exit 0; `uv tool list --show-with` shows **no httpx extra**; `--help` and `status` exit 0 |
| 12 | teardown | REFUSED (exit 2) on five anonymous volumes; image tags put back (12b, exit 0) |
| 13–15 | the five removed on the orchestrator's ruling, then teardown again | each checked and removed (13, 14); **teardown exit 0** (15); the run's folder removed |

Two notes on the 660:
- **It is the update's own files step that renders it** (`scripts/refresh.py`,
  `postgres_connections_up_to_date`), not `ospreyflow apply` as the CHANGELOG's bullet says. The
  outcome is the same, and Postgres restarts once at the update's start.
- **Lite gets 660 too**, since `POSTGRES_MAX_CONNECTIONS` is the same for every profile. The
  CHANGELOG says "(660 on Small)", which is true but not the whole of it.

### The run's own slips, corrected and re-run

**Run 2a (`run2a-logs/`):**
- v0.5.0's install failed. `keycloak-db` ran while Postgres was still in its first-start init (the
  image's temporary server) and got "Connection refused". Run 1's identical install passed, on a host
  at load ~50. This is a start-up race in v0.5.0's install, not part of the update path, and is
  reported but not chased here.
- The sequence carried on past that failure, and my files step lacked the command's `PYTHONPATH`.
- Both are fixed: the sequence now stops at the first failure, and the files step has the
  `PYTHONPATH`. 2a was torn down (exit 0).

**Run 2 stopped twice on lines that were expected:**
- 06's folder diff (the files step must change the folder);
- 10d's one changed key (the version).

Each was read, recorded in `progress.txt`, and resumed from the next phase. Neither phase was repeated.

### Teardown: five anonymous volumes, left for a person's call

`docker volume ls` shows five anonymous volumes no container mounts, all created at 01:11:31–32, inside
this run's v0.5.0 deploy (01:10:21–01:15:54):
- `645ae85b47f5…` holds ArcadeDB logs from this run's two starts (01:11:37 and 01:24:28, the build's
  restart);
- `f9f0ad62ab6a…` holds an `ospreyflow` database folder;
- `5a407b0dc985…`, `d7055dec8e97…` and `e18e0de7ed5f…` are empty.

They look like osprey-upg's ArcadeDB image volumes, kept across the recreate and missed by `down -v`.

**Removed on the orchestrator's ruling (14 November).** Before removal, each volume was checked against
the ruling's conditions, and the `docker volume inspect` output is recorded in
`run2-logs/13-volumes-inspect.txt`. Each one:
- matched exactly one ID;
- had no container (`docker ps -a --filter volume=<id>` empty);
- had no compose project label, so nothing of osprey-small's;
- was created inside the run's window.

All five passed and were removed by full ID (`14-volumes-removed.txt`, exit 0). The teardown, run
again, ends with **exit 0** (`15-teardown-final.txt`): containers 0, volumes 0, the run's image tags
put back. One other lane's tag changed meanwhile (`osprey-test-workspace:proxy`); it is listed and was
not touched. The run's folder `/root/osprey-runs/platform-b-upg` was then removed. The `.meta` folder
beside it keeps the driver and the logs for the signed-update run.

The v0.5.0 install race is recorded in `process/lanes/CARRIES.md` (the orchestrator's ruling 4). The
orchestrator took both CHANGELOG wording notes at 477a500 on `release/v0.5.1`.

## Run 3, the real signed update and its rollback (14 November 2026, 06:35–06:58 UTC)

v0.5.1 was released on the user repository (tag v0.5.1, release workflow 43565800393). Nothing here is a stand-in:
v0.5.0 is installed from its signed release, and `ospreyflow update` moves it to the signed v0.5.1 itself.

### The update (`run3-logs/`, `run3.sh`)

| Phase | What ran | Result |
| --- | --- | --- |
| 01–02 | v0.5.0, `install.sh`, the install | installed: 136 lines of counts, 2 cases, 71 Person vertices; max_connections 100 |
| 04 | the CHANGELOG's repair: `uv tool install --force --editable --with httpx ./cli` | `--help` exit 0 |
| 05 | "Back up first": `ospreyflow backup` | exit 0 |
| 06a | the faulted update, **first attempt**: see below | **not a rollback test**, though it passed |
| 06e | **`ospreyflow update --name osprey-upg --to v0.5.1 --yes`** | **"Updated to v0.5.1."**: find_release, the cosign signatures, pin_images, the GHCR pull, the start and verify_running, all real |
| 07a–e | the end state | 16 running, 12 healthy, v0.5.1; max_connections **660** (server and compose); all 135 counts the same, plus the empty `screening_list_markings`; the 80 secrets held at v0.5.0 byte for byte the same, only `OSPREY_RELEASE_VERSION` changed; the gateway accepts the Conduit's key (200) |
| 08 | "After the update": `uv tool install --force --editable ./cli` | no httpx extra; `--help` and `status` exit 0 |
| 09 | teardown | exit 0, nothing left |

**The first rollback attempt proved nothing, and passed.** The update failed at its own backup ("the backup did not
finish … Nothing was changed"), before any checkout or pull. The phase's checks (a non-zero status, the checkout at
v0.5.0, the deployment saying v0.5.0) are just as true of an update that did nothing.

The cause was my fault proxy. The Docker command line half-closes an exec's hijacked stream when it has no more
input, and `pull_fault.py` closed the daemon's connection there, so every exec's output was lost.

Two fixes followed:
- **The proxy** (9bbbc42) passes the half-close through. Its test, `test_pull_fault.py`, runs against a daemon that
  writes only after the client's half-close; it was red before the fix.
- **The phase** now requires all three of: the fault's log of a refused pull, "failed at 'pull the release's
  images'", and "rolled back to v0.5.0". Run against the first attempt's output, all three fail.

### The rollback (`run3b-logs/`, `run3b.sh`): a fresh v0.5.0, the repair, the backup, then the faulted update

- `pull_fault: refused the pull of ghcr.io/aykr/ner@sha256:9c8a2ef2…`: v0.5.1's own `ner`, while v0.5.0's is never
  refused.
- `ospreyflow: the update to v0.5.1 failed at 'pull the release's images': Error response from daemon: manifest
  unknown: the rehearsal's planted fault`
- `ospreyflow: rolled back to v0.5.0, with its data restored from …/20261114T065030Z-osprey-upg-2be985a…`
- Afterwards:
  - the checkout is at v0.5.0;
  - 16 running, 12 healthy, on v0.5.0;
  - max_connections is 100, v0.5.0's own (no 660 in its compose);
  - **every count is identical** to the pre-update snapshot (`diff` exit 0).
- Teardown: exit 0, nothing left. The run's folder was removed, and the logs were scanned for secrets: none.

So v0.5.1's update path has now run for real, both ways. Forward: the signed release, its signatures and its pull.
Back: a failed pull, rolled back to v0.5.0 with its data restored from the update's own backup.
