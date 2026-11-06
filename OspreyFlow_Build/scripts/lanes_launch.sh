#!/usr/bin/env bash
# The orchestrator's launcher for the lanes (spec/06_DECISIONS.md ADR-142 decision 10).
#
#   lanes_launch.sh setup <lane>             make the lane's worktree and its environment, if not there
#   lanes_launch.sh open <lane> [model]      open a Terminal window in the worktree with Claude Code
#                                            started on Prompt L and the lane's brief (default model: opus)
#   lanes_launch.sh resume <lane> [model]    the same, on Prompt R (a lane whose session ended)
#   lanes_launch.sh headless <lane> [model]  run the lane unattended, claude -p: the docs lane only, kept
#                                            for queue mode (ADR-142 open question 1); since the owner's
#                                            step 0 answer to P7 the docs lane opens with `open docs`
#   lanes_launch.sh alive <lane>             is a Claude Code session running in that worktree?
#
# Run from the repository root (the orchestrator's checkout, on main). The prompts are the files
# OspreyFlow_Build/process/lanes/PROMPT_L.md and PROMPT_R.md, with <lane> replaced; the brief is
# OspreyFlow_Build/process/lanes/<lane>/BRIEF.md as committed on main. Never
# --dangerously-skip-permissions: a headless lane runs under its worktree's .claude/settings.local.json.
#
# Claude Code is started as the orchestrator's own session was: the `claude` on PATH, by its full path,
# under the same CLAUDE_CONFIG_DIR (on 6 November 2026 no `claude-ayan` was defined in the owner's
# shell; ~/.claude-ayan is the config directory). OSPREY_CLAUDE_CMD and OSPREY_CLAUDE_CONFIG_DIR change
# them. Its red-then-green proof is OspreyFlow_Build/tests/test_lanes_launch.py (rule 15).
set -euo pipefail

CLAUDE_CMD="${OSPREY_CLAUDE_CMD:-$(command -v claude || echo claude)}"
CLAUDE_DIR="${OSPREY_CLAUDE_CONFIG_DIR:-${CLAUDE_CONFIG_DIR:-$HOME/.claude-ayan}}"

ROOT="$(git rev-parse --show-toplevel)"
WT="${OSPREY_WORKTREES:-$HOME/dev/osprey-wt}"
STATE="${OSPREY_LANES_DIR:-$HOME/.ospreyflow/lanes}"
LANES_DIR="$ROOT/OspreyFlow_Build/process/lanes"
mkdir -p "$WT" "$STATE"

lane_ok() { case "$1" in studio|glass|case|docs) ;; *) echo "Unknown lane '$1' (studio, glass, case, docs)." >&2; exit 2;; esac; }

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

prompt_for() {
  local lane="$1" which="$2" p b
  p="$(sed "s/<lane>/$lane/g" "$LANES_DIR/PROMPT_$which.md")"
  b="$(cat "$LANES_DIR/$lane/BRIEF.md" 2>/dev/null || echo "(no brief on main yet)")"
  printf '%s\n\n--- Your brief (OspreyFlow_Build/process/lanes/%s/BRIEF.md on main) ---\n\n%s\n' "$p" "$lane" "$b"
}

open_tab() {
  local lane="$1" which="$2" model="${3:-opus}" dir="$WT/$1" start="$STATE/$1.start.sh" pf="$STATE/$1.prompt.md"
  [ -d "$dir" ] || { echo "No worktree for $lane: run setup first." >&2; exit 1; }
  if alive "$lane" >/dev/null; then echo "A Claude Code session is already running in $dir: not opening another (rule 14)." >&2; exit 1; fi
  prompt_for "$lane" "$which" > "$pf"
  # Sourced by the new window's own interactive shell.
  cat > "$start" <<EOF
cd "$dir"
printf '\\033]0;OspreyFlow · %s\\007' "$lane"
export CLAUDE_CONFIG_DIR="$CLAUDE_DIR"
$CLAUDE_CMD --model "$model" "\$(cat "$pf")"
EOF
  osascript -e "tell application \"Terminal\" to do script \"source '$start'\"" -e 'tell application "Terminal" to activate' >/dev/null
  "$ROOT/OspreyFlow_Build/scripts/lanes_heartbeat.sh" beat "$lane" planning "session opened by the orchestrator ($which)" >/dev/null
  echo "Opened $lane in a new Terminal window ($model). Approvals inside it are the owner's."
}

headless() {
  local lane="$1" model="${2:-sonnet}" dir="$WT/$1" pf="$STATE/$1.prompt.md"
  [ "$lane" = "docs" ] || { echo "Headless runs are for the docs lane only (ADR-142 decision 10)." >&2; exit 1; }
  if alive "$lane" >/dev/null; then echo "A session is already running in $dir." >&2; exit 1; fi
  prompt_for "$lane" L > "$pf"
  ( cd "$dir" && CLAUDE_CONFIG_DIR="$CLAUDE_DIR" PF="$pf" M="$model" nohup zsh -ic "$CLAUDE_CMD"' -p --model "$M" "$(cat "$PF")"' > "$STATE/$lane.headless.out" 2>&1 & )
  echo "Started $lane headless ($model); output in $STATE/$lane.headless.out."
}

# A Claude Code process whose working directory is the lane's worktree or inside it (not a sibling
# folder that shares its name as a prefix). A lane's session is never an ancestor of the caller, so
# macOS pgrep's leaving out its own ancestors does not matter here.
alive() {
  local dir="$WT/$1" pids
  pids="$(pgrep -f '(^|/)claude(-ayan)?( |$)' 2>/dev/null | paste -sd, - || true)"
  [ -n "$pids" ] || { echo "no"; return 1; }
  if lsof -a -p "$pids" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' \
      | awk -v d="$dir" '$0 == d || index($0, d "/") == 1 { found = 1 } END { exit !found }'; then
    echo "yes"; return 0
  fi
  echo "no"; return 1
}

cmd="${1:-}"; lane="${2:-}"
case "$cmd" in
  setup) lane_ok "$lane"; setup "$lane" ;;
  open) lane_ok "$lane"; open_tab "$lane" L "${3:-opus}" ;;
  resume) lane_ok "$lane"; open_tab "$lane" R "${3:-opus}" ;;
  headless) lane_ok "$lane"; headless "$lane" "${3:-sonnet}" ;;
  alive) lane_ok "$lane"; alive "$lane" ;;
  *) echo "usage: lanes_launch.sh setup|open|resume|headless|alive <lane> [model]" >&2; exit 2 ;;
esac
