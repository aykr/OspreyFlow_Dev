#!/usr/bin/env bash
# Every version of pid_plan.py on main, each run as it was (it imports only pid_names.py), both
# profiles: is any id given two types within a plan, or across versions? Run from the repository
# root; it writes nothing in the repository. Output: process/lanes/studio/reseed-types/pid_history.txt.
set -euo pipefail
work="$(mktemp -d)"
for c in $(git log --format=%h origin/main -- OspreyFlow_Core/packages/demo_fixtures/pid_plan.py); do
  d="$work/v_$c/pidpkg"; mkdir -p "$d"; touch "$d/__init__.py"
  git show "$c:OspreyFlow_Core/packages/demo_fixtures/pid_plan.py" > "$d/pid_plan.py"
  git show "$c:OspreyFlow_Core/packages/demo_fixtures/pid_names.py" > "$d/pid_names.py"
done
OspreyFlow_Core/.venv/bin/python -I "$(dirname "$0")/pid_history_audit.py" "$work"
