#!/usr/bin/env bash
# One shared dev stack for the whole machine, used by one lane at a time
# (spec/06_DECISIONS.md ADR-142 decision 4; process/CLAUDE.md rule 14).
#
#   OspreyFlow_Build/scripts/stack_lease.sh acquire <lane> "<purpose>"   take the lease, or say who holds it
#   OspreyFlow_Build/scripts/stack_lease.sh release <lane>                give it back (the stack must be down)
#   OspreyFlow_Build/scripts/stack_lease.sh up <lane>                     start the throwaway stack (the holder only)
#   OspreyFlow_Build/scripts/stack_lease.sh down <lane>                   stop it again, before release
#   OspreyFlow_Build/scripts/stack_lease.sh status                        who holds it, since when, for what
#
# The leased stack is the throwaway one (SESSIONS_RUNBOOK.md §4), never `make dev-up`: dev.yaml publishes
# ArcadeDB on 2480, the owner's own deployment's port (8 November 2026, a lane started dev.yaml's containers
# on this script's own advice before the bind failed).
#
# The lock lives outside every worktree (~/.ospreyflow/stack.lease, or $OSPREY_LEASE_DIR), so every
# lane and the orchestrator see the same one. mkdir is atomic: two lanes acquiring at once cannot both
# succeed. Its red-then-green proof is OspreyFlow_Build/tests/test_stack_lease.py (rule 15).
set -euo pipefail

DIR="${OSPREY_LEASE_DIR:-$HOME/.ospreyflow}"
LOCK="$DIR/stack.lease"
# The throwaway stack's containers (SESSIONS_RUNBOOK.md §4; the ports tests/port_guard.py leases).
THROWAWAY="osprey-probe-arcadedb-new osprey-test-pg osprey-test-valkey-6379 osprey-test-objectstore"
mkdir -p "$DIR"

# The dev stack's compose project is named after the compose file's folder ("compose") in every
# worktree, so asking from any worktree sees the one shared stack; the lanes' throwaway test stack is
# checked too. Prints "up" or "down"; if docker
# cannot answer, it says so and fails, so a release is refused rather than let through blind.
stack_state() {
  local root core out
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
  # The throwaway test stack the lanes run their live tests on (FDE_HANDOVER.md: osprey-test-* and
  # osprey-probe-*, on the ports tests/port_guard.py pins), which is not dev.yaml's.
  local more
  if ! more="$(docker ps -q --filter 'name=^osprey-(test|probe)-' 2>&1)"; then
    echo "docker could not say whether the test stack is up: $more" >&2
    return 1
  fi
  if [ -n "$out" ] || [ -n "$more" ]; then echo up; else echo down; fi
}

cmd="${1:-status}"
case "$cmd" in
  acquire)
    who="${2:?usage: stack_lease.sh acquire <lane> \"<purpose>\"}"
    why="${3:-}"
    if mkdir "$LOCK" 2>/dev/null; then
      printf 'holder=%s\npurpose=%s\nsince=%s\nworktree=%s\n' \
        "$who" "$why" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(pwd)" > "$LOCK/info.tmp"
      mv "$LOCK/info.tmp" "$LOCK/info"
      echo "Lease taken by $who. Start the throwaway stack with: OspreyFlow_Build/scripts/stack_lease.sh up $who (the throwaway stack, not dev.yaml's, which binds the owner's 2480)"
    else
      echo "The dev stack is leased; wait, or ask the orchestrator:" >&2
      cat "$LOCK/info" >&2 2>/dev/null || echo "(no details recorded yet)" >&2
      exit 1
    fi
    ;;
  release)
    who="${2:?usage: stack_lease.sh release <lane>}"
    if [ ! -d "$LOCK" ]; then
      echo "No lease is held."
      exit 0
    fi
    holder="$(sed -n 's/^holder=//p' "$LOCK/info" 2>/dev/null || true)"
    if [ "$holder" != "$who" ]; then
      echo "The lease is held by ${holder:-nobody recorded}, not $who." >&2
      exit 1
    fi
    state="$(stack_state)" || { echo "Not released." >&2; exit 1; }
    if [ "$state" = up ]; then
      echo "The dev stack is still up. Run (cd OspreyFlow_Core && make dev-down) first." >&2
      exit 1
    fi
    rm -rf "$LOCK"
    echo "Lease released by $who."
    ;;
  up|down)
    who="${2:?usage: stack_lease.sh up|down <lane>}"
    holder="$(sed -n 's/^holder=//p' "$LOCK/info" 2>/dev/null || true)"
    if [ "$holder" != "$who" ]; then
      echo "The lease is held by ${holder:-nobody}, not $who: take it first." >&2
      exit 1
    fi
    if [ "$cmd" = up ]; then verb=start; else verb=stop; fi
    docker "$verb" $THROWAWAY >/dev/null || { echo "docker could not $verb the throwaway stack." >&2; exit 1; }
    echo "Throwaway stack ${cmd} for $who: $THROWAWAY"
    ;;
  status)
    if [ -d "$LOCK" ]; then cat "$LOCK/info" 2>/dev/null || echo "held (no details recorded yet)"; else echo "free"; fi
    ;;
  *)
    echo "usage: stack_lease.sh acquire <lane> \"<purpose>\" | up <lane> | down <lane> | release <lane> | status" >&2
    exit 2
    ;;
esac
