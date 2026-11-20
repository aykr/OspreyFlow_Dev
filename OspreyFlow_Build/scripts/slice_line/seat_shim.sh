#!/bin/sh
# The seats' `claude` (F1, layer 3 of LINE_FAULTS_2026-11-18.md; README, "Where the guard runs from"). install.sh puts
# this file at ~/.ospreyflow/slice-line/bin/shim/claude (and claude-sol, claude-ayan), read-only and in the manifest;
# run_seat.py puts that folder first on every seat's PATH and starts each seat through it. It runs the real claude only
# for a one-time token run_seat.py has just written to the line's data folder (which no agent can write: the guard),
# and removes the token as it does, so the session it starts never holds one. Anything else, whatever the command's
# text (`claude`, `env claude`, `bash -c`, a name built in the shell), is refused here.
data="${OSPREY_SLICE_HOME:-$HOME/.ospreyflow/slice-line}"
real="${OSPREY_CLAUDE_BIN:-$HOME/.local/bin/claude}"
token="${OSPREY_LAUNCH_TOKEN:-}"
case "$token" in
  ""|*/*|.*) ;;
  *)
    if [ -f "$data/launch/$token" ] && rm "$data/launch/$token" 2>/dev/null; then
      unset OSPREY_LAUNCH_TOKEN
      exec "$real" "$@"
    fi
    ;;
esac
echo "Refused by the slice line's seat shim: a Claude Code session is started only by run_seat.py (no valid one-time launch token)." >&2
exit 126
