#!/usr/bin/env bash
# Rule 15 for ADR-044 Amendment 2's offline cases (tests/services/api/test_unreachable_in_a_row.py): each plant breaks
# one rule in the code's own shape, and the named case must go red on its own; then all is put back and green.
# Restored from a saved copy, never `git checkout` (the orchestrator, 14 Nov: a server copy's .git can be stale).
# Run from the repository root. Offline: the closed ports, no lane. The store's own column and reset are the
# live cases' (test_hotlists.py, test_monitors.py), planted in plants-live.sh on a leased stack.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
CORE=OspreyFlow_Core
EVAL=$CORE/services/api/evaluation.py
SCHED=$CORE/services/api/monitor_schedule.py
WORDS=$CORE/services/api/watch_status.py
TEST=../OspreyFlow_Build/tests/services/api/test_unreachable_in_a_row.py
SAVED="$(mktemp -d)"; for f in "$EVAL" "$SCHED" "$WORDS"; do cp "$f" "$SAVED/$(basename "$f")"; done
restore() { for f in "$EVAL" "$SCHED" "$WORDS"; do cp "$SAVED/$(basename "$f")" "$f"; done; }
trap 'restore; rm -rf "$SAVED"' EXIT
fails=0
run() { (cd "$CORE" && env -u OSPREY_LANE ARCADEDB_HTTP_PORT=59991 POSTGRES_PORT=59992 POSTGRES_PASSWORD=throwaway \
  VALKEY_PORT=59993 CLICKHOUSE_HTTP_PORT=59994 .venv/bin/pytest -c ../OspreyFlow_Build/pytest.ini -q -p no:cacheprovider -rf "$TEST" 2>&1); }
plant() { # name, file, perl substitution, the case that must go red (a substring of its id)
  local name="$1" file="$2" sub="$3" case="$4" out
  perl -0pi -e "$sub" "$file"
  if cmp -s "$file" "$SAVED/$(basename "$file")"; then echo "PLANT DID NOT APPLY: $name"; fails=1; return; fi
  out="$(run)"; restore
  if grep -qE "^FAILED .*::$case" <<<"$out"; then
    echo "AS IT MUST BE (red): $name"; grep -E "^FAILED .*::$case" <<<"$out" | sed -E 's/^FAILED [^:]+::/    /; s/ - .*//'
  else echo "NOT RED FOR ITS REASON: $name (wanted $case)"; grep -E "^FAILED|passed|failed" <<<"$out" | head -5; fails=1; fi
}
plant "one unreachable load stops it (ADR-044 before Amendment 2)" "$EVAL" \
  's/    if why != "unreachable":\n        return False/    if True:\n        return False/' \
  "test_one_unreachable_load_leaves_it_active_counted_once_and_matches_nothing"
plant "the second in a row stops it (the bound one short)" "$EVAL" \
  's/if in_a_row < UNREACHABLE_STOPS_AT:/if in_a_row < UNREACHABLE_STOPS_AT - 1:/' \
  "test_two_in_a_row_leave_it_active_counted_twice"
plant "the third in a row leaves it active (the bound one long)" "$EVAL" \
  's/if in_a_row < UNREACHABLE_STOPS_AT:/if in_a_row <= UNREACHABLE_STOPS_AT:/' \
  "test_the_third_in_a_row_stops_it_unreachable"
plant "another reason counted as unreachable is" "$EVAL" \
  's/    if why != "unreachable":\n        return False/    if why is None:\n        return False/' \
  "test_another_reason_at_the_first_load_stops_it_at_once_uncounted"
plant "a schedule giving its slot back counts" "$SCHED" \
  's/(            await reply\(self.valkey.delete\(claim\)\)\n            return)/            await self.monitors.count_unreachable(monitor.id)\n$1/' \
  "test_a_schedule_giving_its_slot_back_neither_counts_nor_resets"
plant "a schedule giving its slot back resets" "$SCHED" \
  's/(            await reply\(self.valkey.delete\(claim\)\)\n            return)/            await self.monitors.set_status(monitor.id, "active")\n$1/' \
  "test_a_schedule_giving_its_slot_back_neither_counts_nor_resets"
plant "a schedule acting as the owner leaves the count (resets only where it matches)" "$SCHED" \
  's/        await self.monitors.set_status\(monitor.id, "active"\)\n        if monitor.dataset_id is None:/        if monitor.dataset_id is None:/' \
  "test_a_schedule_that_acts_as_the_owner_puts_the_count_back_even_matching_nothing"
plant "the active note says nothing of how many" "$WORDS" \
  's/"Its owner.s sign-in could not be checked at the last two loads. "/"Its owner\x27s sign-in could not be checked at the last load. "/' \
  "test_the_words_for_an_active_watch_with_misses_and_none_without"
out="$(run)"
if grep -qE "[0-9]+ passed" <<<"$out" && ! grep -qE "[0-9]+ failed" <<<"$out"; then echo "unplanted: $(grep -E '[0-9]+ passed' <<<"$out" | tail -1)"; else echo "UNPLANTED NOT GREEN"; fails=1; fi
[ "$fails" = 0 ] && echo "every plant red for its reason, unplanted green" || { echo "SOME PLANT WRONG"; exit 1; }
