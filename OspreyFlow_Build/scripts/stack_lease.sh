#!/usr/bin/env bash
# The lanes' throwaway test stacks, each used by one lane at a time (spec/06_DECISIONS.md ADR-142 decision 4
# and Amendment 3; process/CLAUDE.md rule 14). Stack a on this machine and b to g on the owner's test server
# (b and c moved there, f and g added, each with a ClickHouse, on 9 November 2026), listed in scripts/lane_stacks.tsv; scripts/lane_stack_hosts.tsv names a remote stack's host.
# While $OSPREY_LEASE_DIR/no-local-stacks exists (the owner's per-machine switch, 9 November 2026: test on the
# server, not this machine), acquire never takes a stack with no host, even one asked for by name.
#
#   OspreyFlow_Build/scripts/stack_lease.sh acquire <lane> "<purpose>" [a|b]   take a free stack (a first),
#                                                                          or the one named; or say who holds each
#   OspreyFlow_Build/scripts/stack_lease.sh release <lane>                give it back (its stack must be down)
#   OspreyFlow_Build/scripts/stack_lease.sh up <lane>                     start the holder's own stack
#   OspreyFlow_Build/scripts/stack_lease.sh down <lane>                   stop it again, before release
#   OspreyFlow_Build/scripts/stack_lease.sh ports <lane>                  the export line for the holder's stack
#   OspreyFlow_Build/scripts/stack_lease.sh remote <lane> -- <command…>   run a command on a remote stack's own host,
#                                                                          beside its containers (9 November 2026)
#   OspreyFlow_Build/scripts/stack_lease.sh offline <lane> -- <command…>  the same on the server with no stack: the closed
#                                                                          ports and no lane, e.g. make -k test SKIP_JS=1
#   OspreyFlow_Build/scripts/stack_lease.sh live <lane> [--all | --base <ref>] [-- <pytest args…>]   the live test files the
#                                                                          lane's change against main (or <ref>) can reach (tools/live_select.py, admin's
#                                                                          T1 part 3), run with remote on its stack; --all, every one
#   OspreyFlow_Build/scripts/stack_lease.sh remote-log <lane>             follow the lane's last remote run again (after
#                                                                          a dropped ssh session), exiting with its code
#   OspreyFlow_Build/scripts/stack_lease.sh stop <lane>                   end the lane's last run on its host: TERM to its
#                                                                          process group, then KILL to what is left, and
#                                                                          its exit written. This is how a run is ended:
#                                                                          Ctrl-C here ends only the follow, never the run
#   OspreyFlow_Build/scripts/stack_lease.sh reap <lane>                   end what the lane's last run left behind on its
#                                                                          host (every process still carrying its
#                                                                          OSPREY_RUN_TAG), once it has ended; refused
#                                                                          while it is still running
#
# `remote` copies the caller's worktree to <host>:~/osprey-runs/<lane>, sending only what git tracks or would
# track (`git ls-files -co --exclude-standard`), so nothing gitignored ever leaves this machine (rule 9: the
# real-data exceptions and their datasets are gitignored); osprey.yaml goes as committed, never the local
# copy. It makes OspreyFlow_Core's venv there (uv sync --frozen), mirrors the lease's info file into a lease
# directory there for tests/port_guard.py, then runs the command in the same folder relative to the worktree,
# with the stack's ports pinned (its containers listen on 127.0.0.1 there, as the tunnel does here). Over the
# tunnel each database call crosses the internet (about 0.3 to 0.7 s); there it is local.
#   OspreyFlow_Build/scripts/stack_lease.sh status                        each stack: who holds it, since when, for what
#
# A lane holds at most one stack. The leased stacks are the throwaway ones (SESSIONS_RUNBOOK.md §4), never
# `make dev-up`: dev.yaml publishes ArcadeDB on 2480, the owner's own deployment's port (8 November 2026, a
# lane started dev.yaml's containers on this script's own advice before the bind failed).
#
# The locks live outside every worktree (~/.ospreyflow/stack.lease for stack a, stack-b.lease for b, or
# under $OSPREY_LEASE_DIR), so every lane and the orchestrator see the same ones. mkdir is atomic: two lanes
# acquiring one stack at once cannot both succeed. Its red-then-green proof is
# OspreyFlow_Build/tests/test_stack_lease.py (rule 15).
set -euo pipefail

DIR="${OSPREY_LEASE_DIR:-$HOME/.ospreyflow}"
TABLE="$(cd "$(dirname "$0")" && pwd)/lane_stacks.tsv"
HOSTS="$(cd "$(dirname "$0")" && pwd)/lane_stack_hosts.tsv"
PORTS="$(cd "$(dirname "$0")" && pwd)/lane_ports.tsv"   # each lane's Playwright port slot (T2)

# A lane's Playwright port slot, by its exact row; a lane with none is "unlisted-<lane>", which
# OspreyFlow_Core/apps/lanePorts.ts refuses in words (a sub-lane never takes its parent's by prefix).
ports_slot() { awk -F'\t' -v l="$1" '!/^#/ && $1 == l { print $2; found = 1; exit } END { if (!found) print "unlisted-" l }' "$PORTS" 2>/dev/null || echo "unlisted-$1"; }
STACKS="$(grep -v '^#' "$TABLE" | cut -f1 | awk 'NF && !seen[$0]++' | tr '\n' ' ')"
mkdir -p "$DIR"

lock_of() { if [ "$1" = a ]; then echo "$DIR/stack.lease"; else echo "$DIR/stack-$1.lease"; fi; }
# A stack's containers, and the export line for its pinned ports (the table's own columns).
containers_of() { grep -v '^#' "$TABLE" | awk -F'\t' -v s="$1" '$1 == s && $3 != "-" { printf "%s ", $3 }' | sed 's/ $//'; }
ports_line() {
  grep -v '^#' "$TABLE" | awk -F'\t' -v s="$1" -v lane="$2" '$1 == s && $5 == "MINIO_ENDPOINT" { printf "%s=localhost:%s ", $5, $4; next }
    $1 == s && $5 != "-" { printf "%s=%s ", $5, $4 }
    END { printf "POSTGRES_PASSWORD=throwaway OSPREY_LANE=%s", lane }'
  # A stack with its own ClickHouse container gets its credentials; one with no ClickHouse row, the closed 59994.
  if grep -v '^#' "$TABLE" | awk -F'\t' -v s="$1" '$1 == s && $2 == "clickhouse" && $3 != "-" { f = 1 } END { exit !f }'; then
    printf ' CLICKHOUSE_USER=osprey CLICKHOUSE_PASSWORD=throwaway'
  elif ! grep -v '^#' "$TABLE" | awk -F'\t' -v s="$1" '$1 == s && $2 == "clickhouse" { f = 1 } END { exit !f }'; then
    printf ' CLICKHOUSE_HTTP_PORT=59994'
  fi
  # A stack with no OpenSearch row (stack a), the closed 59999, so no client falls back to 9200.
  if ! grep -v '^#' "$TABLE" | awk -F'\t' -v s="$1" '$1 == s && $2 == "opensearch" { f = 1 } END { exit !f }'; then
    printf ' OPENSEARCH_PORT=59999'
  fi
  echo
}
# The ssh host a stack runs on (scripts/lane_stack_hosts.tsv), or nothing for one on this machine.
host_of() { [ -f "$HOSTS" ] || return 0; grep -v '^#' "$HOSTS" | awk -F'\t' -v s="$1" '$1 == s { print $2; exit }'; }
# docker for a stack: on its own host when it has one, here otherwise.
docker_for() {
  local h; h="$(host_of "$1")"; shift
  if [ -n "$h" ]; then DOCKER_HOST="ssh://$h" docker "$@"; else docker "$@"; fi
}
# Whether a stack may be leased on this machine: a local one not while no-local-stacks is there.
offered() { [ ! -e "$DIR/no-local-stacks" ] || [ -n "$(host_of "$1")" ]; }
# ssh with keepalives, so a short drop on a long internet path does not end the session.
rssh() { ssh -o BatchMode=yes -o ServerAliveInterval=15 -o ServerAliveCountMax=8 "$@"; }
# Follow a lane's last remote run from its start until it ends, then exit with its exit code.
follow() {
  local h="$1" rmeta="$2" code
  code=0
  rssh "$h" "l=$rmeta/runs/last; for i in 1 2 3 4 5 6 7 8 9 10; do [ -s \$l/pid ] && break; sleep 1; done
    [ -s \$l/pid ] || { echo 'No remote run recorded.' >&2; exit 2; }
    tail -n +1 -F --pid=\$(cat \$l/pid) \$l/log 2>/dev/null
    for i in 1 2 3 4 5; do [ -f \$l/exit ] && break; sleep 1; done
    exit \$(cat \$l/exit 2>/dev/null || echo 255)" || code=$?
  [ "$code" = 255 ] && echo "The ssh session to $h ended before the run did, or the run left no exit code: follow it again with remote-log." >&2
  return "$code"
}
# Copy the caller's worktree to <host>:~/osprey-runs/<lane> (only what git tracks or would track; osprey.yaml as
# committed), make the venv there, and start the command detached in the same relative folder with the given
# exports, then follow it. Arguments: lane, host, exports, lease lock name (empty for none), stack name, command.
run_on_host() {
  local who="$1" h="$2" exports="$3" lockname="$4" s="$5" top rel rroot rmeta run rc where holder since setup t_setup keep
  shift 5
  t_setup="$(date +%s)"   # the copy, venv and packages before the command: logged beside its wall time
  rroot="${OSPREY_REMOTE_ROOT:-osprey-runs}/$who"
  rmeta="$rroot.meta"   # the runs and the lease mirror, beside the copy, never in it
  top="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "Not inside a git worktree: run remote from your lane's checkout." >&2; return 1; }
  rel="$(git rev-parse --show-prefix)"
  # Refused before anything is copied: a second call while the lane's last run is alive must not rewrite the
  # copy that run is reading (found by rules, 9 November 2026). Checked again at the start, for a race.
  rc=0
  # A run started before the runs moved beside the copy (ada8460) keeps them inside it, in .runs: ask there too.
  rssh "$h" "for f in $rmeta/runs/last/pid $rroot/.runs/last/pid; do if [ -f \$f ] && kill -0 \$(cat \$f) 2>/dev/null; then exit 3; fi; done" || rc=$?
  case $rc in
    0) ;;
    3) echo "$who's last remote run is still running on $h: follow it with remote-log $who, or wait for it." >&2; return 1 ;;
    *) echo "Could not reach $h." >&2; return 1 ;;
  esac
  list="$(mktemp)"; trap 'rm -f "$list" "$list.cmd"' EXIT
  # What git tracks or would track, less the local osprey.yaml (sent as committed, below) and paths gone from disk.
  ( cd "$top" && git ls-files -co --exclude-standard -z | tr '\0' '\n' \
      | grep -v -x 'OspreyFlow_Core/osprey.yaml' | while IFS= read -r f; do [ -e "$f" ] && printf '%s\n' "$f"; done ) > "$list"
  rssh "$h" "mkdir -p $rroot" || { echo "Could not reach $h." >&2; return 1; }
  rsync -a --files-from="$list" "$top/" "$h:$rroot/" || { echo "Copying the worktree to $h failed." >&2; return 1; }
  # Remove what the worktree no longer has (never the venv or caches), then the committed osprey.yaml.
  rssh "$h" "cd $rroot && python3 -c 'import os,sys
keep=set(sys.stdin.read().splitlines()); keep.add(\"OspreyFlow_Core/osprey.yaml\")
skip=(\".venv\",\"node_modules\",\".pytest_cache\",\"__pycache__\",\".git\",\".runs\",\".osprey-lease\")
for d,ds,fs in os.walk(\".\"):
  ds[:]=[x for x in ds if x not in skip]
  for f in fs:
    p=os.path.relpath(os.path.join(d,f))
    if p not in keep: os.remove(p)'" < "$list" || { echo "Pruning the copy on $h failed." >&2; return 1; }
  ( cd "$top" && git show HEAD:OspreyFlow_Core/osprey.yaml ) | rssh "$h" "cat > $rroot/OspreyFlow_Core/osprey.yaml"
  # The lease's info file mirrored for the port guard there; an offline run gets an empty lease directory.
  if [ -n "$lockname" ]; then
    rssh "$h" "rm -rf $rmeta/lease && mkdir -p $rmeta/lease/$lockname && cat > $rmeta/lease/$lockname/info" < "$(lock_of "$s")/info"
  else
    rssh "$h" "rm -rf $rmeta/lease && mkdir -p $rmeta/lease"
  fi
  rssh "$h" "cd $rroot/OspreyFlow_Core && ~/.local/bin/uv sync --frozen -q" || { echo "uv sync on $h failed." >&2; return 1; }
  # The copy as a repository of its own, committed afresh each run, so a test reading HEAD or git ls-files sees
  # what was sent (osprey.yaml as committed); and the Glass's packages, installed again only when the lock changes. The
  # lock's hash is kept in the lane's meta folder, from $HOME: written relative to the copy's OspreyFlow_Core it sat
  # inside the copy, and the prune above removed it on every run, so npm ci ran every time (case-b, 14 November 2026).
  rssh "$h" "cd $rroot && { [ -d .git ] || git init -q; } && git add -A && git -c user.name='OspreyFlow test runner' -c user.email=test-runner@ospreyflow.invalid commit -q --allow-empty -m 'the copy sent for this run'" \
    || { echo "The git snapshot on $h failed." >&2; return 1; }
  rssh "$h" "export PATH=\$HOME/.local/node/bin:\$PATH; cd $rroot/OspreyFlow_Core && l=\$(sha256sum package-lock.json | cut -c1-64); [ \"\$l\" = \"\$(cat \$HOME/$rmeta/npm.lock 2>/dev/null)\" ] || { npm ci --no-audit --no-fund --loglevel=error >/dev/null && mkdir -p \$HOME/$rmeta && echo \$l > \$HOME/$rmeta/npm.lock; }" \
    || { echo "npm ci on $h failed." >&2; return 1; }
  # The run is started detached on the host and logged there, so a dropped ssh session loses nothing:
  # `remote-log <lane>` follows it again. A lane runs one remote command at a time.
  # Unique beyond the second (T1 part 5's review, must-fix 6): two runs of one lane never share a folder, so never a
  # tag. The folder is made with a plain mkdir on the host, which fails rather than reuse one already there.
  run="$rmeta/runs/$(date -u +%Y%m%dT%H%M%SZ)-$(od -An -N4 -tx4 /dev/urandom | tr -d ' ')"
  # The log ends with its wall time, naming the stack and lease it ran under (rule 14), and keeps the seconds in
  # <run>/wall; pytest names its 30 slowest tests, whatever the command (admin's T1 part 1, 10 November 2026).
  # The lease is named by its holder and since (its lock directory is the same for every lease on a stack); both
  # are kept to safe characters, since they go inside the single-quoted bash -c below. <run>/lease keeps its info.
  if [ -n "$lockname" ]; then
    holder="$(sed -n 's/^holder=//p' "$(lock_of "$s")/info" | tr -cd 'A-Za-z0-9_.-')"
    since="$(sed -n 's/^since=//p' "$(lock_of "$s")/info" | tr -cd 'A-Za-z0-9:_.-')"
    where="stack $s, the lease $holder took at $since"
  else
    where="no stack, no lease"
  fi
  { printf 'cd %q || exit 1\n' "$rroot/$rel"
    # OSPREY_PORTS_LANE and OSPREY_PORTS_SLOT: the lane and its own Playwright ports (OspreyFlow_Core/apps/lanePorts.ts),
    # as lanes' copies run side by side here; not OSPREY_LANE, which an offline run must not name (the port guard's).
    printf 'export %s PYTEST_ADDOPTS=--durations=30 OSPREY_LEASE_DIR=$HOME/%s/lease OSPREY_PORTS_LANE=%s OSPREY_PORTS_SLOT=%s PATH=$HOME/.local/node/bin:$HOME/.local/bin:$PATH\n' "$exports" "$rmeta" "$who" "$(ports_slot "$who")"
    # The run's tag (T1 part 5): every process the run starts inherits it, through setsid and double forks, which a
    # process group is not (platform-b, 10 November 2026: harness-a11y's vite and harness.webapp outlived a stopped
    # run and held the lane's slot ports). When cmd.sh exits, every process still carrying it is ended, and on TERM
    # too (bash ends at once and runs the EXIT trap). INT and HUP are not claimed: the start call below backgrounds the
    # run from a non-interactive shell, which starts it with INT and QUIT ignored (as nohup ignores HUP), and a shell
    # cannot take back a signal ignored when it started (T1 part 5's review, measured: the run's command sees INT
    # ignored). Stopping a run is TERM; making INT work would need the run started with INT restored (CARRIES).
    printf 'export OSPREY_RUN_TAG=$HOME/%s\n' "$run"
    printf '%s\n' "$REAPER"
    printf 'trap '"'"'osprey_reap "$OSPREY_RUN_TAG"'"'"' EXIT\n'
    printf '%q ' "$@"; echo; } > "$list.cmd"
  rc=0
  setup=$(( $(date +%s) - t_setup ))
  keep=""; [ -n "$lockname" ] && keep="cp $rmeta/lease/$lockname/info $run/lease &&"
  rssh "$h" "if [ -f $rmeta/runs/last/pid ] && kill -0 \$(cat $rmeta/runs/last/pid) 2>/dev/null; then exit 3; fi
    mkdir -p $rmeta/runs && mkdir $run || exit 4
    cat > $run/cmd.sh && $keep ln -sfn \$HOME/$run $rmeta/runs/last || exit 5
    { cd \$HOME && nohup setsid bash -c 'echo \$\$ > $run/pid; t0=\$(date +%s); bash $run/cmd.sh; c=\$?; w=\$((\$(date +%s)-t0)); echo \$w > $run/wall; echo \"Wall time: \$w s, exit \$c ($where; set-up before it $setup s)\"; echo \$c > $run/exit' > $run/log 2>&1 < /dev/null; } > /dev/null 2>&1 &
    exit 0" < "$list.cmd" || rc=$?
  case $rc in
    0) ;;
    3) echo "$who's last remote run is still running on $h: follow it with remote-log $who, or wait for it." >&2; return 1 ;;
    4) echo "The run's folder $run could not be made new on $h (one of that name is there already): nothing was started." >&2; return 1 ;;
    5) echo "The run's folder $run on $h could not be set up (its command, lease or last link): nothing was started." >&2; return 1 ;;
    *) echo "Could not start the run on $h." >&2; return 1 ;;
  esac
  echo "Running on $h (stack $s, $rroot/$rel), logged at $run/log: $*" >&2
  follow "$h" "$rmeta"
}
# The reaper a run's cmd.sh defines, and `reap` sends (T1 part 5): it ends every process whose environment holds
# exactly OSPREY_RUN_TAG=<tag> (TERM, then KILL two seconds later), never itself. /proc is Linux's; the hosts are.
# The tag is its argument alone: an empty one is refused, never read as "every process tagged with nothing" nor taken
# from the caller's own environment. The environment is read whole, NUL-separated (`grep -z`), so a value holding a
# newline never matches, and with no redirection that could print its own error. Each pid's environment is read
# again before TERM and before KILL: a pid that ended and was given to another process is never signalled.
# OSPREY_REAPED holds how many were ended, for the caller's words.
# Then the Docker objects the run left, by its label (`osprey.run=<tag>`, which tests/harness/run_owned.py gives the
# test-IdP containers and network; the orchestrator's ruling of 14 November 2026): containers first, then networks,
# which Docker refuses to remove while a container is on them. Another run's, and unlabelled ones, are never touched.
# The scan reads $OSPREY_PROC_ROOT's pid folders when it is set, else /proc's; the re-read before each signal always
# reads /proc, so a pid listed there is signalled only when the real process holds the tag. Nothing on a host sets
# it, and neither cmd.sh's export line nor ssh carries it there (tests/test_stack_lease.py shows both), so a real run
# scans /proc. The tests give a run that is not about reaping an empty table: the scan reads every process on the
# host, one grep each, and a test waiting 5 s on a run's exit file waited on every other lane's run there too (case-b's
# lease-tests record, 14 November 2026).
# shellcheck disable=SC2016
REAPER='osprey_reap() {
  local tag="$1" p pid hit="" n=0 root="${OSPREY_PROC_ROOT:-/proc}"
  OSPREY_REAPED=0
  [ -n "$tag" ] || { echo "No run tag to reap by: nothing reaped." >&2; return 2; }
  osprey_tagged() { grep -qzxF "OSPREY_RUN_TAG=$tag" "${2:-/proc}/$1/environ" 2>/dev/null; }
  for p in "$root"/[0-9]*; do
    pid="${p##*/}"
    [ "$pid" = "$$" ] && continue
    if osprey_tagged "$pid" "$root"; then hit="$hit $pid"; fi
  done
  for pid in $hit; do osprey_tagged "$pid" && kill "$pid" 2>/dev/null && n=$((n + 1)); done
  if [ -n "$hit" ]; then sleep 2; for pid in $hit; do if osprey_tagged "$pid"; then kill -9 "$pid" 2>/dev/null; fi; done; fi
  OSPREY_REAPED=$n
  if [ "$n" -gt 0 ]; then echo "Reaped $n process(es) the run left behind ($tag)." >&2; fi
  if command -v docker >/dev/null 2>&1; then
    local ids nets c=0
    ids=$(docker ps -aq --filter "label=osprey.run=$tag" 2>/dev/null)
    if [ -n "$ids" ]; then c=$(printf "%s\n" $ids | wc -l | tr -d " "); docker rm -f -v $ids >/dev/null 2>&1; fi
    nets=$(docker network ls -q --filter "label=osprey.run=$tag" 2>/dev/null)
    if [ -n "$nets" ]; then docker network rm $nets >/dev/null 2>&1; fi
    if [ "$c" -gt 0 ]; then echo "Removed $c container(s) the run left in Docker, and their network(s) ($tag)." >&2; fi
  fi
  return 0
}'
# Whether any process of a run's own session is alive: the wrapper is its session's leader (setsid), so cmd.sh and its
# command are in it even once the wrapper is gone; a leftover server that made a session of its own is not.
# shellcheck disable=SC2016
SESSION_ALIVE='osprey_session_alive() {
  local sid="$1" p
  for p in /proc/[0-9]*/stat; do
    [ "$(cut -d")" -f2- "$p" 2>/dev/null | cut -d" " -f5)" = "$sid" ] && return 0
  done
  return 1
}'
# The host offline runs go to: $OSPREY_OFFLINE_HOST, or the first host lane_stack_hosts.tsv names.
offline_host() {
  if [ -n "${OSPREY_OFFLINE_HOST:-}" ]; then echo "$OSPREY_OFFLINE_HOST"; return; fi
  [ -f "$HOSTS" ] && grep -v '^#' "$HOSTS" | awk -F'\t' 'NF >= 2 { print $2; exit }'
}
tunnel_sock() { echo "$DIR/tunnel-$1.sock"; }
# One ssh connection carrying each of a remote stack's ports to this machine's 127.0.0.1.
tunnel_open() {
  local s="$1" h fwd="" p
  h="$(host_of "$s")"
  for p in $(grep -v '^#' "$TABLE" | awk -F'\t' -v s="$s" '$1 == s && $4 != "-" { print $4 }'); do
    fwd="$fwd -L 127.0.0.1:$p:127.0.0.1:$p"
  done
  # shellcheck disable=SC2086
  ssh -f -N -M -S "$(tunnel_sock "$s")" -o ExitOnForwardFailure=yes -o BatchMode=yes $fwd "$h"
}
# The test stacks' Postgres allows PG_CONNECTIONS (T1 part 4, 10 November 2026): one Conduit's asyncpg pools open 47
# connections at their minimum, and the default 100 refused four pytest-xdist workers on one stack. Read once the
# server answers; if it allows fewer, ALTER SYSTEM (kept in the container's data folder) and restart that container
# alone, then read it again. Fails if it never answers or still allows fewer. Only the osprey-test-* stacks.
PG_CONNECTIONS=400
pg_show() {
  local s="$1" c="$2" i tries="${OSPREY_PG_READY_TRIES:-60}" got
  for ((i = 0; i < tries; i++)); do
    if got="$(docker_for "$s" exec "$c" psql -U osprey -d postgres -tAc 'SHOW max_connections' 2>/dev/null)" &&
      [[ "$got" =~ ^[0-9]+$ ]]; then
      echo "$got"; return 0
    fi
    sleep "${OSPREY_PG_READY_PAUSE:-1}"
  done
  echo "Test stack $s's Postgres ($c) did not answer after $tries tries." >&2
  return 1
}
pg_connections() {
  local s="$1" c have
  c="$(grep -v '^#' "$TABLE" | awk -F'\t' -v s="$s" '$1 == s && $2 == "postgres" && $3 != "-" { print $3 }')"
  [ -n "$c" ] || return 0
  have="$(pg_show "$s" "$c")" || return 1
  if [ "$have" -lt "$PG_CONNECTIONS" ]; then
    docker_for "$s" exec "$c" psql -U osprey -d postgres -tAc "ALTER SYSTEM SET max_connections = $PG_CONNECTIONS" >/dev/null ||
      { echo "Test stack $s's Postgres ($c) refused ALTER SYSTEM." >&2; return 1; }
    docker_for "$s" restart "$c" >/dev/null || { echo "docker could not restart $c." >&2; return 1; }
    have="$(pg_show "$s" "$c")" || return 1
  fi
  if [ "$have" -lt "$PG_CONNECTIONS" ]; then
    echo "Test stack $s's Postgres ($c) allows max_connections $have after a restart, not $PG_CONNECTIONS." >&2
    return 1
  fi
  echo "Test stack $s's Postgres ($c): max_connections $have."
}
tunnel_close() {
  local s="$1"
  ssh -S "$(tunnel_sock "$s")" -O exit "$(host_of "$s")" >/dev/null 2>&1 || true
}

# The stack a lane holds, or nothing.
held_by() {
  local s
  for s in $STACKS; do
    if [ "$(sed -n 's/^holder=//p' "$(lock_of "$s")/info" 2>/dev/null || true)" = "$1" ]; then echo "$s"; return 0; fi
  done
}

# Whether a stack is up, as "up" or "down". For stack a, dev.yaml's compose project is checked too (it is
# named after the compose file's folder, "compose", in every worktree, so asking from any worktree sees
# the one shared stack). Only the stack's own containers are asked about, so another lane's live run on
# the other stack does not hold a release up. If docker cannot answer, it says so and fails, so a release
# is refused rather than let through blind.
stack_state() {
  local stack="$1" root core out="" more filters="" c
  if [ "$stack" = a ]; then
    root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
    core="$root/OspreyFlow_Core"
    if [ ! -f "$core/deploy/compose/dev.yaml" ]; then
      echo "No OspreyFlow_Core/deploy/compose/dev.yaml under $root: run this from a checkout." >&2
      return 1
    fi
    if ! out="$(docker compose -f "$core/deploy/compose/dev.yaml" ps -q 2>&1)"; then
      echo "docker could not say whether the dev stack is up: $out" >&2
      return 1
    fi
  fi
  for c in $(containers_of "$stack"); do filters="$filters --filter name=^/?$c\$"; done
  # shellcheck disable=SC2086
  if ! more="$(docker_for "$stack" ps -q $filters 2>&1)"; then
    echo "docker could not say whether test stack $stack is up: $more" >&2
    return 1
  fi
  if [ -n "$out" ] || [ -n "$more" ]; then echo up; else echo down; fi
}

# Whether every one of a stack's containers is running, asked of the stack's own host (T1 part 5; studio's L1.7 ran
# a whole live selection against a leased stack that was down, 10 November 2026). One container up is not the stack
# up. Prints nothing and succeeds when all are up; names each one that is down and fails otherwise; fails, saying
# so, when docker cannot answer, so a run is refused rather than sent blind.
stack_wholly_up() {
  local s="$1" c filters="" running missing=""
  for c in $(containers_of "$s"); do filters="$filters --filter name=^/?$c\$"; done
  # shellcheck disable=SC2086
  if ! running="$(docker_for "$s" ps --format '{{.Names}}' $filters 2>&1)"; then
    echo "docker could not say whether test stack $s is up: $running" >&2
    return 1
  fi
  for c in $(containers_of "$s"); do
    grep -qx "$c" <<< "$running" || missing="$missing $c"
  done
  [ -z "$missing" ] && return 0
  echo "Test stack $s is not up (not running:$missing): start it with OspreyFlow_Build/scripts/stack_lease.sh up $LEASE_LANE, then run again. Nothing was sent." >&2
  return 1
}

cmd="${1:-status}"
LEASE_LANE="${2:-}"
case "$cmd" in
  acquire)
    who="${2:?usage: stack_lease.sh acquire <lane> \"<purpose>\" [a|b]}"
    why="${3:-}"
    want="${4:-}"
    mine="$(held_by "$who")"
    if [ -n "$mine" ]; then
      echo "$who already holds stack $mine: a lane holds one stack at a time." >&2
      exit 1
    fi
    if [ -n "$want" ]; then
      case " $STACKS " in *" $want "*) ;; *) echo "No stack '$want' (one of: $STACKS)." >&2; exit 2;; esac
      if ! offered "$want"; then
        echo "Stack $want runs on this machine, and local stacks are off here ($DIR/no-local-stacks): take a server stack." >&2
        exit 1
      fi
      try="$want"
    else
      try=""
      for s in $STACKS; do if offered "$s"; then try="$try $s"; fi; done
    fi
    for s in $try; do
      lock="$(lock_of "$s")"
      if mkdir "$lock" 2>/dev/null; then
        printf 'holder=%s\nstack=%s\npurpose=%s\nsince=%s\nworktree=%s\n' \
          "$who" "$s" "$why" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(pwd)" > "$lock/info.tmp"
        mv "$lock/info.tmp" "$lock/info"
        echo "Lease on stack $s taken by $who. Start it with: OspreyFlow_Build/scripts/stack_lease.sh up $who (the throwaway stack, not dev.yaml's, which binds the owner's 2480)"
        echo "Pin its ports for every live run: export $(ports_line "$s" "$who")"
        exit 0
      fi
    done
    echo "Every test stack you asked for is leased; wait, or ask the orchestrator:" >&2
    for s in $try; do
      echo "stack $s:" >&2
      cat "$(lock_of "$s")/info" >&2 2>/dev/null || echo "(no details recorded yet)" >&2
    done
    exit 1
    ;;
  release)
    who="${2:?usage: stack_lease.sh release <lane>}"
    s="$(held_by "$who")"
    if [ -z "$s" ]; then
      held=""
      for t in $STACKS; do [ -d "$(lock_of "$t")" ] && held="$held $t"; done
      if [ -z "$held" ]; then echo "No lease is held."; exit 0; fi
      echo "$who holds no stack (held:$held; status shows by whom)." >&2
      exit 1
    fi
    state="$(stack_state "$s")" || { echo "Not released." >&2; exit 1; }
    if [ "$state" = up ]; then
      echo "Test stack $s is still up. Run OspreyFlow_Build/scripts/stack_lease.sh down $who first." >&2
      exit 1
    fi
    rm -rf "$(lock_of "$s")"
    echo "Lease on stack $s released by $who."
    ;;
  up|down)
    who="${2:?usage: stack_lease.sh up|down <lane>}"
    s="$(held_by "$who")"
    if [ -z "$s" ]; then
      echo "$who holds no stack: take one first (acquire)." >&2
      exit 1
    fi
    if [ "$cmd" = up ]; then verb=start; else verb=stop; fi
    read -r -a these <<< "$(containers_of "$s")"
    remote="$(host_of "$s")"
    [ "$cmd" = down ] && [ -n "$remote" ] && tunnel_close "$s"
    docker_for "$s" "$verb" "${these[@]}" >/dev/null || { echo "docker could not $verb test stack $s." >&2; exit 1; }
    [ "$cmd" = up ] && { pg_connections "$s" || exit 1; }
    if [ "$cmd" = up ] && [ -n "$remote" ]; then
      tunnel_open "$s" || { echo "Test stack $s started on $remote, but its ssh tunnel did not open: run down, then up." >&2; exit 1; }
    fi
    echo "Test stack $s ${cmd} for $who: ${these[*]}${remote:+ (on $remote, tunnelled to 127.0.0.1 here)}"
    ;;
  remote)
    who="${2:?usage: stack_lease.sh remote <lane> -- <command…>}"
    shift 2
    [ "${1:-}" = "--" ] && shift
    [ "$#" -gt 0 ] || { echo "usage: stack_lease.sh remote <lane> -- <command…>" >&2; exit 2; }
    s="$(held_by "$who")"
    [ -n "$s" ] || { echo "$who holds no stack: take one first (acquire)." >&2; exit 1; }
    h="$(host_of "$s")"
    [ -n "$h" ] || { echo "Stack $s runs on this machine: run the command here, not with remote." >&2; exit 1; }
    stack_wholly_up "$s" || exit 1
    run_on_host "$who" "$h" "$(ports_line "$s" "$who")" "$(basename "$(lock_of "$s")")" "$s" "$@"
    ;;
  offline)
    who="${2:?usage: stack_lease.sh offline <lane> -- <command…>}"
    shift 2
    [ "${1:-}" = "--" ] && shift
    [ "$#" -gt 0 ] || { echo "usage: stack_lease.sh offline <lane> -- <command…>" >&2; exit 2; }
    h="$(offline_host)"
    [ -n "$h" ] || { echo "No host for offline runs: lane_stack_hosts.tsv names none (or set OSPREY_OFFLINE_HOST)." >&2; exit 1; }
    # The closed ports, no lane and no lease: the port guard refuses every live port, as for an offline run here.
    run_on_host "$who" "$h" "ARCADEDB_HTTP_PORT=59991 POSTGRES_PORT=59992 VALKEY_PORT=59993 CLICKHOUSE_HTTP_PORT=59994 OPENSEARCH_PORT=59999" "" "offline" "$@"
    ;;
  live)
    who="${2:?usage: stack_lease.sh live <lane> [--all | --base <ref>] [-- <pytest args…>]}"
    shift 2
    all=""
    case "${1:-}" in
      --all) all="--all"; shift ;;
      --base) all="--base ${2:?usage: stack_lease.sh live <lane> --base <ref>}"; shift 2 ;;
    esac
    [ "${1:-}" = "--" ] && shift
    s="$(held_by "$who")"
    [ -n "$s" ] || { echo "$who holds no stack: take one first (acquire)." >&2; exit 1; }
    h="$(host_of "$s")"
    [ -n "$h" ] || { echo "Stack $s runs on this machine: run the selection here, not with live." >&2; exit 1; }
    stack_wholly_up "$s" || exit 1
    top="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "Not inside a git worktree: run live from your lane's checkout." >&2; exit 1; }
    cd "$top/OspreyFlow_Build"
    # The selection is made here, from the lane's own diff; OSPREY_LIVE_SELECT stands in for it in the tests.
    # shellcheck disable=SC2086
    picks="$(${OSPREY_LIVE_SELECT:-../OspreyFlow_Core/.venv/bin/python -m tools.live_select} $all --why)" \
      || { echo "The selection failed: nothing was run." >&2; exit 1; }
    files=()
    while IFS= read -r f; do [ -n "$f" ] && files+=("../OspreyFlow_Build/$f"); done <<< "$picks"
    [ "${#files[@]}" -gt 0 ] || { echo "The selection came out empty, which it never should (route rights is its floor): nothing was run." >&2; exit 1; }
    echo "live: ${#files[@]} live test files${all:+ ($all)}." >&2
    run_on_host "$who" "$h" "$(ports_line "$s" "$who")" "$(basename "$(lock_of "$s")")" "$s" \
      sh -c 'cd ../OspreyFlow_Core && exec .venv/bin/pytest -c ../OspreyFlow_Build/pytest.ini -q -rfE "$@"' sh "${files[@]}" "$@"
    ;;
  remote-log)
    who="${2:?usage: stack_lease.sh remote-log <lane>}"
    s="$(held_by "$who")"
    h=""; [ -n "$s" ] && h="$(host_of "$s")"
    [ -n "$h" ] || h="$(offline_host)"   # no remote stack held: the lane's offline run
    [ -n "$h" ] || { echo "No host to follow a run on." >&2; exit 1; }
    follow "$h" "${OSPREY_REMOTE_ROOT:-osprey-runs}/$who.meta"
    ;;
  stop)
    # Ends the lane's last run (remote, live or offline) on its host (T1 part 5; the orchestrator's ruling): TERM to
    # its process group (the wrapper is its session's and group's leader), up to 15 s for it to end, then KILL to the
    # group and every process of the run's tag still there; then the run's exit file (143, or 137 when a KILL was
    # needed), unless the run wrote its own, so its follow ends and the lane's next run is allowed. Ctrl-C on this
    # machine ends only the follow, never the run.
    who="${2:?usage: stack_lease.sh stop <lane>}"
    s="$(held_by "$who")"
    h=""; [ -n "$s" ] && h="$(host_of "$s")"
    [ -n "$h" ] || h="$(offline_host)"
    [ -n "$h" ] || { echo "No host to stop a run on." >&2; exit 1; }
    rmeta="${OSPREY_REMOTE_ROOT:-osprey-runs}/$who.meta"
    rc=0
    printf '%s\n%s\n%s\n' "$REAPER" "$SESSION_ALIVE" \
      't=$(readlink "$1/runs/last") || { echo "No run of this lane is recorded on this host." >&2; exit 0; }
      w=$(cat "$t/pid" 2>/dev/null)
      [ -n "$w" ] || { echo "The run $t recorded no pid: nothing stopped." >&2; exit 3; }
      if [ -f "$t/exit" ] && ! kill -0 "$w" 2>/dev/null && ! osprey_session_alive "$w"; then echo "The run $t has ended already (exit $(cat "$t/exit"))."; exit 0; fi
      kill -TERM -- "-$w" 2>/dev/null
      code=143
      for i in $(seq 1 30); do osprey_session_alive "$w" || break; sleep 0.5; done
      if osprey_session_alive "$w"; then kill -KILL -- "-$w" 2>/dev/null; code=137; fi
      osprey_reap "$t" >/dev/null 2>&1
      [ -f "$t/exit" ] || echo "$code" > "$t/exit"
      echo "Stopped the run $t (exit $(cat "$t/exit"))."' \
      | rssh "$h" "bash -s -- $rmeta" || rc=$?
    case $rc in
      0) ;;
      3) exit 3 ;;
      *) echo "Could not reach $h to stop the run." >&2; exit 1 ;;
    esac
    ;;
  reap)
    # What the lane's last run (remote, live or offline) left behind, when its wrapper was itself killed and its
    # own reaper never ran: every process on the host still carrying that run's OSPREY_RUN_TAG (T1 part 5).
    who="${2:?usage: stack_lease.sh reap <lane>}"
    s="$(held_by "$who")"
    h=""; [ -n "$s" ] && h="$(host_of "$s")"
    [ -n "$h" ] || h="$(offline_host)"
    [ -n "$h" ] || { echo "No host to reap a run on." >&2; exit 1; }
    rmeta="${OSPREY_REMOTE_ROOT:-osprey-runs}/$who.meta"
    # Sent on stdin, so nothing in it is expanded here; the tag is the run folder `last` points at. It fails closed
    # (T1 part 5's review): reaped only once the run has ended, its exit written, or its recorded pid dead with no
    # process of its session left (cmd.sh and its command outlive a killed wrapper in it). Otherwise refused: a
    # running run is ended with `stop`.
    rc=0
    printf '%s\n%s\n%s\n' "$REAPER" "$SESSION_ALIVE" \
      't=$(readlink "$1/runs/last") || { echo "No run of this lane is recorded on this host." >&2; exit 0; }
      w=$(cat "$t/pid" 2>/dev/null)
      if [ ! -f "$t/exit" ]; then
        if [ -z "$w" ]; then echo "The run $t recorded no pid and no exit: it may be starting; nothing reaped." >&2; exit 3; fi
        if kill -0 "$w" 2>/dev/null || osprey_session_alive "$w"; then echo "The run $t is still running: end it with stop; nothing reaped." >&2; exit 3; fi
      fi
      osprey_reap "$t" || exit $?
      if [ "$OSPREY_REAPED" -gt 0 ]; then echo "Reaped $OSPREY_REAPED process(es) the run $t left behind."; else echo "No process tagged for the run $t was found: nothing reaped."; fi' \
      | rssh "$h" "bash -s -- $rmeta" || rc=$?
    case $rc in
      0) ;;
      2|3) exit "$rc" ;;
      *) echo "Could not reach $h to reap." >&2; exit 1 ;;
    esac
    ;;
  ports)
    who="${2:?usage: stack_lease.sh ports <lane>}"
    s="$(held_by "$who")"
    [ -n "$s" ] || { echo "$who holds no stack." >&2; exit 1; }
    echo "export $(ports_line "$s" "$who")"
    ;;
  status)
    for s in $STACKS; do
      lock="$(lock_of "$s")"
      if ! offered "$s"; then
        echo "$s: off (local stacks are off on this machine)"
      elif [ -d "$lock" ]; then
        printf '%s: %s\n' "$s" "$(tr '\n' ' ' < "$lock/info" 2>/dev/null | sed 's/ $//' || echo "held (no details recorded yet)")"
      else
        echo "$s: free"
      fi
    done
    ;;
  *)
    echo "usage: stack_lease.sh acquire <lane> \"<purpose>\" [a|b] | up <lane> | down <lane> | ports <lane> | remote <lane> -- <command…> | live <lane> [--all | --base <ref>] [-- <pytest args…>] | offline <lane> -- <command…> | remote-log <lane> | stop <lane> | reap <lane> | release <lane> | status" >&2
    exit 2
    ;;
esac
