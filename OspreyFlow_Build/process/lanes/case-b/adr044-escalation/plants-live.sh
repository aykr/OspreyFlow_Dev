#!/usr/bin/env bash
# Rule 15 for ADR-044 Amendment 2's live store cases (test_hotlists.py, test_monitors.py), on a leased stack's
# Postgres: the whole two files unplanted first (so nothing else in them broke), then each plant in the store's own
# SQL, its case red; restored from a saved copy, never `git checkout` (a server copy's .git can be stale). Run from
# the repository root under `stack_lease.sh remote`, which pins the stack's ports.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
CORE=OspreyFlow_Core
H=$CORE/services/api/hotlists.py
M=$CORE/services/api/monitors.py
T="../OspreyFlow_Build/tests/services/api/test_hotlists.py ../OspreyFlow_Build/tests/services/api/test_monitors.py"
SAVED="$(mktemp -d)"; cp "$H" "$SAVED/hotlists.py"; cp "$M" "$SAVED/monitors.py"
restore() { cp "$SAVED/hotlists.py" "$H"; cp "$SAVED/monitors.py" "$M"; }
trap 'restore; rm -rf "$SAVED"' EXIT
fails=0
run() { (cd "$CORE" && .venv/bin/pytest -c ../OspreyFlow_Build/pytest.ini -q -p no:cacheprovider -rf $T -k "$1" 2>&1); }
echo "== unplanted, both files whole"
(cd "$CORE" && .venv/bin/pytest -c ../OspreyFlow_Build/pytest.ini -q -p no:cacheprovider -rf $T 2>&1) | grep -E "^FAILED|passed|failed" | sed 's/ - .*//'
plant() { # name, file, perl substitution, the case (-k)
  local name="$1" file="$2" sub="$3" case="$4" out
  perl -0pi -e "$sub" "$file"
  if cmp -s "$file" "$SAVED/$(basename "$file")"; then echo "PLANT DID NOT APPLY: $name"; fails=1; return; fi
  out="$(run "$case")"; restore
  if grep -qE "^FAILED .*$(basename "$file" .py).*$case" <<<"$out"; then echo "AS IT MUST BE (red): $name"; grep -m1 -E "^E  " <<<"$out" | sed 's/^/    /'
  else echo "NOT RED FOR ITS REASON: $name"; grep -E "^FAILED|passed|failed" <<<"$out" | head -4; fails=1; fi
}
plant "the hotlist's count not put back by set_status" "$H" \
  's/THEN \$3 END, unreachable_in_a_row = 0 WHERE id = \$1/THEN \$3 END WHERE id = \$1/' \
  "test_the_unreachable_count_outlives_a_restart_and_any_status_puts_it_back"
plant "the hotlist's count answered, not kept (gone at a restart)" "$H" \
  's/"UPDATE hotlists SET unreachable_in_a_row = unreachable_in_a_row \+ 1 WHERE id = \$1 "\n                "RETURNING unreachable_in_a_row"/"SELECT unreachable_in_a_row + 1 FROM hotlists WHERE id = \$1"/' \
  "test_the_unreachable_count_outlives_a_restart_and_any_status_puts_it_back"
plant "the watch's count not put back by set_status" "$M" \
  's/THEN \$3 END, unreachable_in_a_row = 0 WHERE id = \$1/THEN \$3 END WHERE id = \$1/' \
  "test_the_unreachable_count_outlives_a_restart_and_any_status_puts_it_back"
plant "the watch's count answered, not kept" "$M" \
  's/"UPDATE monitors SET unreachable_in_a_row = unreachable_in_a_row \+ 1 WHERE id = \$1 "\n                "RETURNING unreachable_in_a_row"/"SELECT unreachable_in_a_row + 1 FROM monitors WHERE id = \$1"/' \
  "test_the_unreachable_count_outlives_a_restart_and_any_status_puts_it_back"
[ "$fails" = 0 ] && echo "every live plant red for its reason" || { echo "SOME PLANT WRONG"; exit 1; }
