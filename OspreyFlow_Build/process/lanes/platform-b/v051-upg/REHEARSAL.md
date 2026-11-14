# v0.5.0 → v0.5.1 upgrade rehearsal (platform-b, 14 November 2026, 00:48–01:30 UTC)

The orchestrator's last gate before publishing v0.5.1: the update rehearsed on the test server
(`ospreyflow-test`) as a throwaway named deployment, `osprey-upg`. osprey-small was never touched: this
session refused a read-only compose call on it, and that refusal was not worked around. No lane stack
and no lease were used.

- **Root:** `/root/osprey-runs/platform-b-upg`, with its own HOME.
- **Driver:** `upg_run.sh`, the rules lane's `gates/upg_run.sh` adapted. Its guards are kept:
  - `tools/upg_guard.sh`: compose only as `-p osprey-upg` on the run's own file; volume removal of
    `osprey-upg_*` alone; no prune.
  - `tools/upg_images.py` with P5b's `OwnImages`, for the image tags.
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
| 12 | teardown | **REFUSED (exit 2)**: five anonymous volumes; see below. The image tags were put back (12b, exit 0) |

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
They are not removed until the orchestrator says so, and the run's folder is kept until then.
