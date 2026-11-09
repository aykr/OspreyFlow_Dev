#!/usr/bin/env bash
# The lanes' throwaway test stacks, each used by one lane at a time (spec/06_DECISIONS.md ADR-142 decision 4
# and Amendment 3; process/CLAUDE.md rule 14). Stack a on this machine and b to e on the owner's test server
# (b and c moved there on 9 November 2026), listed in scripts/lane_stacks.tsv; scripts/lane_stack_hosts.tsv names a remote stack's host.
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
  [ "$1" = a ] || printf ' CLICKHOUSE_HTTP_PORT=59994'
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
    top="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "Not inside a git worktree: run remote from your lane's checkout." >&2; exit 1; }
    rel="$(git rev-parse --show-prefix)"
    rroot="${OSPREY_REMOTE_ROOT:-osprey-runs}/$who"
    list="$(mktemp)"; trap 'rm -f "$list"' EXIT
    # What git tracks or would track, less the local osprey.yaml (sent as committed, below) and paths gone from disk.
    ( cd "$top" && git ls-files -co --exclude-standard -z | tr '\0' '\n' \
        | grep -v -x 'OspreyFlow_Core/osprey.yaml' | while IFS= read -r f; do [ -e "$f" ] && printf '%s\n' "$f"; done ) > "$list"
    ssh -o BatchMode=yes "$h" "mkdir -p $rroot" || { echo "Could not reach $h." >&2; exit 1; }
    rsync -a --files-from="$list" "$top/" "$h:$rroot/" || { echo "Copying the worktree to $h failed." >&2; exit 1; }
    # Remove what the worktree no longer has (never the venv or caches), then the committed osprey.yaml.
    ssh -o BatchMode=yes "$h" "cd $rroot && python3 -c 'import os,sys
keep=set(sys.stdin.read().splitlines()); keep.add(\"OspreyFlow_Core/osprey.yaml\")
skip=(\".venv\",\"node_modules\",\".pytest_cache\",\"__pycache__\",\".osprey-lease\",\".git\")
for d,ds,fs in os.walk(\".\"):
  ds[:]=[x for x in ds if x not in skip]
  for f in fs:
    p=os.path.relpath(os.path.join(d,f))
    if p not in keep: os.remove(p)'" < "$list" || { echo "Pruning the copy on $h failed." >&2; exit 1; }
    ( cd "$top" && git show HEAD:OspreyFlow_Core/osprey.yaml ) | ssh -o BatchMode=yes "$h" "cat > $rroot/OspreyFlow_Core/osprey.yaml"
    lockname="$(basename "$(lock_of "$s")")"
    ssh -o BatchMode=yes "$h" "rm -rf $rroot/.osprey-lease && mkdir -p $rroot/.osprey-lease/$lockname && cat > $rroot/.osprey-lease/$lockname/info" < "$(lock_of "$s")/info"
    ssh -o BatchMode=yes "$h" "cd $rroot/OspreyFlow_Core && ~/.local/bin/uv sync --frozen -q" || { echo "uv sync on $h failed." >&2; exit 1; }
    cmdline="$(printf '%q ' "$@")"
    echo "Running on $h (stack $s, $rroot/$rel): $*" >&2
    # shellcheck disable=SC2029
    ssh -o BatchMode=yes "$h" "cd $rroot/$rel && export $(ports_line "$s" "$who") OSPREY_LEASE_DIR=\$HOME/$rroot/.osprey-lease PATH=\$HOME/.local/bin:\$PATH && $cmdline"
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
    echo "usage: stack_lease.sh acquire <lane> \"<purpose>\" [a|b] | up <lane> | down <lane> | ports <lane> | remote <lane> -- <command…> | release <lane> | status" >&2
    exit 2
    ;;
esac
