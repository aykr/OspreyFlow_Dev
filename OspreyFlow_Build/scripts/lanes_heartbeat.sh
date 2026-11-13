#!/usr/bin/env bash
# The lanes' heartbeat and the owner's monitor (spec/06_DECISIONS.md ADR-142 decision 9).
#
#   lanes_heartbeat.sh beat <lane> <state> "<note>"   a lane records where it is
#        state: planning | working | testing | waiting-for-owner | blocked | ready-to-merge | idle | paused
#        (a lane at its usage limit is beaten from outside as: beat <lane> blocked "usage limit")
#   lanes_heartbeat.sh stages <lane> "<step>" "<n>|<state>|<name>[|<note>]" ...
#                                                     a lane states its current step's stages, numbered
#        state: done | now | todo | blocked; a second call for the same step replaces its list; each
#        step keeps its own list (13 November 2026)
#   lanes_heartbeat.sh stages <lane> --clear "<step>" the step is finished: its stages go
#   lanes_heartbeat.sh stages <lane> --clear --all    every step's stages of the lane go
#   lanes_heartbeat.sh nudge <lane> "<message>"     the orchestrator leaves a lane a message, shown
#                                                     to it at its next beat (a session it cannot type into)
#   lanes_heartbeat.sh [--full]                       the owner's default view (reorganised 13 November 2026):
#                                                     what needs you, the path to the release, each active
#                                                     lane with its stages, the steps left one line a group,
#                                                     the release, housekeeping, and one row per lane;
#                                                     --full: every group's block and every merge in full
#   lanes_heartbeat.sh --lanes [--full]               lane by lane (the same as `show`)
#   lanes_heartbeat.sh show                           one table: every lane, the lease, what needs you
#   lanes_heartbeat.sh summary                        the older short view: one line of totals, what needs
#                                                     you, and the remaining steps by track with their times
#   lanes_heartbeat.sh watch [seconds] [--full]       the default view and what needs you (--full: lane by
#   lanes_heartbeat.sh watch --full [seconds]         lane) every N seconds (default 300), and send a
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
STAGE_STATES="done now todo blocked"
LAUNCHER="${OSPREY_LAUNCHER:-$(cd "$(dirname "$0")" && pwd)/lanes_launch.sh}"
# The step table the orchestrator keeps on main (process/lanes/progress.tsv).
PROGRESS="${OSPREY_PROGRESS_FILE:-$(cd "$(dirname "$0")/.." && pwd)/process/lanes/progress.tsv}"
# The orchestrator's estimates of time to merge, beside the step table (the owner, 9 November 2026: "add the
# time estimates table to the heartbeat dashboard"). Tab-separated: lane, step, where it is, estimate; a first
# line `# as of <UTC ISO time>` says when they were made, so the dashboard can say how old they are.
ESTIMATES="${OSPREY_ESTIMATES_FILE:-$(dirname "$PROGRESS")/estimates.tsv}"
# The default view's two groupings of every step (groups.tsv: lane, step, feature, deployment; its header lists
# the allowed values) and the release it reports (release.tsv: key, value), both beside the step table.
GROUPS_FILE="${OSPREY_GROUPS_FILE:-$(dirname "$PROGRESS")/groups.tsv}"
RELEASE="${OSPREY_RELEASE_FILE:-$(dirname "$PROGRESS")/release.tsv}"
# The path to the next release, in order, with what each step needs first (the owner, 13 November 2026: "list the
# steps and their expected completion times ... show the dependencies between the steps"). finish.tsv, kept by
# the orchestrator: id, step, who, expected, after (ids, comma-separated, or -), status (done | building | todo);
# a first line `# target <name>` names the release. A step not done whose `after` names a step not done is shown
# as waiting on it, whatever its own status says.
FINISH="${OSPREY_FINISH_FILE:-$(dirname "$PROGRESS")/finish.tsv}"
# The route to the next release (ROUTE_052.md, the owner, 13 November 2026): route.tsv, what the owner and the
# orchestrator owe (owner_due.tsv) and the audit rulings (audit.tsv), beside the step table. With a route.tsv,
# the default view and watch show the route; without one, the overview.
ROUTE="${OSPREY_ROUTE_FILE:-$(dirname "$PROGRESS")/route.tsv}"
OWNER_DUE="${OSPREY_OWNER_DUE_FILE:-$(dirname "$PROGRESS")/owner_due.tsv}"
AUDIT="${OSPREY_AUDIT_FILE:-$(dirname "$PROGRESS")/audit.tsv}"
ACCOUNTS="${OSPREY_ACCOUNTS_FILE:-$HOME/.ospreyflow/accounts.conf}"   # lanes_launch.sh's own default
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
# The first value only, read whole: under pipefail a `| head -1` whose producer is still writing dies of SIGPIPE
# (141) and ends the whole view (12 November 2026: `show` stopped part-way under the parallel test run).
field() { sed -n "s/^$1=//p" "$2" 2>/dev/null | sed -n 1p; }

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

# A lane's stages, one list a step (brief hb, 13 November 2026; kept per lane and step since the orchestrator's
# hb2, 13 November: one file a lane let a post for a new step erase its earlier steps' lists): <lane>.<step>.stages,
# each byte of the step other than an ASCII letter, digit, '.', '_' or '-' written '_' (`stage_file`, and the views'
# `stages_of` in STAGES_PL, the one reader both views share). Written whole (as
# `beat` writes its file), the step and the time, then one `stage=<n>|<state>|<name>[|<note>]` line each. Every stage
# is checked before anything is written, so a refused call leaves the earlier list as it was. The views still read a
# lane's one <lane>.stages from before, for the step it names.
stage_file() { local LC_ALL=C; printf '%s/%s.%s.stages' "$DIR" "$1" "${2//[^A-Za-z0-9._-]/_}"; }   # byte by byte, as the views read it
stages() {
  local usage='usage: stages <lane> "<step>" "<n>|<state>|<name>[|<note>]" ... | stages <lane> --clear "<step>" | stages <lane> --clear --all'
  local lane="${1:?$usage}"; shift
  if [ "${1:-}" = --clear ]; then
    # Named, never implied: a lane with two steps in flight clears the one it finished, not both (hb2's review).
    case "${2:-}" in
      '') echo "Say which step's stages go: stages $lane --clear \"<step>\", or every step's: --clear --all." >&2; exit 2 ;;
      --all) rm -f "$DIR/$lane.stages" "$DIR/$lane".*.stages; echo "Stages cleared for $lane, every step."; return 0 ;;
    esac
    rm -f "$(stage_file "$lane" "$2")"
    if [ -f "$DIR/$lane.stages" ] && [ "$(field step "$DIR/$lane.stages" || true)" = "$2" ]; then rm -f "$DIR/$lane.stages"; fi
    echo "Stages cleared for $lane, $2."; return 0
  fi
  local step="${1:?$usage}"; shift
  [ $# -ge 1 ] || { echo "No stages given. A stage is <n>|<state>|<name>[|<note>]." >&2; exit 2; }
  local nl=$'\n' s n st name rest
  case "$step" in *"$nl"*) echo "The step is one line: '$step'." >&2; exit 2 ;; esac
  for s in "$@"; do
    case "$s" in *"$nl"*) echo "A stage is one line: '$s'." >&2; exit 2 ;; esac
    IFS='|' read -r n st name rest <<< "$s"
    case "$n" in ''|*[!0-9]*) echo "A stage is <n>|<state>|<name>[|<note>], with n a number: '$s'." >&2; exit 2 ;; esac
    [ -n "$name" ] || { echo "A stage is <n>|<state>|<name>[|<note>], with a name: '$s'." >&2; exit 2; }
    case "$st" in done|now|todo|blocked) ;; *) echo "Unknown stage state '$st' in '$s'. One of: $STAGE_STATES" >&2; exit 2 ;; esac
  done
  # Shown only for the step the lane is on, which the view takes from the step table: say so when it lacks this one.
  if [ -f "$PROGRESS" ] && ! awk -F'\t' -v l="$lane" -v s="$step" '!/^#/ && $1 == l && $2 == s { f = 1 } END { exit !f }' "$PROGRESS"; then
    echo "Kept, but '$step' is not one of $lane's steps in the step table (progress.tsv): it shows once its beat is on a step of that name." >&2
  fi
  local file; file="$(stage_file "$lane" "$step")"
  { printf 'step=%s\nat=%s\n' "$step" "$(iso)"; printf 'stage=%s\n' "$@"; } > "$file.tmp"
  mv "$file.tmp" "$file"
  echo "Stages: $lane, $step, $# stages."
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
  asof="$(sed -n 's/^# as of //p' "$ESTIMATES" | sed -n 1p)"
  if [ -n "$asof" ]; then
    t="$(date -u -j -f '%Y-%m-%dT%H:%M:%SZ' "$asof" +%s 2>/dev/null || date -u -d "$asof" +%s 2>/dev/null || echo "")"
    [ -n "$t" ] && ago=", $(( ($(date -u +%s) - t) / 60 ))m ago"
  fi
  echo "ESTIMATED TIME TO MERGE (the orchestrator's${asof:+, as of ${asof:11:5} UTC}$ago):"
  # Cut and padded by characters, never bytes (BSD awk and cut count bytes: an en dash cut through printed invalid
  # UTF-8, 10 November 2026): perl in UTF-8 mode, on macOS and Linux alike.
  { grep -v '^#' "$ESTIMATES" || true; } | perl -CSD -F'\t' -lane 'next if @F < 4; printf "  %-9s %-6s %-46s %s\n", $F[0], $F[1], substr($F[2], 0, 46), $F[3]'
  echo
}

# A note waiting for a test stack names the lease: the word itself, never the letters inside "release" (13 November
# 2026: "waiting for R1 to release the test server" was read as waiting for the lease, and left NEEDS YOU).
LEASE_RE='(^|[^[:alpha:]])[Ll]ease([^[:alpha:]]|$)'
names_lease() { [[ "$1" =~ $LEASE_RE ]]; }

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
          if names_lease "$note"; then echo "$lane is waiting for the lease: $note" >> "$mine"   # the orchestrator passes it
          else case "$note" in
            # Only a note that names the owner is the owner's: lanes beat this state while they wait on
            # the orchestrator (a merge, a slot, a stack), and on 10 November 2026 those reached Needs you.
            *[Oo]wner*) echo "$lane is waiting for you: $note" >> "$needs" ;;
            *) echo "$lane is waiting for the orchestrator: $note" >> "$mine" ;;
          esac; fi ;;
        blocked)
          if names_lease "$note"; then echo "$lane is waiting for the lease: $note" >> "$mine"   # the orchestrator passes it
          else case "$note" in
            *"usage limit"*) echo "$lane stopped at its usage limit on account $(cat "$DIR/$lane.account" 2>/dev/null || echo default): switch it (lanes_launch.sh switch $lane --account <name>) or write a fallback line" >> "$needs" ;;
            *) echo "$lane is blocked: $note" >> "$needs" ;;
          esac; fi ;;
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
    prog="$(progress_of "$lane")"; head="${prog%%$'\n'*}"; steps="$(printf '%s\n' "$prog" | tail -n +2)"
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
      line2="${now:+now ${now%% *} $(printf '%s\n' "${now#* }" | perl -CSD -ne 'print substr($_, 0, 48)' | tr -d '\n')}"
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
  # The default view reads the same lines (NEEDS_COPY, its own file: views run at once must not mix them).
  if [ -n "${NEEDS_COPY:-}" ]; then cp "$needs" "$NEEDS_COPY"; fi
  mv "$needs" "$DIR/.needs"
}

# The owner's short view (10 November 2026: "the dashboard is getting too busy to read"): one line of totals, what
# needs you, then the remaining steps as the orchestrator's estimates give them, by track (estimates.tsv's fifth
# column, A demo or B client; none means A), then one line of lane states. `show` keeps every detail.
summary() {
  show >/dev/null   # works out what needs the owner, as watch's notifications rely on
  local counts done=0 total=0 inuse=0 lock
  counts="$(awk -F'\t' '!/^#/ && NF>=4 { n++; if ($4 == "done") d++ } END { printf "%d %d", d+0, n+0 }' "$PROGRESS" 2>/dev/null)"
  [ -n "$counts" ] && read -r done total <<< "$counts"
  for lock in "$LEASE_DIR"/stack.lease "$LEASE_DIR"/stack-*.lease; do [ -d "$lock" ] && inuse=$((inuse + 1)); done
  echo "OSPREYFLOW · $done of $total steps done · stacks in use: $inuse · sessions: $(sessions)"
  echo
  if [ -s "$DIR/.needs" ]; then echo "NEEDS YOU:"; sed 's/^/  - /' "$DIR/.needs"; else echo "Nothing needs you."; fi
  if [ -s "$ESTIMATES" ]; then
    local asof; asof="$(sed -n 's/^# as of //p' "$ESTIMATES" | sed -n 1p)"
    echo
    echo "REMAINING (the orchestrator's estimates${asof:+, as of ${asof:11:5} UTC}):"
    { grep -v '^#' "$ESTIMATES" || true; } | perl -CSD -F'\t' -lane 'next if @F < 4; $t = (($F[4] // "") eq "B") ? "B" : "A";
        $r{$t} .= sprintf("    %-10s %-7s %-40s %s\n", $F[0], $F[1], substr($F[2], 0, 40), $F[3]);
      END { print "  Demo track:\n$r{A}" =~ s/\n\z//r if $r{A}; print "  Client track:\n$r{B}" =~ s/\n\z//r if $r{B} }'
  fi
  echo
  local line="" lane st
  for lane in $LANES; do
    st="$(field state "$DIR/$lane.beat" || true)"; [ -n "$st" ] || st="-"
    line="$line$lane $st · "
  done
  echo "LANES: ${line% · }"
  echo "Every detail: lanes_heartbeat.sh show"
}

# --- the owner's default view (11 November 2026; reporting only) -------------------------------------------
# Two views of the same steps, by foundation feature and by deployment (groups.tsv), each block "N of M steps
# done" and then only the steps not done, in plain words; then the release, housekeeping and one row per lane.
# Every step is counted somewhere: a step groups.tsv does not group is listed under its own heading, never
# dropped (test_lanes_groups.py keeps that heading empty).

# A lane's account: its <lane>.account, else its line in the owner's accounts file, else "default".
account_of() {
  local a
  a="$(cat "$DIR/$1.account" 2>/dev/null || true)"
  [ -n "$a" ] || a="$(awk -v l="$1" '$1 == "lane" && $2 == l && $3 == "=" { print $4; exit }' "$ACCOUNTS" 2>/dev/null || true)"
  echo "${a:-default}"
}

# Where a lane's session runs: lanes_launch.sh's own alive test (a Claude Code process in its worktree).
where_of() {
  if (cd "$SCRIPTS_DIR" && "$LAUNCHER" alive "$1") >/dev/null 2>&1; then echo "this Mac"; else echo "not running"; fi
}

# What has merged since the release. The merge commits on main since release.tsv's `cut` (first parent only, so a
# lane's own merges of main are not counted) when that commit is in this repository; progress.tsv carries no
# dates, so it cannot say what merged after a given day, and a cut this repository lacks is said in words.
release_merges() {
  # OSPREY_REPO: the repository whose main is read (the test's own; CI's checkout holds one commit).
  local cut ref="${OSPREY_MAIN_REF:-main}" repo="${OSPREY_REPO:-$SCRIPTS_DIR}"
  cut="$(awk -F'\t' '!/^#/ && $1 == "cut" { print $2; exit }' "$RELEASE" 2>/dev/null || true)"
  if [ -n "$cut" ] && git -C "$repo" cat-file -e "$cut^{commit}" 2>/dev/null; then
    printf 'from\t%s\n' "$cut"
    git -C "$repo" log --merges --first-parent --format='%cs%x09%s' "$cut..$ref" 2>/dev/null || true
  else
    printf 'missing\t%s\n' "$cut"
  fi
}

clock() {
  local e fmt='%a %e %b %Y, %H:%M'
  e="$(now)"
  printf '%s UTC (%s UK time)' \
    "$(date -u -r "$e" +"$fmt" 2>/dev/null || date -u -d "@$e" +"$fmt")" \
    "$(TZ=Europe/London date -r "$e" +%H:%M 2>/dev/null || TZ=Europe/London date -d "@$e" +%H:%M)"
}

overview() {
  local full="" lanes merges needs lane st note at ago
  [ "${1:-}" = --full ] && full=1
  lanes="$(mktemp "$DIR/.overview.XXXXXX")"; merges="$(mktemp "$DIR/.merges.XXXXXX")"; needs="$(mktemp "$DIR/.ovneeds.XXXXXX")"
  # shellcheck disable=SC2064   # these files, now
  trap "rm -f '$lanes' '$merges' '$needs'" EXIT
  # What needs the owner, by `show`'s own reading, into this view's own file; watch keeps a copy (OVERVIEW_NEEDS)
  # for its notifications, so another view run meanwhile cannot change what it notifies.
  NEEDS_COPY="$needs" show >/dev/null
  if [ -n "${OVERVIEW_NEEDS:-}" ]; then cp "$needs" "$OVERVIEW_NEEDS"; fi
  for lane in $LANES; do
    # A lane that has never beaten has no .beat file; under pipefail that must not end the whole view.
    st="$(field state "$DIR/$lane.beat" || true)"; note="$(field note "$DIR/$lane.beat" || true)"
    at="$(field at "$DIR/$lane.beat" || true)"; ago="-"
    [ -n "$at" ] && ago="$(mins "$(age_s "$at")")"
    printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$lane" "${st:--}" "$note" "$(account_of "$lane")" "$(where_of "$lane")" "$ago" >> "$lanes"
  done
  release_merges > "$merges"
  P_CLOCK="$(clock)" P_PROGRESS="$PROGRESS" P_GROUPS="$GROUPS_FILE" P_EST="$ESTIMATES" P_RELEASE="$RELEASE" P_FINISH="$FINISH" \
    P_LANES="$lanes" P_MERGES="$merges" P_NEEDS="$needs" P_DIR="$DIR" P_FULL="$full" perl -CSD -e "$STAGES_PL$OVERVIEW_PL"
  rm -f "$lanes" "$merges" "$needs"; trap - EXIT
}

# shellcheck disable=SC2016   # perl, not the shell, expands these
# The one reader of a lane`s stages, which both views run before their own program (hb2`s review: two copies drift).
# A lane`s stages for one step: its own file (`stage_file`: the step`s UTF-8 bytes, each other than an ASCII letter,
# digit, ".", "_" or "-" written "_"), else the one file a lane kept before, when it names that step.
STAGES_PL='
sub stages_in { my ($f) = @_; my ($step, @s); open(my $h, "<:encoding(UTF-8)", $f) or return;
  while (<$h>) { chomp; if (/^step=(.*)$/) { $step = $1 } elsif (/^stage=(.*)$/) { my @p = split /\|/, $1, 4; push @s, \@p if @p >= 3 } }
  return ($step, @s) }
sub stage_name { my ($step) = @_; require Encode; return Encode::encode("UTF-8", $step) =~ s/[^A-Za-z0-9._-]/_/gr }
sub stages_of { my ($lane, $want) = @_; return unless defined $want;
  my ($step, @s) = stages_in("$ENV{P_DIR}/$lane." . stage_name($want) . ".stages");
  return ($step, @s) if defined $step && $step eq $want;
  ($step, @s) = stages_in("$ENV{P_DIR}/$lane.stages");
  return defined $step && $step eq $want ? ($step, @s) : () }
'

# shellcheck disable=SC2016   # perl, not the shell, expands these
OVERVIEW_PL='
use strict; use warnings; use utf8;
sub rows { my ($f) = @_; my @r; open(my $h, "<:encoding(UTF-8)", $f) or return @r;
  while (<$h>) { chomp; next if /^#/ || !/\S/; push @r, [split /\t/, $_, -1] } return @r }
sub cut { my ($s, $n) = @_; return $s if length $s <= $n; $s = substr($s, 0, $n - 1); $s =~ s/\s+\S*$//; return "$s…" }
my @prog = grep { @$_ >= 5 } rows($ENV{P_PROGRESS});
my (%feat, %dep);
for (rows($ENV{P_GROUPS})) { next if @$_ < 4; my $k = "$_->[0]\t$_->[1]"; ($feat{$k}, $dep{$k}) = ($_->[2], $_->[3]) }
my %day;   # estimates.tsv: lane, step (or "P8, P9b"), note, day, track
for (rows($ENV{P_EST})) { next if @$_ < 4; my $r = $_; $day{"$r->[0]\t$_"} = $r->[3] for split /,\s*/, $r->[1] }
my %rel; for (rows($ENV{P_RELEASE})) { $rel{$_->[0]} = $_->[1] if @$_ >= 2 }
my @lanes = grep { @$_ >= 5 } rows($ENV{P_LANES});
my %plain = (todo => "not started", building => "building", review => "in review", done => "merged");

# The step a lane is on: the step of its own that its beat names first (the longer of two at one place, so
# "P5b proof" over "P5b"); a beat that names none falls back to the step table: the first in review or being
# built, else the first not started.
my (%on, %beat);
for my $l (@lanes) {
  my ($lane, $state, $note) = @$l; $beat{$lane} = [$state, $note];
  my ($best, $pos);
  for my $r (grep { $_->[0] eq $lane } @prog) {
    my $s = $r->[1];
    next unless $note =~ /(?<![A-Za-z0-9.\-])\Q$s\E(?![A-Za-z0-9\-])/;
    my $p = $-[0];
    ($best, $pos) = ($s, $p) if !defined $pos || $p < $pos || ($p == $pos && length $s > length $best);
  }
  unless (defined $best) {
    my @mine = grep { $_->[0] eq $lane } @prog;
    my ($busy) = grep { $_->[3] eq "review" || $_->[3] eq "building" } @mine;
    my ($todo) = grep { $_->[3] eq "todo" } @mine;
    $best = ($busy || $todo || [])->[1];
  }
  $on{$lane} = $best if defined $best;
}

# A step'"'"'s name: its title'"'"'s first clause, after any leading "deferred"/"cut" status words.
sub name_of { my ($t) = @_;
  $t =~ s/^(?:DEFERRED|Cut for|After the client.s install)[^:]*:\s*//;
  $t =~ s/(?::|;| \(| — ).*//; return ucfirst cut($t, 60) }
sub shortnote { my ($n) = @_; my @w = split " ", $n; my $s = join " ", @w[0 .. ($#w < 5 ? $#w : 5)];
  $s =~ s/[\s,;:.]+$//; return @w > 6 ? "$s…" : $s }
sub state_of { my ($r) = @_; my ($lane, $step, $status) = @$r[0, 1, 3];
  if ($status ne "done" && defined $on{$lane} && $on{$lane} eq $step) {
    my ($bs, $bn) = @{ $beat{$lane} };
    return "waiting to merge" if $bs eq "ready-to-merge";
    return "blocked" if $bs eq "blocked";
    if ($bs eq "waiting-for-owner") {   # the same reading as `show`: only a note naming the owner is the owner'"'"'s
      return "waiting for a test stack" if $bn =~ /(?<![[:alpha:]])[Ll]ease(?![[:alpha:]])/;   # the word, as `show` reads it
      return "needs you: " . shortnote($bn) if $bn =~ /[Oo]wner/;
      return "waiting for the orchestrator";
    } }
  return $plain{$status} // "not started" }
sub line_of { my ($r) = @_; my $d = $day{"$r->[0]\t$r->[1]"} // "no estimate";
  return sprintf "    %s (%s, %s) · %s · %s", name_of($r->[4]), $r->[1], $r->[0], state_of($r), $d }
sub block { my ($title, @in) = @_; my $done = grep { $_->[3] eq "done" } @in;
  print "  $title\n"; printf "    %d of %d steps done\n", $done, scalar @in;
  print line_of($_), "\n" for grep { $_->[3] ne "done" } @in; print "\n" }
sub k { "$_[0][0]\t$_[0][1]" }

my $asof = ""; if (open(my $h, "<", $ENV{P_EST})) { while (<$h>) { $asof = $1 if /^# as of \S*T(\d\d:\d\d)/ } }
print "OSPREYFLOW · $ENV{P_CLOCK}\n";
print "Client-install chain expected to finish merging: ", ($rel{chain} // "unknown"),
  ($asof ? " (estimates as of $asof UTC)" : ""), "\n";
{ my %c; $c{$_->[3]}++ for @prog;   # the same figures as `show`'"'"'s OVERALL line (the owner, 11 November 2026)
  printf "OVERALL: %d of %d steps done · %d in review · %d building · %d not started\n\n",
    $c{done} // 0, scalar @prog, $c{review} // 0, $c{building} // 0, $c{todo} // 0 }
my $full = $ENV{P_FULL};

# What needs the owner, first (brief hb, 13 November 2026): `show`'"'"'s own lines.
{ my @n; if (open(my $h, "<:encoding(UTF-8)", $ENV{P_NEEDS})) { @n = grep { /\S/ } map { s/\s+$//r } <$h> }
  if (@n) { print "NEEDS YOU:\n"; print "  - $_\n" for @n } else { print "Nothing needs you.\n" }
  print "\n" }

# The path to the next release (finish.tsv): each step, who, when, and what it waits on.
{ my @f = grep { @$_ >= 6 } rows($ENV{P_FINISH});
  if (@f) {
    my $target = "the next release";
    if (open(my $h, "<:encoding(UTF-8)", $ENV{P_FINISH})) { while (<$h>) { $target = $1 if /^# target (.+?)\s*$/ } }
    my %st = map { $_->[0] => $_->[5] } @f;
    my %plainf = (done => "done", building => "in progress", todo => "not started");
    my $left = grep { $_->[5] ne "done" } @f;
    printf "PATH TO %s · %d of %d steps left\n", uc $target, $left, scalar @f;
    for my $r (@f) {
      my ($id, $step, $who, $when, $after, $status) = @$r;
      my @after = grep { $_ ne "" && $_ ne "-" } split /\s*,\s*/, $after;
      my @open = grep { ($st{$_} // "todo") ne "done" } @after;
      my $state = $status eq "done" ? "done"
        : @open ? "waiting on " . join(", ", @open) : ($plainf{$status} // $status);
      my @parts = (cut($step, 58), $who, $state);
      push @parts, "expected $when" if $status ne "done";
      push @parts, "after " . join(", ", @after) if @after && $status ne "done";
      printf "  %-3s %s\n", "$id.", join(" · ", @parts);
    }
    print "\n";
  } }

# Each lane at work, with its current step'"'"'s stages (`stages`); paused, idle and silent lanes on one line at the end.
sub words_of { my ($s, $n) = @_;   # the beat'"'"'s state in plain words, read as `show` reads it
  return "ready to merge" if $s eq "ready-to-merge";
  if ($s eq "waiting-for-owner") {
    return "waiting for a test stack" if $n =~ /(?<![[:alpha:]])[Ll]ease(?![[:alpha:]])/;
    return $n =~ /[Oo]wner/ ? "waiting for you" : "waiting for the orchestrator" }
  return $s }
{ my %mark = (done => "✅", now => "⏳", todo => "—", blocked => "⛔");
  my (%rest, @order);
  print "LANES NOW\n";
  for my $l (@lanes) {
    my ($lane, $state, $note, undef, undef, $ago) = @$l;
    if ($state eq "paused" || $state eq "idle" || $state eq "-") {
      my $k = $state eq "-" ? "no heartbeat" : $state; push @order, $k unless $rest{$k}; push @{ $rest{$k} }, $lane; next }
    my ($step, @s) = stages_of($lane, $on{$lane});
    # A list is shown only for the step the lane is on (%on: the first step its beat names, else the step table'"'"'s
    # current one), never for one its note mentions in passing.
    @s = () unless defined $step && defined $on{$lane} && $on{$lane} eq $step;
    my $head = sprintf "  %s · %s · %s · last heard %s", uc $lane, (@s ? $step : $on{$lane} // "-"), words_of($state, $note),
      (defined $ago && $ago ne "-" ? "${ago}m ago" : "never");
    if (@s) {
      # Where the lane is: the stage under way, else a blocked one, else the first not started.
      my ($at) = ((grep { $_->[1] eq "now" } @s), (grep { $_->[1] eq "blocked" } @s), (grep { $_->[1] eq "todo" } @s));
      $head .= $at ? sprintf(" · stage %s of %d", $at->[0], scalar @s) : sprintf(" · all %d stages done", scalar @s);
      print cut($head, 120), "\n";
      for (@s) { my ($n, $st, $name, $nt) = @$_;
        print cut(sprintf("    %s %s. %s%s", $mark{$st} // "?", $n, $name, defined $nt && $nt ne "" ? " · $nt" : ""), 118), "\n" }
    } else {
      print cut($head, 120), "\n"; print "    ", cut($note, 112), "\n" if $note ne "" }
  }
  @order = grep { $rest{$_} } ("idle", "paused", "no heartbeat");   # the same order every time
  if (@order) { print "  ", ucfirst(join("; ", map { "$_: " . join(", ", @{ $rest{$_} }) } @order)), "\n" }
  print "\n" }

# One line a group (`--full`: the blocks), naming only the steps not done.
sub group { my ($title, @in) = @_;
  return block($title, @in) if $full;
  my $done = grep { $_->[3] eq "done" } @in; my @open = grep { $_->[3] ne "done" } @in;
  my $s = sprintf "  %s: %d of %d done", $title, $done, scalar @in;
  # Steps side by side with the same lane and state share one "(lane, state)": "P8, P7a (platform, not started)".
  my @runs; for (@open) { my $ls = "$_->[0], " . (state_of($_) =~ s/^needs you:.*/needs you/r);   # its note: NEEDS YOU
    if (@runs && $runs[-1][1] eq $ls) { push @{ $runs[-1][0] }, $_->[1] } else { push @runs, [[$_->[1]], $ls] } }
  # As many as the screen holds, then how many more (never a bare "…" through one).
  my @items = map { join(", ", @{ $_->[0] }) . " ($_->[1])" } @runs;
  if (@items) {
    my $all = $s . " · open: " . join(", ", @items);
    if (length $all <= 120) { $s = $all }
    else {
      my $left = () = map { @{ $_->[0] } } @runs; my $line = $s . " · open:"; my $sep = " ";
      for my $i (0 .. $#runs) {
        my @st = @{ $runs[$i][0] };
        my $piece = join(", ", @st) . " ($runs[$i][1])";
        my $more = $left - @st;
        last if length("$line$sep$piece") + ($more ? length(", +$more more") : 0) > 120;
        $line .= "$sep$piece"; $sep = ", "; $left = $more }
      $s = $line . ($sep eq " " ? " " : ", ") . "+$left more" } }
  print "$s\n" }

print "VIEW 1 · FOUNDATION FEATURES\n", ($full ? "\n" : "");
for my $f ("Ingest Studio", "Four places, the Glass and Admin", "Cases and drawing boards", "Rules and alerting",
    "Models and maps", "Laurium") { group($f, grep { ($feat{k($_)} // "") eq $f } @prog) }
print "\n" unless $full;

print "VIEW 2 · DEPLOYMENT\n", ($full ? "\n" : "");
my $small = $rel{small} // "unknown"; $small =~ s/ \(.*// unless $full;
my @deps = (["Local-lite", "Local-lite"], ["Small", "Small (osprey-small runs $small)"],
  ["Client install", $full ? "Client install (cloud-platform profile, shape: poc)" : "Client install"],
  ["After the client'"'"'s install", $full ? "After the client'"'"'s install (the deferred steps)" : "After the client'"'"'s install"]);
for my $d (@deps) { group($d->[1], grep { ($dep{k($_)} // "") eq $d->[0] } @prog) }
print "\n" unless $full;

print "RELEASE\n";
my @m = rows($ENV{P_MERGES}); my $how = shift @m;
if (!$full) {
  my $count = ($how && $how->[0] eq "from")
    ? sprintf("%d merge%s since %s", scalar @m, @m == 1 ? "" : "s", $how->[1])
    : sprintf("merges since: not known (cut %s not in this repository)", ($how && $how->[1]) || "(none)");
  print cut(sprintf("  %s, published %s · %s · next: %s", $rel{last} // "unknown", $rel{published} // "unknown", $count,
    $rel{next} // "not set"), 120), "\n\n";
} else { printf "  Last: %s, published %s\n", $rel{last} // "unknown", $rel{published} // "unknown" }
if (!$full) { }
elsif ($how && $how->[0] eq "from") {
  printf "  Merged on main since (%d merge%s after %s):\n", scalar @m, @m == 1 ? "" : "s", $how->[1];
  for (@m) { my ($date, $subj) = @$_; my $lane = $subj =~ /^merge\((?:lane\/)?([^)]*)\)/ ? $1 : "";
    $subj =~ s/^[^:]*:\s*//; $subj =~ s/(?:;| \(| — ).*//;
    my ($y, $mo, $dd) = split /-/, $date; my @mn = qw(Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec);
    printf "    %d %s · %s%s\n", $dd, $mn[$mo - 1], cut($subj, 60), $lane ? " ($lane)" : "" }
} else { printf "  Merged since: not known (the release cut %s is not in this repository)\n", ($how && $how->[1]) || "(none)" }
printf "  Next: %s\n\n", $rel{next} // "not set" if $full;   # the short view has it on its one line

print "HOUSEKEEPING\n\n";
block("Housekeeping", grep { ($feat{k($_)} // "") eq "Housekeeping" && ($dep{k($_)} // "") eq "Housekeeping" } @prog);

my @loose = grep { !defined $feat{k($_)} } @prog;
if (@loose) { print "NOT IN GROUPS.TSV\n\n"; block("Not grouped", @loose) }

print "LANES\n";
printf "  %-11s %-8s %-12s %-62s %s\n", "Lane", "Account", "Session", "On now", "Next";
for my $l (@lanes) {
  my ($lane, undef, undef, $acct, $where) = @$l; my $cur = $on{$lane};
  my $now = defined $cur ? sprintf("%s (%s / %s)", $cur, $feat{"$lane\t$cur"} // "ungrouped", $dep{"$lane\t$cur"} // "ungrouped") : "-";
  my @mine = grep { $_->[0] eq $lane } @prog; my $i = 0;
  if (defined $cur) { for (0 .. $#mine) { if ($mine[$_][1] eq $cur) { $i = $_ + 1; last } } }
  my ($nx) = grep { $_->[3] ne "done" && (!defined $cur || $_->[1] ne $cur) } @mine[$i .. $#mine];
  printf "  %-11s %-8s %-12s %-62s %s\n", $lane, $acct, $where, cut($now, 62), $nx ? $nx->[1] : "free" }
print $full ? "\nThe short view: lanes_heartbeat.sh · lane by lane: lanes_heartbeat.sh --lanes\n"
  : "\nEvery block in full: lanes_heartbeat.sh --full · lane by lane: lanes_heartbeat.sh --lanes\n";
'

# The route view (ROUTE_052.md, "The heartbeat's route view"): one screen, nothing else needing reading.
route_view() {
  local lanes needs lane st note
  lanes="$(mktemp "$DIR/.route.XXXXXX")"; needs="$(mktemp "$DIR/.routeneeds.XXXXXX")"
  # shellcheck disable=SC2064   # these files, now
  trap "rm -f '$lanes' '$needs'" EXIT
  NEEDS_COPY="$needs" show >/dev/null
  if [ -n "${OVERVIEW_NEEDS:-}" ]; then cp "$needs" "$OVERVIEW_NEEDS"; fi
  for lane in $LANES; do
    st="$(field state "$DIR/$lane.beat" || true)"; note="$(field note "$DIR/$lane.beat" || true)"
    printf '%s\t%s\t%s\n' "$lane" "${st:--}" "$note" >> "$lanes"
  done
  P_CLOCK="$(clock)" P_NOW="$(now)" P_PROGRESS="$PROGRESS" P_ROUTE="$ROUTE" P_OWNER_DUE="$OWNER_DUE" \
    P_AUDIT="$AUDIT" P_LANES="$lanes" P_NEEDS="$needs" P_DIR="$DIR" perl -CSD -e "$STAGES_PL$ROUTE_PL"
  rm -f "$lanes" "$needs"; trap - EXIT
}

# shellcheck disable=SC2016   # perl, not the shell, expands these
ROUTE_PL='
use strict; use warnings; use utf8; use Encode (); use POSIX qw(floor strftime); use Time::Local qw(timegm);
sub rows { my ($f) = @_; my @r; open(my $h, "<:encoding(UTF-8)", $f) or return @r;
  while (<$h>) { chomp; next if /^#/ || !/\S/; push @r, [split /\t/, $_, -1] } return @r }
sub cut { my ($s, $n) = @_; return $s if length $s <= $n; $s = substr($s, 0, $n - 1); $s =~ s/\s+\S*$//; return "$s…" }
sub day_of { my ($d) = @_; my ($y, $m, $dd) = split /-/, $d; return floor(timegm(0, 0, 12, $dd, $m - 1, $y) / 86400) }
sub said { my ($d) = @_; my ($y, $m, $dd) = split /-/, $d;
  return strftime("%a %e %b", 0, 0, 12, $dd, $m - 1, $y - 1900) =~ s/  / /r }
sub bar { my ($frac, $w) = @_; $frac = 0 if $frac < 0; $frac = 1 if $frac > 1; my $f = int($frac * $w + 0.5);
  return "[" . ("█" x $f) . ("░" x ($w - $f)) . "]" }
sub plural { my ($n, $one) = @_; return "$n $one" . ($n == 1 ? "" : "s") }
sub names { my ($note, $step) = @_; return $note =~ /(?<![A-Za-z0-9.\-])\Q$step\E(?![A-Za-z0-9\-])/ }

my $today = floor($ENV{P_NOW} / 86400);
my ($release, $target) = ("the release", undef);
if (open(my $h, "<:encoding(UTF-8)", $ENV{P_ROUTE})) {
  while (<$h>) { chomp; ($release, $target) = ($1, $2) if /^# target\t([^\t]+)\t(\d{4}-\d\d-\d\d)/ } }
my @route = grep { @$_ >= 8 } rows($ENV{P_ROUTE});
my @progress = grep { @$_ >= 5 } rows($ENV{P_PROGRESS});
my %status; $status{"$_->[0]:$_->[1]"} = $_->[3] for @progress;
my %beat; for (grep { @$_ >= 3 } rows($ENV{P_LANES})) { $beat{$_->[0]} = [$_->[1], $_->[2]] }

# Each step: its state from its lane`s own progress row ("done" only when merged, its gates passed) and beat
# (blocked when the lane is blocked naming it), and a bar from the lane`s stages where they name its step.
my (@done, @risk);
for my $r (@route) {
  my ($id, $title, $lane, $start, $end, $crit, $after, $prog) = @$r;
  my ($plane, $pstep) = $prog =~ /^([^:]+):(.+)$/ ? ($1, $2) : (undef, undef);
  my $st = defined $pstep ? ($status{"$plane:$pstep"} // "todo") : "todo";
  # In review: built, its gates passed, waiting to merge (the owner, 13 Nov: never "running"); done only when merged.
  my $state = $st eq "done" ? "done" : $st eq "review" ? "built, waiting to merge"
    : $st eq "building" ? "running" : "not started";
  if ($state ne "done" && defined $pstep && ($beat{$plane}[0] // "") eq "blocked"
      && names($beat{$plane}[1], $pstep)) { $state = "blocked" }
  my ($frac, $staged, @listed) = ($state eq "done" || $state =~ /^built/ ? 1 : 0, "");
  if ($state ne "done" && $state !~ /^built/ && defined $pstep) {
    my ($step, @s) = stages_of($plane, $pstep);
    if (defined $step && $step eq $pstep && @s) {
      my ($at) = ((grep { $_->[1] eq "now" } @s), (grep { $_->[1] eq "blocked" } @s),
                  (grep { $_->[1] eq "todo" } @s));
      my $n = $at ? $at->[0] : scalar @s; $frac = $n / @s; $staged = "stage $n of " . scalar @s;
      # The owner`s rule: from the lanes` own records. A stage done or under way is the step running,
      # though its progress row says todo; blocked still wins, and done comes from the merged row alone.
      $state = "running" if $state eq "not started" && grep { $_->[1] eq "done" || $_->[1] eq "now" } @s;
      @listed = @s if $state eq "running" || $state eq "blocked" } }
  push @$r, $state, $frac, $staged, \@listed;
  push @done, $r if $state eq "done";
  push @risk, $r if $state ne "done" && $crit eq "y" && day_of($end) < $today;
}

my $first = (sort { $a <=> $b } map { day_of($_->[3]) } @route)[0] // $today;
my $last = defined $target ? day_of($target) : $today;
my $total = $last - $first + 1; my $used = $today - $first + 1;
$used = 0 if $used < 0; $used = $total if $used > $total;
my $left = $last - $today;
my $word = (@done < @route && $today > $last) ? "late" : @risk ? "at risk" : "on track";
print "OSPREYFLOW · $ENV{P_CLOCK}\n";
printf "ROUTE TO %s · %s · %s · %s\n", uc $release, (defined $target ? said($target) : "no date"),
  ($left >= 0 ? plural($left, "day") . " left" : plural(-$left, "day") . " past"), $word;
my $built = grep { $_->[8] =~ /^built/ } @route;
printf "  %s %d of %d steps done%s · %s day %d of %d\n", bar(@route ? @done / @route : 0, 20), scalar @done,
  scalar @route, ($built ? " · $built built, waiting to merge" : ""), bar($total ? $used / $total : 0, 13), $used, $total;
if (my ($r) = sort { day_of($a->[4]) <=> day_of($b->[4]) } @risk) {
  my $more = @risk > 1 ? sprintf(" (+%d more at risk)", @risk - 1) : "";
  print cut(sprintf("  At risk: %s %s (%s) was due %s", $r->[0], $r->[1], $r->[2], said($r->[4])),
    118 - length $more), "$more\n" }
print "\n";

# Each row, and under a running or blocked one its stages by name (the owner, 13 Nov: "stage 5 of 5" says nothing
# without them). One screen, 40 lines: the rows are printed after the lists below are made, so their room is what the
# lists leave. Past it, each row`s done stages fold to one "✅ n done" line; then its stages still to do to one
# "— n to do" line; then each row`s list is one line (the done and the still to do counted, the stage under way or
# blocked named); then rows from the last lose their lists, those steps counted.
my %mark = (done => "✅", now => "⏳", todo => "—", blocked => "⛔");
my @rows;
for my $r (@route) {
  my ($id, $title, $lane, $start, $end, $crit, $after, $prog, $state, $frac, $staged, $listed) = @$r;
  my (undef, $sd, $smo) = split / /, said($start); my (undef, $ed, $emo) = split / /, said($end);
  my $dates = $smo eq $emo ? ($sd eq $ed ? "$ed $emo" : "$sd–$ed $emo") : "$sd $smo–$ed $emo";
  my $late = $today - day_of($end);
  # The state, then only what is worth saying: its stage, days behind, what it waits on; then its title.
  my @said = ($staged ? "$state, $staged" : $state);
  push @said, plural($late, "day") . " behind" if $state ne "done" && $late > 0;
  push @said, "after $after" if $state ne "done" && $after ne "-" && $after ne "";
  my $line = sprintf("  %-3s %s %-12s %-9s %s %s · %s", $id, ($crit eq "y" ? "★" : " "), $lane, $dates,
    bar($frac, 6), join(" · ", @said), $title);
  push @rows, [cut($line, 120), $listed];
}
sub stage_line { my ($n, $st, $name, $nt) = @{ $_[0] };
  return cut(sprintf("        %s %s. %s%s", $mark{$st} // "?", $n, $name, defined $nt && $nt ne "" ? " · $nt" : ""), 120) }
sub lines_of { my ($fold, $listed) = @_; my @s = @$listed; return () unless @s;
  return map { stage_line($_) } @s if $fold == 0;
  if ($fold == 3) {   # one line: the done counted, the stage under way or blocked named, the rest counted
    my @at = grep { $_->[1] eq "now" || $_->[1] eq "blocked" } @s;
    my $done = grep { $_->[1] eq "done" } @s; my $todo = grep { $_->[1] eq "todo" } @s;
    return cut("        " . join(" · ", ($done ? "✅ $done done" : ()),
      (map { "$mark{$_->[1]} $_->[0]. $_->[2]" } @at), ($todo ? "— $todo to do" : ())), 120) }
  my @done = grep { $_->[1] eq "done" } @s; my @todo = grep { $_->[1] eq "todo" } @s;
  my @rest = grep { $_->[1] ne "done" && ($fold < 2 || $_->[1] ne "todo") } @s;
  return ((@done ? ("        ✅ " . scalar(@done) . " done") : ()), (map { stage_line($_) } @rest),
          ($fold >= 2 && @todo ? ("        — " . scalar(@todo) . " to do") : ())) }
my $head_lines = 4 + (@risk ? 1 : 0);
my $tail = ""; open(my $tail_fh, ">:encoding(UTF-8)", \$tail) or die; my $screen = select($tail_fh);

sub listed { my ($cap, @items) = @_; my @shown = @items[0 .. ($#items < $cap - 1 ? $#items : $cap - 1)];
  print "  ", cut($_, 116), "\n" for @shown; printf "  +%d more\n", @items - @shown if @items > @shown }
my @due = grep { @$_ >= 4 && $_->[3] eq "open" } rows($ENV{P_OWNER_DUE});
my @owner = map { said($_->[1]) . " · $_->[2]" } sort { $a->[1] cmp $b->[1] } grep { $_->[0] eq "owner" } @due;
my @needs; if (open(my $h, "<:encoding(UTF-8)", $ENV{P_NEEDS})) { @needs = grep { /\S/ } map { s/\s+$//r } <$h> }
my @you = (@needs, @owner);   # what a lane says needs you first: never behind "+N more"
print "WAITING ON YOU · ", (@you ? scalar @you : "nothing"), "\n"; listed(3, @you);
my @orch = map { said($_->[1]) . " · $_->[2]" } sort { $a->[1] cmp $b->[1] }
  grep { $_->[0] eq "orchestrator" } @due;
print "WAITING ON THE ORCHESTRATOR · ", (@orch ? scalar(@orch) . " open" : "nothing"), "\n"; listed(4, @orch);

my @audit = grep { @$_ >= 4 } rows($ENV{P_AUDIT});
if (@audit) {
  my $settled = grep { $_->[2] !~ /pending/ } @audit; my %in; $in{$_->[3]}++ for @audit;
  my @in = map { "$in{$_} $_" } grep { $in{$_} } ("yes", "no", "owner to decide");
  push @in, map { "$in{$_} $_" } grep { !/^(yes|no|owner to decide)$/ } sort keys %in;
  printf "AUDIT RULINGS %s %d of %d settled · in %s: %s\n", bar($settled / @audit, 10), $settled,
    scalar @audit, $release, join(", ", @in) }

my %onroute = map { $_->[7] => 1 } @route; my %outside;
for (@progress) { my ($lane, $step, undef, $st) = @$_;
  push @{ $outside{$lane} }, $step if $st ne "done" && !$onroute{"$lane:$step"} }
my @lanes = sort keys %outside; my $count = 0; $count += @{ $outside{$_} } for @lanes;
print "OUTSIDE THIS ROUTE · ", ($count ? plural($count, "step") : "nothing"), "\n";
listed(3, map { "$_: " . join(", ", @{ $outside{$_} }) } @lanes);

my $merged = grep { $_->[3] eq "done" } @progress;
printf "FINISHED %s %d of %d steps merged\n", bar(@progress ? $merged / @progress : 0, 20), $merged,
  scalar @progress;
print "Other views: lanes_heartbeat.sh --overview · --full · --lanes · summary\n";
select($screen); close $tail_fh; $tail = Encode::decode("UTF-8", $tail);
my $room = 40 - $head_lines - 1 - scalar(split /\n/, $tail);
my ($fold, @under, $shown, $hidden) = (0);
for my $f (0 .. 3) { $fold = $f; @under = map { [lines_of($f, $_->[1])] } @rows;
  $shown = @rows; $shown += @$_ for @under; last if $shown <= $room }
$hidden = 0;
for (my $i = $#under; $i >= 0 && $shown > $room - 1; $i--) {
  next unless @{ $under[$i] }; $shown -= @{ $under[$i] }; $hidden++; $under[$i] = [] }
for my $i (0 .. $#rows) { print $rows[$i][0], "\n"; print "$_\n" for @{ $under[$i] } }
printf "        +%s more running, their stages left out to keep one screen\n", plural($hidden, "step") if $hidden;
print "\n", $tail;
'

notify() {
  local msg="$1"
  if command -v osascript >/dev/null 2>&1; then
    osascript -e "display notification \"${msg//\"/\'}\" with title \"OspreyFlow lanes\"" >/dev/null 2>&1 || true
  fi
}

# OSPREY_WATCH_PASSES stops after that many passes (the test's; unset, it runs until Ctrl-C).
watch_loop() {
  local every="${1:-300}" view="${2:-}" prev="$DIR/.needs.prev" pass=0 seen="$DIR/.needs.watch.$$"
  : > "$prev"
  while true; do
    clear 2>/dev/null || true
    echo "OspreyFlow lanes · $(date '+%H:%M:%S') · every ${every}s · Ctrl-C to stop"; echo
    if [ "$view" = "--full" ]; then
      show; cp "$DIR/.needs" "$seen"
    else
      # What needs the owner first, by show's reading, kept for the notifications: the route, else the overview.
      if [ -f "$ROUTE" ]; then OVERVIEW_NEEDS="$seen" route_view; else OVERVIEW_NEEDS="$seen" overview; fi
    fi
    # notify only for lines that are new since the last pass
    if [ -s "$seen" ]; then
      while IFS= read -r line; do
        if ! grep -qxF -- "$line" "$prev"; then notify "$line"; fi
      done < "$seen"
    fi
    cp "$seen" "$prev"; rm -f "$seen"
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

case "${1:-}" in
  "") if [ -f "$ROUTE" ]; then route_view; else overview; fi ;;
  --overview) overview ;;
  --full) overview --full ;;
  stages) shift; stages "$@" ;;
  --lanes) shift; show "${1:-}" ;;
  beat) shift; beat "$@" ;;
  nudge) shift; nudge "$@" ;;
  show) shift; show "${1:-}" ;;
  summary) summary ;;
  watch) shift; case "${1:-}" in --full) watch_loop "${2:-300}" --full ;; *) watch_loop "${1:-300}" "${2:-}" ;; esac ;;
  *) echo "usage: lanes_heartbeat.sh [--full] | --lanes [--full] | beat <lane> <state> \"<note>\" | stages <lane> \"<step>\" \"<n>|<state>|<name>[|<note>]\" ... | stages <lane> --clear \"<step>\" | stages <lane> --clear --all | nudge <lane> \"<message>\" | show | summary | watch [seconds] [--full] | watch --full [seconds]" >&2; exit 2 ;;
esac
