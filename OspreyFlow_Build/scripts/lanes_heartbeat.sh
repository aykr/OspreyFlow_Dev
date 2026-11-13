#!/usr/bin/env bash
# The lanes' heartbeat and the owner's monitor (spec/06_DECISIONS.md ADR-142 decision 9).
#
#   lanes_heartbeat.sh beat <lane> <state> "<note>"   a lane records where it is
#        state: planning | working | testing | waiting-for-owner | blocked | ready-to-merge | idle | paused
#        (a lane at its usage limit is beaten from outside as: beat <lane> blocked "usage limit")
#   lanes_heartbeat.sh nudge <lane> "<message>"     the orchestrator leaves a lane a message, shown
#                                                     to it at its next beat (a session it cannot type into)
#   lanes_heartbeat.sh                                the owner's default view (11 November 2026): the steps
#                                                     left by foundation feature and by deployment, the
#                                                     release, housekeeping, and one row per lane
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
            # Only a note that names the owner is the owner's: lanes beat this state while they wait on
            # the orchestrator (a merge, a slot, a stack), and on 10 November 2026 those reached Needs you.
            *[Oo]wner*) echo "$lane is waiting for you: $note" >> "$needs" ;;
            *) echo "$lane is waiting for the orchestrator: $note" >> "$mine" ;;
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
  local cut ref="${OSPREY_MAIN_REF:-main}"
  cut="$(awk -F'\t' '!/^#/ && $1 == "cut" { print $2; exit }' "$RELEASE" 2>/dev/null || true)"
  if [ -n "$cut" ] && git -C "$SCRIPTS_DIR" cat-file -e "$cut^{commit}" 2>/dev/null; then
    printf 'from\t%s\n' "$cut"
    git -C "$SCRIPTS_DIR" log --merges --first-parent --format='%cs%x09%s' "$cut..$ref" 2>/dev/null || true
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
  local lanes merges lane st note
  lanes="$(mktemp "$DIR/.overview.XXXXXX")"; merges="$(mktemp "$DIR/.merges.XXXXXX")"
  for lane in $LANES; do
    # A lane that has never beaten has no .beat file; under pipefail that must not end the whole view.
    st="$(field state "$DIR/$lane.beat" || true)"; note="$(field note "$DIR/$lane.beat" || true)"
    printf '%s\t%s\t%s\t%s\t%s\n' "$lane" "${st:--}" "$note" "$(account_of "$lane")" "$(where_of "$lane")" >> "$lanes"
  done
  release_merges > "$merges"
  P_CLOCK="$(clock)" P_PROGRESS="$PROGRESS" P_GROUPS="$GROUPS_FILE" P_EST="$ESTIMATES" P_RELEASE="$RELEASE" P_FINISH="$FINISH" \
    P_LANES="$lanes" P_MERGES="$merges" perl -CSD -e "$OVERVIEW_PL"
  rm -f "$lanes" "$merges"
}

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
      return "waiting for a test stack" if $bn =~ /lease/;
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

print "VIEW 1 · FOUNDATION FEATURES\n\n";
for my $f ("Ingest Studio", "Four places, the Glass and Admin", "Cases and drawing boards", "Rules and alerting",
    "Models and maps", "Laurium") { block($f, grep { ($feat{k($_)} // "") eq $f } @prog) }

print "VIEW 2 · DEPLOYMENT\n\n";
my @deps = (["Local-lite", "Local-lite"], ["Small", "Small (osprey-small runs " . ($rel{small} // "unknown") . ")"],
  ["Client install", "Client install (cloud-platform profile, shape: poc)"],
  ["After the client'"'"'s install", "After the client'"'"'s install (the deferred steps)"]);
for my $d (@deps) { block($d->[1], grep { ($dep{k($_)} // "") eq $d->[0] } @prog) }

print "RELEASE\n";
printf "  Last: %s, published %s\n", $rel{last} // "unknown", $rel{published} // "unknown";
my @m = rows($ENV{P_MERGES}); my $how = shift @m;
if ($how && $how->[0] eq "from") {
  printf "  Merged on main since (%d merge%s after %s):\n", scalar @m, @m == 1 ? "" : "s", $how->[1];
  for (@m) { my ($date, $subj) = @$_; my $lane = $subj =~ /^merge\((?:lane\/)?([^)]*)\)/ ? $1 : "";
    $subj =~ s/^[^:]*:\s*//; $subj =~ s/(?:;| \(| — ).*//;
    my ($y, $mo, $dd) = split /-/, $date; my @mn = qw(Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec);
    printf "    %d %s · %s%s\n", $dd, $mn[$mo - 1], cut($subj, 60), $lane ? " ($lane)" : "" }
} else { printf "  Merged since: not known (the release cut %s is not in this repository)\n", ($how && $how->[1]) || "(none)" }
printf "  Next: %s\n\n", $rel{next} // "not set";

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
print "\nLane by lane: lanes_heartbeat.sh --lanes\n";
'

notify() {
  local msg="$1"
  if command -v osascript >/dev/null 2>&1; then
    osascript -e "display notification \"${msg//\"/\'}\" with title \"OspreyFlow lanes\"" >/dev/null 2>&1 || true
  fi
}

# OSPREY_WATCH_PASSES stops after that many passes (the test's; unset, it runs until Ctrl-C).
watch_loop() {
  local every="${1:-300}" view="${2:-}" prev="$DIR/.needs.prev" pass=0
  : > "$prev"
  while true; do
    clear 2>/dev/null || true
    echo "OspreyFlow lanes · $(date '+%H:%M:%S') · every ${every}s · Ctrl-C to stop"; echo
    if [ "$view" = "--full" ]; then
      show
    else
      show >/dev/null   # works out what needs the owner, as the notifications below rely on
      overview
      echo
      if [ -s "$DIR/.needs" ]; then echo "NEEDS YOU:"; sed 's/^/  - /' "$DIR/.needs"; else echo "Nothing needs you."; fi
    fi
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

case "${1:-}" in
  "") overview ;;
  --lanes) shift; show "${1:-}" ;;
  beat) shift; beat "$@" ;;
  nudge) shift; nudge "$@" ;;
  show) shift; show "${1:-}" ;;
  summary) summary ;;
  watch) shift; case "${1:-}" in --full) watch_loop "${2:-300}" --full ;; *) watch_loop "${1:-300}" "${2:-}" ;; esac ;;
  *) echo "usage: lanes_heartbeat.sh [--lanes [--full]] | beat <lane> <state> \"<note>\" | nudge <lane> \"<message>\" | show | summary | watch [seconds] [--full] | watch --full [seconds]" >&2; exit 2 ;;
esac
