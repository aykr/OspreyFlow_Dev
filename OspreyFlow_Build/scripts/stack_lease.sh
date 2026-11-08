#!/usr/bin/env bash
# The lanes' throwaway test stacks, each used by one lane at a time (spec/06_DECISIONS.md ADR-142 decision 4
# and Amendment 3; process/CLAUDE.md rule 14). Two stacks, a and b, listed in scripts/lane_stacks.tsv.
#
#   OspreyFlow_Build/scripts/stack_lease.sh acquire <lane> "<purpose>" [a|b]   take a free stack (a first),
#                                                                          or the one named; or say who holds each
#   OspreyFlow_Build/scripts/stack_lease.sh release <lane>                give it back (its stack must be down)
#   OspreyFlow_Build/scripts/stack_lease.sh up <lane>                     start the holder's own stack
#   OspreyFlow_Build/scripts/stack_lease.sh down <lane>                   stop it again, before release
#   OspreyFlow_Build/scripts/stack_lease.sh ports <lane>                  the export line for the holder's stack
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
  if ! more="$(docker ps -q $filters 2>&1)"; then
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
      try="$want"
    else
      try="$STACKS"
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
    docker "$verb" "${these[@]}" >/dev/null || { echo "docker could not $verb test stack $s." >&2; exit 1; }
    echo "Test stack $s ${cmd} for $who: ${these[*]}"
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
      if [ -d "$lock" ]; then
        printf '%s: %s\n' "$s" "$(tr '\n' ' ' < "$lock/info" 2>/dev/null | sed 's/ $//' || echo "held (no details recorded yet)")"
      else
        echo "$s: free"
      fi
    done
    ;;
  *)
    echo "usage: stack_lease.sh acquire <lane> \"<purpose>\" [a|b] | up <lane> | down <lane> | ports <lane> | release <lane> | status" >&2
    exit 2
    ;;
esac
