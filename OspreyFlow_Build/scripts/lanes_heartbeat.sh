#!/usr/bin/env bash
# The lanes' heartbeat and the owner's monitor (spec/06_DECISIONS.md ADR-142 decision 9).
#
#   lanes_heartbeat.sh beat <lane> <state> "<note>"   a lane records where it is
#        state: planning | working | testing | waiting-for-owner | blocked | ready-to-merge | idle | paused
#        (a lane at its usage limit is beaten from outside as: beat <lane> blocked "usage limit")
#   lanes_heartbeat.sh nudge <lane> "<message>"     the orchestrator leaves a lane a message, shown
#                                                     to it at its next beat (a session it cannot type into)
#   lanes_heartbeat.sh show                           one table: every lane, the lease, what needs you
#   lanes_heartbeat.sh watch [seconds]                show again every N seconds (default 300) and send a
#                                                     macOS notification when something newly needs you; a
#                                                     lane blocked at its usage limit is switched to its
#                                                     owner-written fallback account once, never otherwise
#                                                     (ADR-142 Amendment 1 decision 6)
#
# Heartbeats live outside every worktree ($OSPREY_LANES_DIR, default ~/.ospreyflow/lanes), so every
# session and the monitor see the same ones; each beat appends to <lane>.log and rewrites <lane>.beat.
# Each "Needs you" line names a fact that does not change from one pass to the next (since when, not
# for how long), so watch notifies once per new line, not on every pass. Its red-then-green proof is
# OspreyFlow_Build/tests/test_lanes_heartbeat.py (rule 15).
set -euo pipefail

DIR="${OSPREY_LANES_DIR:-$HOME/.ospreyflow/lanes}"
LEASE_DIR="${OSPREY_LEASE_DIR:-$HOME/.ospreyflow}"
WT="${OSPREY_WORKTREES:-$HOME/dev/osprey-wt}"
# The lanes and the test stacks (ADR-142 Amendment 3): scripts/lanes.conf and scripts/lane_stacks.tsv.
SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"
LANE_NAMES="studio case admin rules platform docs"
# shellcheck source=/dev/null
[ -f "$SCRIPTS_DIR/lanes.conf" ] && . "$SCRIPTS_DIR/lanes.conf"
LANES="${OSPREY_LANES:-$LANE_NAMES}"
STACKS="$(grep -v '^#' "$SCRIPTS_DIR/lane_stacks.tsv" 2>/dev/null | cut -f1 | awk 'NF && !seen[$0]++' | tr '\n' ' ')"
STACKS="${STACKS:-a}"
QUIET_MIN="${OSPREY_QUIET_MINUTES:-45}"       # a working lane silent this long is flagged
LEASE_MAX_MIN="${OSPREY_LEASE_MAX_MINUTES:-120}"
BEHIND_MAX="${OSPREY_BEHIND_MAX:-5}"
STATES="planning working testing waiting-for-owner blocked ready-to-merge idle paused"
LAUNCHER="${OSPREY_LAUNCHER:-$(cd "$(dirname "$0")" && pwd)/lanes_launch.sh}"
# The step table the orchestrator keeps on main (process/lanes/progress.tsv).
PROGRESS="${OSPREY_PROGRESS_FILE:-$(cd "$(dirname "$0")/.." && pwd)/process/lanes/progress.tsv}"
# The orchestrator's estimates of time to merge, beside the step table (the owner, 9 November 2026: "add the
# time estimates table to the heartbeat dashboard"). Tab-separated: lane, step, where it is, estimate; a first
# line `# as of <UTC ISO time>` says when they were made, so the dashboard can say how old they are.
ESTIMATES="${OSPREY_ESTIMATES_FILE:-$(dirname "$PROGRESS")/estimates.tsv}"
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

# A lane's steps from the step table: line 1 "done total", then "status<TAB>step<TAB>title" per step.
progress_of() {
  [ -f "$PROGRESS" ] || return 0
  awk -F'\t' -v lane="$1" '!/^#/ && NF>=4 && $1==lane {
      total++; if ($4=="done") done++
      word = ($4=="done" ? "done" : ($4=="review" ? "in review" : ($4=="building" ? "being built" : "to do")))
      line[++n] = word "\t" $2 "\t" $5
    }
    END { if (total) { printf "%d %d\n", done+0, total; for (i=1;i<=n;i++) print line[i] } }' "$PROGRESS"
}

# The step a lane is on: the first in review or being built, else the first still to do ("<id> <title>").
current_of() {
  [ -f "$PROGRESS" ] || return 0
  awk -F'\t' -v lane="$1" '!/^#/ && NF>=4 && $1==lane {
      if (!busy && ($4=="review" || $4=="building")) busy = $2 " " $5
      if (!next_ && $4=="todo") next_ = $2 " " $5 }
    END { print (busy ? busy : next_) }' "$PROGRESS"
}

# A progress bar: bar <done> <total> <width>, e.g. [███░░░░░░░░░].
bar() {
  local d="$1" t="$2" w="${3:-12}" f i out="["
  [ "$t" -gt 0 ] || { echo "[]"; return; }
  f=$(( (d * w + t / 2) / t ))
  for ((i = 0; i < w; i++)); do if [ "$i" -lt "$f" ]; then out+="█"; else out+="░"; fi; done
  echo "$out]"
}

# The whole build in one line; with a bar unless $1 is "plain" (`show --full` keeps its words alone).
overall() {
  [ -f "$PROGRESS" ] || return 0
  local counts; counts="$(awk -F'\t' '!/^#/ && NF>=4 { n++; c[$4]++ }
    END { if (n) printf "%d %d %d %d %d", c["done"]+0, n, c["review"]+0, c["building"]+0, c["todo"]+0 }' "$PROGRESS")"
  [ -n "$counts" ] || return 0
  set -- $counts "${1:-}"
  local b=""; [ "${6:-}" = plain ] || b="$(bar "$1" "$2" 24) "
  printf 'OVERALL: %s%d of %d steps done · %d in review · %d being built · %d to do\n\n' "$b" "$1" "$2" "$3" "$4" "$5"
}

# Prints one tree per lane; writes the lines that need the owner to $DIR/.needs
# Each test stack on one line; a lease held past its limit goes to the orchestrator's list ($1): its own
# check settles it (the owner, 9 November 2026).
stacks_lines() {
  local queue="$1" st lock
  for st in $STACKS; do
    if [ "$st" = a ]; then lock="$LEASE_DIR/stack.lease"; else lock="$LEASE_DIR/stack-$st.lease"; fi
    if [ -d "$lock" ]; then
      local h p s a; h=$(field holder "$lock/info"); p=$(field purpose "$lock/info"); s=$(field since "$lock/info")
      a=$(age_s "$s")
      echo "Test stack $st: leased by $h for '${p:0:70}', $(mins "$a") minutes"
      if [ "$(mins "$a")" -ge "$LEASE_MAX_MIN" ]; then
        echo "Test stack $st has been leased by $h since $s ($p)" >> "$queue"
      fi
    else
      echo "Test stack $st: free"
    fi
  done
}

# The estimates table, with when it was made and how long ago; nothing when there is no estimates file.
estimates() {
  [ -s "$ESTIMATES" ] || { echo; return 0; }
  local asof ago="" t
  asof="$(sed -n 's/^# as of //p' "$ESTIMATES" | head -1)"
  if [ -n "$asof" ]; then
    t="$(date -u -j -f '%Y-%m-%dT%H:%M:%SZ' "$asof" +%s 2>/dev/null || date -u -d "$asof" +%s 2>/dev/null || echo "")"
    [ -n "$t" ] && ago=", $(( ($(date -u +%s) - t) / 60 ))m ago"
  fi
  echo "ESTIMATED TIME TO MERGE (the orchestrator's${asof:+, as of ${asof:11:5} UTC}$ago):"
  grep -v '^#' "$ESTIMATES" | awk -F'\t' 'NF >= 4 { printf "  %-9s %-6s %-46s %s\n", $1, $2, substr($3, 1, 46), $4 }'
  echo
}

# `show` is one screen: a heading and at most one note line per lane, with the step it is on (the owner,
# 8 November 2026: no scrolling). `show --full` adds every step as a checklist.
show() {
  local full=""; [ "${1:-}" = "--full" ] && full=1
  local width="${COLUMNS:-$(tput cols 2>/dev/null || echo 110)}"; [ "$width" -gt 120 ] && width=120
  # Each run its own files: the owner's `watch` and anyone's `show` may run at the same moment.
  local needs mine
  needs="$(mktemp "$DIR/.needs.XXXXXX")"; mine="$(mktemp "$DIR/.orchestrator.XXXXXX")"
  if [ -n "$full" ]; then overall plain | sed '/^$/d'; else overall | sed '/^$/d'; fi
  stacks_lines "$mine"
  echo "Claude sessions running: $(sessions)"
  echo
  for lane in $LANES; do
    local f="$DIR/$lane.beat" state="-" note="" at="" ago="never" ab="-" lc="-"
    if [ -f "$f" ]; then
      state=$(field state "$f"); note=$(field note "$f"); at=$(field at "$f")
      local a; a=$(age_s "$at"); ago="$(mins "$a")m ago"
      case "$state" in
        working|testing|planning)
          if [ "$(mins "$a")" -ge "$QUIET_MIN" ]; then
            echo "$lane has been quiet since $at while $state" >> "$mine"   # the orchestrator's check asks it
          fi ;;
        waiting-for-owner)
          case "$note" in
            *"lease"*) echo "$lane is waiting for the lease: $note" >> "$mine" ;;   # the orchestrator passes it
            *) echo "$lane is waiting for you: $note" >> "$needs" ;;
          esac ;;
        blocked)
          case "$note" in
            *"lease"*) echo "$lane is waiting for the lease: $note" >> "$mine" ;;   # the orchestrator passes it
            *"usage limit"*) echo "$lane stopped at its usage limit on account $(cat "$DIR/$lane.account" 2>/dev/null || echo default): switch it (lanes_launch.sh switch $lane --account <name>) or write a fallback line" >> "$needs" ;;
            *) echo "$lane is blocked: $note" >> "$needs" ;;
          esac ;;
        paused) ago="paused $(mins "$a")m ago" ;;   # a paused lane is never stalled
        ready-to-merge) echo "$lane is ready to merge (since $at)" >> "$mine" ;;
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
        echo "$lane is $BEHIND_MAX or more commits behind main: to rebase" >> "$mine"
      fi
    fi
    if [ -s "$DIR/$lane.nudge" ]; then note="(unread nudge) $note"; fi
    if [ "$state" != paused ] && grep -q '^requested' "$DIR/$lane.pause" 2>/dev/null; then note="(pause requested) $note"; fi
    local account; account="$(cat "$DIR/$lane.account" 2>/dev/null || echo default)"
    local prog head steps done total merged
    prog="$(progress_of "$lane")"; head="$(printf '%s\n' "$prog" | head -1)"; steps="$(printf '%s\n' "$prog" | tail -n +2)"
    done="${head%% *}"; total="${head#* }"
    merged=""
    case "$ab" in +0/*) merged="all merged" ;; +*) merged="${ab%%/*} commits not yet merged"; merged="${merged#+}" ;; esac
    printf '%s: ' "$(echo "$lane" | tr '[:lower:]' '[:upper:]')"
    if [ -z "$full" ]; then
      # Two lines: the bar and the state; then the step it is on and its note, each within the screen.
      local now line2
      [ -n "$head" ] && printf '%s %s of %s done · ' "$(bar "$done" "$total" 12)" "$done" "$total"
      case "$merged" in "all merged") merged=merged ;; *" commits not yet merged") merged="${merged%% *} to merge" ;; esac
      if [ "$state" = paused ]; then
        printf '%s · account %s%s\n' "$ago" "$account" "${merged:+ · $merged}"
      else
        printf '%s · %s · account %s%s\n' "$state" "$ago" "$account" "${merged:+ · $merged}"
      fi
      now="$(current_of "$lane")"
      line2="${now:+now ${now%% *} $(echo "${now#* }" | cut -c1-48)}"
      [ -n "$note" ] && line2="${line2:+$line2 — }$note"
      [ -n "$line2" ] && printf '  %s\n' "${line2:0:$((width - 2))}"
      continue
    fi
    [ -n "$head" ] && printf '%s of %s done · ' "$done" "$total"
    if [ "$state" = paused ]; then
      printf '%s · account %s%s\n' "$ago" "$account" "${merged:+ · $merged}"
    else
      printf '%s · last heard %s · account %s%s\n' "$state" "$ago" "$account" "${merged:+ · $merged}"
    fi
    if [ -n "$steps" ]; then
      printf '%s\n' "$steps" | awk -F'\t' -v note="${note:0:90}" '{
          now = ""; if (!told && ($1=="in review" || $1=="being built") && note != "") { now = "   <- now: " note; told = 1 }
          printf "  %-12s %-6s %s%s\n", $1, $2, $3, now }
        END { if (!told && note != "") printf "  note: %s\n", note }'
    elif [ -n "$note" ]; then printf '  note: %s\n' "${note:0:90}"; fi
    echo
  done
  estimates
  echo
  if [ -s "$needs" ]; then echo "NEEDS YOU:"; sed 's/^/  - /' "$needs"; else echo "Nothing needs you."; fi
  # The orchestrator's own queue: shown for information, never notified.
  if [ -s "$mine" ]; then echo; echo "FOR THE ORCHESTRATOR (it acts on these; nothing for you):"; sed 's/^/  - /' "$mine"; fi
  rm -f "$mine"
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
    # Amendment 1 decision 6: only under the owner's fallback line, and once (lanes_launch.sh checks both).
    for lane in $LANES; do
      if [ "$(field state "$DIR/$lane.beat")" = blocked ] && field note "$DIR/$lane.beat" | grep -q "usage limit"; then
        "$LAUNCHER" fallback-switch "$lane" >> "$DIR/.fallback.log" 2>&1 || true
      fi
    done
    pass=$((pass + 1))
    if [ -n "${OSPREY_WATCH_PASSES:-}" ] && [ "$pass" -ge "$OSPREY_WATCH_PASSES" ]; then break; fi
    sleep "$every"
  done
}

case "${1:-show}" in
  beat) shift; beat "$@" ;;
  nudge) shift; nudge "$@" ;;
  show) shift; show "${1:-}" ;;
  watch) shift; watch_loop "${1:-300}" ;;
  *) echo "usage: lanes_heartbeat.sh beat <lane> <state> \"<note>\" | nudge <lane> \"<message>\" | show | watch [seconds]" >&2; exit 2 ;;
esac
