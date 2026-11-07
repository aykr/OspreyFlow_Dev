#!/usr/bin/env bash
# The lanes' heartbeat and the owner's monitor (spec/06_DECISIONS.md ADR-142 decision 9).
#
#   lanes_heartbeat.sh beat <lane> <state> "<note>"   a lane records where it is
#        state: planning | working | testing | waiting-for-owner | blocked | ready-to-merge | idle
#   lanes_heartbeat.sh nudge <lane> "<message>"     the orchestrator leaves a lane a message, shown
#                                                     to it at its next beat (a session it cannot type into)
#   lanes_heartbeat.sh show                           one table: every lane, the lease, what needs you
#   lanes_heartbeat.sh watch [seconds]                show again every N seconds (default 300) and send a
#                                                     macOS notification when something newly needs you
#
# Heartbeats live outside every worktree ($OSPREY_LANES_DIR, default ~/.ospreyflow/lanes), so every
# session and the monitor see the same ones; each beat appends to <lane>.log and rewrites <lane>.beat.
# Each "Needs you" line names a fact that does not change from one pass to the next (since when, not
# for how long), so watch notifies once per new line, not on every pass. Its red-then-green proof is
# OspreyFlow_Build/tests/test_lanes_heartbeat.py (rule 15).
set -euo pipefail

DIR="${OSPREY_LANES_DIR:-$HOME/.ospreyflow/lanes}"
LEASE="${OSPREY_LEASE_DIR:-$HOME/.ospreyflow}/stack.lease"
WT="${OSPREY_WORKTREES:-$HOME/dev/osprey-wt}"
LANES="${OSPREY_LANES:-studio glass case docs}"
QUIET_MIN="${OSPREY_QUIET_MINUTES:-45}"       # a working lane silent this long is flagged
LEASE_MAX_MIN="${OSPREY_LEASE_MAX_MINUTES:-120}"
BEHIND_MAX="${OSPREY_BEHIND_MAX:-5}"
STATES="planning working testing waiting-for-owner blocked ready-to-merge idle"
# The step table the orchestrator keeps on main (process/lanes/progress.tsv).
PROGRESS="${OSPREY_PROGRESS_FILE:-$(cd "$(dirname "$0")/.." && pwd)/process/lanes/progress.tsv}"
mkdir -p "$DIR"

now() { echo "${OSPREY_NOW:-$(date -u +%s)}"; }   # OSPREY_NOW: the test's clock
iso() { date -u +%Y-%m-%dT%H:%M:%SZ; }
# seconds since an ISO time (macOS date and GNU date both handled)
age_s() {
  local t="$1" e
  e=$(date -u -j -f '%Y-%m-%dT%H:%M:%SZ' "$t" +%s 2>/dev/null || date -u -d "$t" +%s 2>/dev/null || echo 0)
  echo $(( $(now) - e ))
}
mins() { echo $(( $1 / 60 )); }
field() { sed -n "s/^$1=//p" "$2" 2>/dev/null | head -1; }

beat() {
  local lane="${1:?usage: beat <lane> <state> \"<note>\"}" state="${2:?state}" note="${3:-}"
  case " $STATES " in *" $state "*) ;; *) echo "Unknown state '$state'. One of: $STATES" >&2; exit 2;; esac
  local head=""
  head=$(git rev-parse --short HEAD 2>/dev/null || true)
  printf 'lane=%s\nstate=%s\nnote=%s\nat=%s\nhead=%s\n' "$lane" "$state" "$note" "$(iso)" "$head" > "$DIR/$lane.beat.tmp"
  mv "$DIR/$lane.beat.tmp" "$DIR/$lane.beat"
  printf '%s\t%s\t%s\t%s\n' "$(iso)" "$state" "$head" "$note" >> "$DIR/$lane.log"
  echo "Heartbeat: $lane $state."
  # OSPREY_BEAT_KEEP_NUDGE: a beat made on the lane's behalf (the launcher's, at open) leaves the
  # nudge for the lane's own first beat to show.
  if [ -z "${OSPREY_BEAT_KEEP_NUDGE:-}" ] && [ -s "$DIR/$lane.nudge" ]; then
    echo; echo "MESSAGE FROM THE ORCHESTRATOR (act on it before going on):"; cat "$DIR/$lane.nudge"
    printf '%s\tnudge read\t%s\t\n' "$(iso)" "$head" >> "$DIR/$lane.log"
    rm -f "$DIR/$lane.nudge"
  fi
}

nudge() {
  local lane="${1:?usage: nudge <lane> \"<message>\"}" msg="${2:?message}"
  printf '[%s] %s\n' "$(iso)" "$msg" >> "$DIR/$lane.nudge"
  echo "Nudge left for $lane; it sees it at its next heartbeat."
}

# Claude Code sessions on this machine. macOS pgrep leaves out its own ancestors unless given -a, so
# a monitor started from inside a session would not count that session.
sessions() {
  local a=""
  [ "$(uname)" = Darwin ] && a="-a"
  # shellcheck disable=SC2086
  pgrep $a -f '(^|/)claude(-ayan)?( |$)' 2>/dev/null | wc -l | tr -d ' '
}

# A lane's progress from the step table: line 1 "done/total bar", then "STEP in review: title" lines.
progress_of() {
  [ -f "$PROGRESS" ] || return 0
  awk -F'\t' -v lane="$1" '!/^#/ && NF>=4 && $1==lane {
      total++; if ($4=="done") done++
      bar = bar ($4=="done" ? "■" : ($4=="todo" ? "□" : "◧"))
      if ($4=="review") hand[++h] = $2 " in review: " $5
      if ($4=="building") hand[++h] = $2 " building: " $5
    }
    END { if (total) { printf "%d/%d %s\n", done+0, total, bar; for (i=1;i<=h;i++) print hand[i] } }' "$PROGRESS"
}

# Prints one tree per lane; writes the lines that need the owner to $DIR/.needs
show() {
  local needs="$DIR/.needs.tmp"; : > "$needs"
  for lane in $LANES; do
    local f="$DIR/$lane.beat" state="-" note="" at="" ago="never" ab="-" lc="-"
    if [ -f "$f" ]; then
      state=$(field state "$f"); note=$(field note "$f"); at=$(field at "$f")
      local a; a=$(age_s "$at"); ago="$(mins "$a")m ago"
      case "$state" in
        working|testing|planning)
          if [ "$(mins "$a")" -ge "$QUIET_MIN" ]; then
            echo "$lane has been quiet since $at while $state" >> "$needs"
          fi ;;
        waiting-for-owner) echo "$lane is waiting for you: $note" >> "$needs" ;;
        blocked) echo "$lane is blocked: $note" >> "$needs" ;;
        ready-to-merge) echo "$lane is ready to merge (since $at): tell the orchestrator" >> "$needs" ;;
      esac
    else
      echo "$lane has never sent a heartbeat" >> "$needs"
    fi
    if [ -d "$WT/$lane" ]; then
      local cnt behind ahead
      cnt=$(git -C "$WT/$lane" rev-list --left-right --count "main...lane/$lane" 2>/dev/null || echo "? ?")
      ab="$(echo "$cnt" | awk '{print "+"$2"/-"$1}')"
      lc=$(git -C "$WT/$lane" log -1 --format=%cr "lane/$lane" 2>/dev/null | sed 's/ ago//' || echo "-")
      behind=$(echo "$cnt" | awk '{print $1}'); ahead=$(echo "$cnt" | awk '{print $2}')
      # A merged lane (nothing ahead of main) has nothing to rebase, however far main has moved.
      if [ "$behind" != "?" ] && [ "$ahead" != "0" ] && [ "$behind" -ge "$BEHIND_MAX" ]; then
        echo "$lane is $BEHIND_MAX or more commits behind main: ask it to rebase" >> "$needs"
      fi
    fi
    if [ -s "$DIR/$lane.nudge" ]; then note="(unread nudge) $note"; fi
    local prog head steps count bar
    prog="$(progress_of "$lane")"; head="$(printf '%s\n' "$prog" | head -1)"; steps="$(printf '%s\n' "$prog" | tail -n +2)"
    count="${head%% *}"; bar="${head#* }"; [ -n "$head" ] || { count="-"; bar=""; }
    printf '%-7s %5s  %s   %s · beat %s\n' "$lane" "$count" "$bar" "$state" "$ago"
    printf '        %s vs main · last commit %s\n' "$ab" "$lc"
    if [ -n "$steps" ]; then printf '%s\n' "$steps" | sed 's/^/        ├─ /'; fi
    [ -n "$note" ] && printf '        └─ %s\n' "${note:0:100}"
    echo
  done
  echo
  if [ -d "$LEASE" ]; then
    local h p s a; h=$(field holder "$LEASE/info"); p=$(field purpose "$LEASE/info"); s=$(field since "$LEASE/info")
    a=$(age_s "$s")
    echo "Dev stack: leased by $h for '$p', $(mins "$a") minutes"
    if [ "$(mins "$a")" -ge "$LEASE_MAX_MIN" ]; then
      echo "The dev stack has been leased by $h since $s ($p)" >> "$needs"
    fi
  else
    echo "Dev stack: free"
  fi
  echo "Claude sessions running: $(sessions)"
  echo
  if [ -s "$needs" ]; then echo "NEEDS YOU:"; sed 's/^/  - /' "$needs"; else echo "Nothing needs you."; fi
  mv "$needs" "$DIR/.needs"
}

notify() {
  local msg="$1"
  if command -v osascript >/dev/null 2>&1; then
    osascript -e "display notification \"${msg//\"/\'}\" with title \"OspreyFlow lanes\"" >/dev/null 2>&1 || true
  fi
}

# OSPREY_WATCH_PASSES stops after that many passes (the test's; unset, it runs until Ctrl-C).
watch_loop() {
  local every="${1:-300}" prev="$DIR/.needs.prev" pass=0
  : > "$prev"
  while true; do
    clear 2>/dev/null || true
    echo "OspreyFlow lanes · $(date '+%H:%M:%S') · every ${every}s · Ctrl-C to stop"; echo
    show
    # notify only for lines that are new since the last pass
    if [ -s "$DIR/.needs" ]; then
      while IFS= read -r line; do
        if ! grep -qxF -- "$line" "$prev"; then notify "$line"; fi
      done < "$DIR/.needs"
    fi
    cp "$DIR/.needs" "$prev"
    pass=$((pass + 1))
    if [ -n "${OSPREY_WATCH_PASSES:-}" ] && [ "$pass" -ge "$OSPREY_WATCH_PASSES" ]; then break; fi
    sleep "$every"
  done
}

case "${1:-show}" in
  beat) shift; beat "$@" ;;
  nudge) shift; nudge "$@" ;;
  show) show ;;
  watch) shift; watch_loop "${1:-300}" ;;
  *) echo "usage: lanes_heartbeat.sh beat <lane> <state> \"<note>\" | nudge <lane> \"<message>\" | show | watch [seconds]" >&2; exit 2 ;;
esac
