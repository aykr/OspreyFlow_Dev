#!/usr/bin/env bash
# The orchestrator's launcher for the lanes (spec/06_DECISIONS.md ADR-142 decision 10, Amendment 1).
#
#   lanes_launch.sh setup <lane>                         make the lane's worktree and its environment, if not there
#   lanes_launch.sh open <lane> [model] [--account <a>]  open a Terminal window in the worktree with Claude Code
#                                                        started on Prompt L and the lane's brief (default model: opus)
#   lanes_launch.sh resume <lane> [model] [--account <a>] the same, on Prompt R (a lane whose session ended or
#                                                        was paused); HANDOFF.md, if there, is named first
#   lanes_launch.sh headless <lane> [model] [--account <a>] run the lane unattended, claude -p: the docs lane only
#   lanes_launch.sh orchestrator [--account <a>]         open the orchestrator's own window at the repository root
#   lanes_launch.sh pause <lane>                         ask the lane to stop at its next safe point (a nudge it acts on)
#   lanes_launch.sh pause <lane> --now                   the lane cannot answer: record its state from outside in
#                                                        HANDOFF.md, commit nothing, mark it paused (unclean)
#   lanes_launch.sh pause-done <lane> "<step>"           run BY THE LANE at its safe point: releases the lease if it
#                                                        holds it, commits `wip(<lane>): paused at <step>` with its
#                                                        HANDOFF.md, beats paused
#   lanes_launch.sh switch <lane> --account <a>          pause, wait for the session to end, resume on that account
#   lanes_launch.sh fallback-switch <lane>               watch mode's: switch once to the owner's `fallback` account;
#                                                        refused with no fallback line (Amendment 1 decision 6)
#   lanes_launch.sh merge-ok <lane>                      the merge gate: refuses a branch holding a `wip(` commit
#   lanes_launch.sh alive <lane>                         is a Claude Code session running in that worktree?
#
# Accounts (Amendment 1 decisions 1-3): an account is a Claude Code config directory the owner signed in
# by hand. ~/.ospreyflow/accounts.conf ($OSPREY_ACCOUNTS_FILE) names them:
#   account ayan   = ~/.claude-ayan
#   orchestrator   = ayan
#   lane case      = client
#   fallback case  = ayan          (written only by the owner)
# A lane with no line uses the orchestrator's account; with no file, every session uses the default
# config directory below. This script names an account and its directory, and never reads, copies or
# prints anything inside one.
#
# Run from the repository root (the orchestrator's checkout, on main). The prompts are the files
# OspreyFlow_Build/process/lanes/PROMPT_L.md and PROMPT_R.md, with <lane> replaced; the brief is
# OspreyFlow_Build/process/lanes/<lane>/BRIEF.md as committed on main. Never
# --dangerously-skip-permissions: a headless lane runs under its worktree's .claude/settings.local.json.
#
# Claude Code is started by its full path (on 6 November 2026 no `claude-ayan` was defined in the
# owner's shell; ~/.claude-ayan is the config directory). OSPREY_CLAUDE_CMD and OSPREY_CLAUDE_CONFIG_DIR
# change them. Its red-then-green proof is OspreyFlow_Build/tests/test_lanes_launch.py (rule 15).
set -euo pipefail

CLAUDE_CMD="${OSPREY_CLAUDE_CMD:-$(command -v claude || echo claude)}"
CLAUDE_DIR="${OSPREY_CLAUDE_CONFIG_DIR:-${CLAUDE_CONFIG_DIR:-$HOME/.claude-ayan}}"
ACCOUNTS="${OSPREY_ACCOUNTS_FILE:-$HOME/.ospreyflow/accounts.conf}"
SWITCH_WAIT="${OSPREY_SWITCH_WAIT:-1800}"     # seconds switch waits for a paused session to end
SWITCH_POLL="${OSPREY_SWITCH_POLL:-10}"

ROOT="$(git rev-parse --show-toplevel)"
WT="${OSPREY_WORKTREES:-$HOME/dev/osprey-wt}"
STATE="${OSPREY_LANES_DIR:-$HOME/.ospreyflow/lanes}"
LANES_DIR="$ROOT/OspreyFlow_Build/process/lanes"
HEARTBEAT="$ROOT/OspreyFlow_Build/scripts/lanes_heartbeat.sh"
LEASE_SH="$ROOT/OspreyFlow_Build/scripts/stack_lease.sh"
LEASE_DIR="${OSPREY_LEASE_DIR:-$HOME/.ospreyflow}"
# Each lane's Playwright port slot (T2, lane_ports.tsv), by its exact row; "unlisted-<lane>" otherwise, which a
# Playwright run refuses in words (OspreyFlow_Core/apps/lanePorts.ts).
PORTS="$(cd "$(dirname "$0")" && pwd)/lane_ports.tsv"
ports_slot() { awk -F'\t' -v l="$1" '!/^#/ && $1 == l { print $2; found = 1; exit } END { if (!found) print "unlisted-" l }' "$PORTS" 2>/dev/null || echo "unlisted-$1"; }
mkdir -p "$WT" "$STATE"

# The lanes (ADR-142 Amendment 3: glass split into admin and rules on 8 November 2026, platform added).
LANE_NAMES="studio case admin rules platform docs"
# shellcheck source=/dev/null
[ -f "$(dirname "$0")/lanes.conf" ] && . "$(dirname "$0")/lanes.conf"
lane_ok() {
  case " $LANE_NAMES " in *" $1 "*) ;; *) echo "Unknown lane '$1' ($(echo "$LANE_NAMES" | sed 's/ /, /g'))." >&2; exit 2;; esac
}
# The test stack a lane holds (its lock's info names it), or nothing: stack.lease is stack a's, stack-<s>.lease another's.
stack_held_by() {
  local info
  for info in "$LEASE_DIR"/stack.lease/info "$LEASE_DIR"/stack-*.lease/info; do
    [ -f "$info" ] || continue
    if [ "$(sed -n 's/^holder=//p' "$info")" = "$1" ]; then
      case "$info" in */stack.lease/info) echo a ;; *) basename "$(dirname "$info")" .lease | sed 's/^stack-//' ;; esac
      return 0
    fi
  done
}

# --- accounts ---------------------------------------------------------------------------------------

# The value of a "<key> = <value>" line in accounts.conf (comments and spaces stripped), or nothing.
conf() {
  [ -f "$ACCOUNTS" ] || return 0
  awk -v key="$1" '{ sub(/#.*/, ""); n = index($0, "="); if (!n) next
      k = substr($0, 1, n - 1); v = substr($0, n + 1)
      gsub(/^[ \t]+|[ \t]+$/, "", k); gsub(/^[ \t]+|[ \t]+$/, "", v); gsub(/[ \t]+/, " ", k)
      if (k == key) { print v; exit } }' "$ACCOUNTS"
}

# ACCOUNT_NAME and ACCOUNT_DIR for a lane (or "orchestrator") and an optional override; exits refusing
# an account accounts.conf does not name, or whose directory is not there, before anything starts.
resolve_account() {
  local who="$1" want="${2:-}" dir
  if [ -z "$want" ]; then
    if [ "$who" = orchestrator ]; then want="$(conf orchestrator)"; else want="$(conf "lane $who")"; fi
    [ -n "$want" ] || want="$(conf orchestrator)"
  fi
  if [ -z "$want" ]; then ACCOUNT_NAME="default"; ACCOUNT_DIR="$CLAUDE_DIR"; return 0; fi
  dir="$(conf "account $want")"
  if [ -z "$dir" ]; then
    echo "Refused: no account '$want' in $ACCOUNTS (an 'account $want = <directory>' line). Nothing was started." >&2
    exit 1
  fi
  case "$dir" in "~"|"~/"*) dir="$HOME${dir#\~}" ;; esac
  if [ ! -d "$dir" ]; then
    echo "Refused: account '$want' names $dir, which does not exist. Sign it in first: CLAUDE_CONFIG_DIR=$dir claude, then /login. Nothing was started." >&2
    exit 1
  fi
  ACCOUNT_NAME="$want"; ACCOUNT_DIR="$dir"
}

# --- setup and sessions -----------------------------------------------------------------------------

setup() {
  local lane="$1" dir="$WT/$1"
  if [ ! -d "$dir" ]; then
    git -C "$ROOT" worktree add "$dir" -b "lane/$lane" main
  fi
  if [ -f "$ROOT/.claude/settings.local.json" ] && [ ! -f "$dir/.claude/settings.local.json" ]; then
    mkdir -p "$dir/.claude"; cp "$ROOT/.claude/settings.local.json" "$dir/.claude/"
  fi
  if [ -f "$ROOT/OspreyFlow_Core/osprey.yaml" ]; then
    cp "$ROOT/OspreyFlow_Core/osprey.yaml" "$dir/OspreyFlow_Core/osprey.yaml"
    git -C "$dir" update-index --skip-worktree OspreyFlow_Core/osprey.yaml
  fi
  if [ -z "${OSPREY_SETUP_SKIP_ENV:-}" ]; then   # the test's: no installs
    ( cd "$dir/OspreyFlow_Core" && uv sync --frozen && npm ci )
    ( cd "$dir" && graphify update . ) || echo "graphify update failed in $dir: the hook guard may refuse searches until it is run." >&2
  fi
  echo "Worktree ready: $dir (branch lane/$lane)."
}

handoff_of() { echo "$WT/$1/OspreyFlow_Build/process/lanes/$1/HANDOFF.md"; }

prompt_for() {
  local lane="$1" which="$2" p b
  p="$(sed "s/<lane>/$lane/g" "$LANES_DIR/PROMPT_$which.md")"
  b="$(cat "$LANES_DIR/$lane/BRIEF.md" 2>/dev/null || echo "(no brief on main yet)")"
  if [ "$which" = R ] && [ -f "$(handoff_of "$lane")" ]; then
    printf 'Before anything else, read OspreyFlow_Build/process/lanes/%s/HANDOFF.md: this lane was paused, and it is the only memory carried over from the previous session.\n\n' "$lane"
  fi
  printf '%s\n\n--- Your brief (OspreyFlow_Build/process/lanes/%s/BRIEF.md on main) ---\n\n%s\n' "$p" "$lane" "$b"
}

open_tab() {
  local lane="$1" which="$2" model="$3" want="$4" dir="$WT/$1" start="$STATE/$1.start.sh" pf="$STATE/$1.prompt.md"
  [ -d "$dir" ] || { echo "No worktree for $lane: run setup first." >&2; exit 1; }
  resolve_account "$lane" "$want"
  if alive "$lane" >/dev/null; then echo "A Claude Code session is already running in $dir: not opening another (rule 14)." >&2; exit 1; fi
  prompt_for "$lane" "$which" > "$pf"
  # Sourced by the new window's own interactive shell.
  cat > "$start" <<EOF
cd "$dir"
printf '\\033]0;OspreyFlow · %s · account %s\\007' "$lane" "$ACCOUNT_NAME"
echo "OspreyFlow $lane lane on account $ACCOUNT_NAME."
export CLAUDE_CONFIG_DIR="$ACCOUNT_DIR"
export OSPREY_LANE="$lane"
export OSPREY_PORTS_SLOT="$(ports_slot "$lane")"
$CLAUDE_CMD --model "$model" "\$(cat "$pf")"
EOF
  osascript -e "tell application \"Terminal\" to do script \"source '$start'\"" -e 'tell application "Terminal" to activate' >/dev/null
  echo "$ACCOUNT_NAME" > "$STATE/$lane.account"
  rm -f "$STATE/$lane.pause"
  OSPREY_BEAT_KEEP_NUDGE=1 "$HEARTBEAT" beat "$lane" planning "session opened by the orchestrator ($which, account $ACCOUNT_NAME)" >/dev/null
  echo "Opened $lane in a new Terminal window ($model, account $ACCOUNT_NAME). Approvals inside it are the owner's."
}

open_orchestrator() {
  local want="$1" start="$STATE/orchestrator.start.sh"
  resolve_account orchestrator "$want"
  cat > "$start" <<EOF
cd "$ROOT"
printf '\\033]0;OspreyFlow · orchestrator · account %s\\007' "$ACCOUNT_NAME"
echo "OspreyFlow orchestrator on account $ACCOUNT_NAME."
export CLAUDE_CONFIG_DIR="$ACCOUNT_DIR"
$CLAUDE_CMD
EOF
  osascript -e "tell application \"Terminal\" to do script \"source '$start'\"" -e 'tell application "Terminal" to activate' >/dev/null
  echo "Opened the orchestrator's window (account $ACCOUNT_NAME)."
}

headless() {
  local lane="$1" model="$2" want="$3" dir="$WT/$1" pf="$STATE/$1.prompt.md"
  [ "$lane" = "docs" ] || { echo "Headless runs are for the docs lane only (ADR-142 decision 10)." >&2; exit 1; }
  resolve_account "$lane" "$want"
  if alive "$lane" >/dev/null; then echo "A session is already running in $dir." >&2; exit 1; fi
  prompt_for "$lane" L > "$pf"
  echo "$ACCOUNT_NAME" > "$STATE/$lane.account"
  ( cd "$dir" && CLAUDE_CONFIG_DIR="$ACCOUNT_DIR" OSPREY_LANE="$lane" OSPREY_PORTS_SLOT="$(ports_slot "$lane")" PF="$pf" M="$model" nohup zsh -ic "$CLAUDE_CMD"' -p --model "$M" "$(cat "$PF")"' > "$STATE/$lane.headless.out" 2>&1 & )
  echo "Started $lane headless ($model, account $ACCOUNT_NAME); output in $STATE/$lane.headless.out."
}

# A Claude Code process whose working directory is the lane's worktree or inside it (not a sibling
# folder that shares its name as a prefix). A lane's session is never an ancestor of the caller, so
# macOS pgrep's leaving out its own ancestors does not matter here.
alive() {
  local dir="$WT/$1" pids
  pids="$(pgrep -f '(^|/)claude(-ayan)?( |$)' 2>/dev/null | paste -sd, - || true)"
  [ -n "$pids" ] || { echo "no"; return 1; }
  # lsof exits 1 when any pid in the list has gone (a session ending between pgrep and lsof); under pipefail
  # that hid every live session in the list (12 November 2026), so its status is not the answer, awk's is.
  if { lsof -a -p "$pids" -d cwd -Fn 2>/dev/null || true; } | sed -n 's/^n//p' \
      | awk -v d="$dir" '$0 == d || index($0, d "/") == 1 { found = 1 } END { exit !found }'; then
    echo "yes"; return 0
  fi
  echo "no"; return 1
}

# --- pausing and switching (Amendment 1 decisions 4-6) -----------------------------------------------

pause() {
  local lane="$1" now="${2:-}" dir="$WT/$1"
  [ -d "$dir" ] || { echo "No worktree for $lane." >&2; exit 1; }
  if [ "$now" = "--now" ]; then
    local h head files holder
    h="$(handoff_of "$lane")"; head="$(git -C "$dir" log -1 --format='%h %s' 2>/dev/null || echo '?')"
    files="$(git -C "$dir" status --short 2>/dev/null || true)"
    holder="$(stack_held_by "$lane")"
    mkdir -p "$(dirname "$h")"
    {
      echo "# $lane · paused (unclean) from outside, $(date -u +%Y-%m-%dT%H:%M:%SZ)"
      echo
      echo "The lane could not answer, so the orchestrator recorded this; nothing was committed for it."
      echo
      echo "- Branch head: $head"
      [ -n "$holder" ] && echo "- It still holds the lease on test stack $holder: bring that stack down (stack_lease.sh down $lane) and release it first."
      echo "- Uncommitted files in the worktree (reconcile them before anything else):"
      if [ -n "$files" ]; then printf '%s\n' "$files" | sed -n '1,20s/^/    /p'; else echo "    (none)"; fi
      echo "- Done, next and open questions: unknown; read REPORT.md and git log main..lane/$lane."
    } > "$h"
    echo "unclean $(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$STATE/$lane.pause"
    OSPREY_BEAT_KEEP_NUDGE=1 "$HEARTBEAT" beat "$lane" paused "paused (unclean) from outside; HANDOFF.md written, nothing committed" >/dev/null
    echo "$lane marked paused (unclean). $h records its head and uncommitted files; nothing was committed."
    return 0
  fi
  echo "requested $(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$STATE/$lane.pause"
  "$HEARTBEAT" nudge "$lane" "PAUSE REQUESTED (ADR-142 Amendment 1). Stop at your next safe point: never mid-tool. Bring the stack down if you have it up. Write OspreyFlow_Build/process/lanes/$lane/HANDOFF.md (at most 30 lines: step and part; last commit; done, next, what was running; open questions; what the next session must not redo). Then run OspreyFlow_Build/scripts/lanes_launch.sh pause-done $lane \"<step>\" and end your session." >/dev/null
  echo "Pause requested for $lane; it acts on it at its next heartbeat."
}

pause_done() {
  local lane="$1" step="${2:?usage: pause-done <lane> \"<step>\"}" dir="$WT/$1" h holder n
  h="$(handoff_of "$lane")"
  [ -f "$h" ] || { echo "Refused: write $h first (at most 30 lines)." >&2; exit 1; }
  n=$(wc -l < "$h" | tr -d ' ')
  [ "$n" -le 30 ] || { echo "Refused: $h has $n lines; at most 30." >&2; exit 1; }
  holder="$(stack_held_by "$lane")"
  if [ -n "$holder" ]; then
    ( cd "$dir" && "$LEASE_SH" release "$lane" ) || { echo "Refused: the lease could not be released, so the lane is not paused." >&2; exit 1; }
  fi
  git -C "$dir" add -A
  git -C "$dir" commit -q -m "wip($lane): paused at $step" -m "Paused under ADR-142 Amendment 1; HANDOFF.md says where it stands. Never merged: rewrite into proper commits after resuming."
  echo "clean $(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$STATE/$lane.pause"
  ( cd "$dir" && OSPREY_BEAT_KEEP_NUDGE=1 "$HEARTBEAT" beat "$lane" paused "paused at $step" >/dev/null )
  echo "$lane paused at $step: $(git -C "$dir" log -1 --format=%h). End this session now."
}

paused_state() { sed -n 's/^state=//p' "$STATE/$1.beat" 2>/dev/null | sed -n 1p; }

switch() {
  local lane="$1" want="$2" waited=0
  [ -n "$want" ] || { echo "usage: lanes_launch.sh switch <lane> --account <name>" >&2; exit 2; }
  resolve_account "$lane" "$want"
  if [ "$(paused_state "$lane")" != paused ]; then pause "$lane"; fi
  while [ "$(paused_state "$lane")" != paused ] || alive "$lane" >/dev/null; do
    if [ "$waited" -ge "$SWITCH_WAIT" ]; then
      echo "Not switched: $lane has not paused and ended its session after ${SWITCH_WAIT}s." >&2; exit 1
    fi
    sleep "$SWITCH_POLL"; waited=$((waited + SWITCH_POLL))
  done
  open_tab "$lane" R "opus" "$want"
}

fallback_switch() {
  local lane="$1" fb used="$STATE/$1.fallback-used"
  fb="$(conf "fallback $lane")"
  if [ -z "$fb" ]; then
    echo "No fallback line for $lane in $ACCOUNTS: not switched (only the owner switches it)." >&2
    return 1
  fi
  if [ -f "$used" ]; then echo "$lane already switched to its fallback once: not again." >&2; return 1; fi
  resolve_account "$lane" "$fb"
  if [ "$(paused_state "$lane")" != paused ]; then pause "$lane" --now >/dev/null; fi
  if alive "$lane" >/dev/null; then
    echo "$lane is paused for its fallback ($fb), but its window is still open: close it and the next pass resumes it." >&2
    return 1
  fi
  touch "$used"
  open_tab "$lane" R "opus" "$fb"
  local line="- $(date -u +%Y-%m-%dT%H:%M:%SZ) $lane switched to its fallback account $fb at its usage limit (ADR-142 Amendment 1 decision 6)."
  for f in "$LANES_DIR/PUSH_LOG.md" "$LANES_DIR/MORNING.md"; do [ -f "$f" ] && echo "$line" >> "$f"; done
  return 0
}

merge_ok() {
  local lane="$1" wip
  wip="$(git -C "$ROOT" log --format='%h %s' "main..lane/$lane" | grep -E '^[0-9a-f]+ wip\(' || true)"
  if [ -n "$wip" ]; then
    echo "Refused: lane/$lane holds a wip( commit, never merged; the lane rewrites it into proper commits first:" >&2
    printf '%s\n' "$wip" | sed 's/^/  /' >&2
    exit 1
  fi
  echo "lane/$lane holds no wip( commit."
}

# --- arguments --------------------------------------------------------------------------------------

cmd="${1:-}"; lane="${2:-}"
shift $(( $# >= 2 ? 2 : $# ))
model=""; account=""; now=""; rest=()
while [ $# -gt 0 ]; do
  case "$1" in
    --account) account="${2:?--account needs a name}"; shift 2 ;;
    --account=*) account="${1#--account=}"; shift ;;
    --now) now="--now"; shift ;;
    *) rest+=("$1"); shift ;;
  esac
done
[ "${#rest[@]}" -gt 0 ] && model="${rest[0]}"
case "$cmd" in
  setup) lane_ok "$lane"; setup "$lane" ;;
  open) lane_ok "$lane"; open_tab "$lane" L "${model:-opus}" "$account" ;;
  resume) lane_ok "$lane"; open_tab "$lane" R "${model:-opus}" "$account" ;;
  headless) lane_ok "$lane"; headless "$lane" "${model:-sonnet}" "$account" ;;
  orchestrator) [ "$lane" = "--account" ] && { account="$model"; }; [[ "$lane" == --account=* ]] && account="${lane#--account=}"; open_orchestrator "$account" ;;
  pause) lane_ok "$lane"; pause "$lane" "$now" ;;
  pause-done) lane_ok "$lane"; pause_done "$lane" "${rest[0]:-}" ;;
  switch) lane_ok "$lane"; switch "$lane" "$account" ;;
  fallback-switch) lane_ok "$lane"; fallback_switch "$lane" ;;
  merge-ok) lane_ok "$lane"; merge_ok "$lane" ;;
  alive) lane_ok "$lane"; alive "$lane" ;;
  *) echo "usage: lanes_launch.sh setup|open|resume|headless|pause|pause-done|switch|fallback-switch|merge-ok|alive <lane> [model] [--account <name>] [--now] | orchestrator [--account <name>]" >&2; exit 2 ;;
esac
