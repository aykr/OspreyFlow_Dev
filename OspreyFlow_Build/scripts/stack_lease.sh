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
#   OspreyFlow_Build/scripts/stack_lease.sh live <lane> [--all] [-- <pytest args…>]   the live test files the lane's change
#                                                                          against main can reach (scripts/live_select.py, admin's
#                                                                          T1 part 3), run with remote on its stack; --all, every one
#   OspreyFlow_Build/scripts/stack_lease.sh remote-log <lane>             follow the lane's last remote run again (after
#                                                                          a dropped ssh session), exiting with its code
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
  # what was sent (osprey.yaml as committed); and the Glass's packages, installed again only when the lock changes.
  rssh "$h" "cd $rroot && { [ -d .git ] || git init -q; } && git add -A && git -c user.name='OspreyFlow test runner' -c user.email=test-runner@ospreyflow.invalid commit -q --allow-empty -m 'the copy sent for this run'" \
    || { echo "The git snapshot on $h failed." >&2; return 1; }
  rssh "$h" "export PATH=\$HOME/.local/node/bin:\$PATH; cd $rroot/OspreyFlow_Core && l=\$(sha256sum package-lock.json | cut -c1-64); [ \"\$l\" = \"\$(cat $rmeta/npm.lock 2>/dev/null)\" ] || { npm ci --no-audit --no-fund --loglevel=error >/dev/null && mkdir -p $rmeta && echo \$l > $rmeta/npm.lock; }" \
    || { echo "npm ci on $h failed." >&2; return 1; }
  # The run is started detached on the host and logged there, so a dropped ssh session loses nothing:
  # `remote-log <lane>` follows it again. A lane runs one remote command at a time.
  run="$rmeta/runs/$(date -u +%Y%m%dT%H%M%SZ)"
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
    printf 'export %s PYTEST_ADDOPTS=--durations=30 OSPREY_LEASE_DIR=$HOME/%s/lease PATH=$HOME/.local/node/bin:$HOME/.local/bin:$PATH\n' "$exports" "$rmeta"
    printf '%q ' "$@"; echo; } > "$list.cmd"
  rc=0
  setup=$(( $(date +%s) - t_setup ))
  keep=""; [ -n "$lockname" ] && keep="cp $rmeta/lease/$lockname/info $run/lease &&"
  rssh "$h" "if [ -f $rmeta/runs/last/pid ] && kill -0 \$(cat $rmeta/runs/last/pid) 2>/dev/null; then exit 3; fi
    mkdir -p $run && cat > $run/cmd.sh && $keep ln -sfn \$HOME/$run $rmeta/runs/last
    cd \$HOME && nohup setsid bash -c 'echo \$\$ > $run/pid; t0=\$(date +%s); bash $run/cmd.sh; c=\$?; w=\$((\$(date +%s)-t0)); echo \$w > $run/wall; echo \"Wall time: \$w s, exit \$c ($where; set-up before it $setup s)\"; echo \$c > $run/exit' > $run/log 2>&1 < /dev/null &
    exit 0" < "$list.cmd" || rc=$?
  case $rc in
    0) ;;
    3) echo "$who's last remote run is still running on $h: follow it with remote-log $who, or wait for it." >&2; return 1 ;;
    *) echo "Could not start the run on $h." >&2; return 1 ;;
  esac
  echo "Running on $h (stack $s, $rroot/$rel), logged at $run/log: $*" >&2
  follow "$h" "$rmeta"
}
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

cmd="${1:-status}"
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
    run_on_host "$who" "$h" "ARCADEDB_HTTP_PORT=59991 POSTGRES_PORT=59992 VALKEY_PORT=59993 CLICKHOUSE_HTTP_PORT=59994" "" "offline" "$@"
    ;;
  live)
    who="${2:?usage: stack_lease.sh live <lane> [--all] [-- <pytest args…>]}"
    shift 2
    all=""
    [ "${1:-}" = "--all" ] && { all="--all"; shift; }
    [ "${1:-}" = "--" ] && shift
    s="$(held_by "$who")"
    [ -n "$s" ] || { echo "$who holds no stack: take one first (acquire)." >&2; exit 1; }
    h="$(host_of "$s")"
    [ -n "$h" ] || { echo "Stack $s runs on this machine: run the selection here, not with live." >&2; exit 1; }
    top="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "Not inside a git worktree: run live from your lane's checkout." >&2; exit 1; }
    cd "$top/OspreyFlow_Build"
    # The selection is made here, from the lane's own diff; OSPREY_LIVE_SELECT stands in for it in the tests.
    # shellcheck disable=SC2086
    picks="$(${OSPREY_LIVE_SELECT:-../OspreyFlow_Core/.venv/bin/python -m scripts.live_select} $all --why)" \
      || { echo "The selection failed: nothing was run." >&2; exit 1; }
    files=()
    while IFS= read -r f; do [ -n "$f" ] && files+=("../OspreyFlow_Build/$f"); done <<< "$picks"
    [ "${#files[@]}" -gt 0 ] || { echo "The selection came out empty, which it never should (route rights is its floor): nothing was run." >&2; exit 1; }
    echo "live: ${#files[@]} live test files${all:+ (the full set)}." >&2
    run_on_host "$who" "$h" "$(ports_line "$s" "$who")" "$(basename "$(lock_of "$s")")" "$s" \
      sh -c 'cd ../OspreyFlow_Core && exec .venv/bin/pytest -c ../OspreyFlow_Build/pytest.ini -q -rfE -p no:randomly "$@"' sh "${files[@]}" "$@"
    ;;
  remote-log)
    who="${2:?usage: stack_lease.sh remote-log <lane>}"
    s="$(held_by "$who")"
    h=""; [ -n "$s" ] && h="$(host_of "$s")"
    [ -n "$h" ] || h="$(offline_host)"   # no remote stack held: the lane's offline run
    [ -n "$h" ] || { echo "No host to follow a run on." >&2; exit 1; }
    follow "$h" "${OSPREY_REMOTE_ROOT:-osprey-runs}/$who.meta"
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
    echo "usage: stack_lease.sh acquire <lane> \"<purpose>\" [a|b] | up <lane> | down <lane> | ports <lane> | remote <lane> -- <command…> | live <lane> [--all] | offline <lane> -- <command…> | remote-log <lane> | release <lane> | status" >&2
    exit 2
    ;;
esac
