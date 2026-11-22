#!/usr/bin/env bash
# The one push (process/lanes/v062/slice-line/README.md, "The push step"): main to origin, only after the merge
# script has written main. Run by merge_slice.py at the end of a merge or a records commit, or by the owner;
# the guard refuses it from any agent's command.
#
# Refuses unless: this is the main checkout, on main, with HEAD written by the merge script (a Slice-Merge or
# Slice-Records trailer); origin is the URL recorded at install (~/.ospreyflow/slice-line/origin.url); and the
# push is a plain fast-forward of main:main. Never another remote, never another branch or a tag, never --force.
# Every merge is pushed (the owner, 20 November 2026), whatever GitHub's last completed run said, red included: GitHub
# always tests the newest main. Only a run on main in progress or queued holds a push back, since a new push would
# cancel it: the push waits, recorded in push.pending; the board shows it, and the conductor runs
# `merge_slice.py push-pending` when the run ends (the next merge's push also carries it); the owner can run this too.
set -euo pipefail

DATA="${OSPREY_SLICE_HOME:-$HOME/.ospreyflow/slice-line}"
BIN="$HOME/.ospreyflow/slice-line"
LOG="$DATA/push.log"
say() { printf '%s\n' "$*"; printf '%s\t%s\n' "$(date -u +%FT%TZ)" "$*" >> "$LOG"; }
mkdir -p "$DATA"

top="$(git rev-parse --show-toplevel)"
common="$(git rev-parse --path-format=absolute --git-common-dir)"
[ "$(dirname "$common")" = "$top" ] || { say "Refused: not the main checkout ($top)."; exit 2; }
[ "$(git rev-parse --abbrev-ref HEAD)" = "main" ] || { say "Refused: the main checkout is not on main."; exit 2; }
trailers="$(git log -1 --format='%(trailers:only,unfold)' HEAD)"
if ! printf '%s' "$trailers" | grep -qE '^(Slice-Merge|Slice-Records|Owner-Approved-Diff):'; then
  say "Refused: main's tip $(git rev-parse --short HEAD) was not written by the merge script."; exit 2
fi
want="$(cat "$BIN/origin.url" 2>/dev/null || true)"
[ -n "$want" ] || { say "Refused: no recorded origin URL ($BIN/origin.url); run install.sh."; exit 2; }
have="$(git remote get-url --push origin 2>/dev/null || true)"
[ "$have" = "$want" ] || { say "Refused: origin is not the recorded remote."; exit 2; }

if [ -z "${OSPREY_PUSH_NO_CI_CHECK:-}" ] && command -v gh >/dev/null 2>&1; then
  busy="$(gh run list --branch main --status in_progress --json databaseId -q 'length' 2>/dev/null || echo 0)"
  queued="$(gh run list --branch main --status queued --json databaseId -q 'length' 2>/dev/null || echo 0)"
  if [ "${busy:-0}" != "0" ] || [ "${queued:-0}" != "0" ]; then
    git rev-parse HEAD > "$DATA/push.pending"
    say "Deferred: a CI run on main is in progress or queued; $(git rev-parse --short HEAD) waits (push.pending): merge_slice.py push-pending pushes it when the run ends."
    exit 3
  fi
fi

git fetch -q origin main
if ! git merge-base --is-ancestor origin/main HEAD; then
  say "Refused: origin/main is not an ancestor of main (it would need a force)."; exit 2
fi
git push origin "refs/heads/main:refs/heads/main"
remote="$(git ls-remote origin refs/heads/main | cut -f1)"
[ "$remote" = "$(git rev-parse HEAD)" ] || { say "Pushed, but origin's main ($remote) is not HEAD."; exit 1; }
rm -f "$DATA/push.pending"
say "Pushed main $(git rev-parse --short HEAD) to origin; ls-remote matches."
