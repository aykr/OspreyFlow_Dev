#!/usr/bin/env bash
# Rule 15 for the views list's `first_item` (ADR-145 Amendment 17; tests/services/api/test_case_views.py): each plant
# breaks one rule in `case_views.first_item` in the code's own shape, and the named case goes red; restored from a
# saved copy. Offline: the closed ports, no lane. Run from the repository root.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
CORE=OspreyFlow_Core
F=$CORE/services/api/case_views.py
SAVED="$(mktemp -d)"; cp "$F" "$SAVED/case_views.py"
trap 'cp "$SAVED/case_views.py" "$F"; rm -rf "$SAVED"' EXIT
fails=0
run() { (cd "$CORE" && env -u OSPREY_LANE ARCADEDB_HTTP_PORT=59991 POSTGRES_PORT=59992 POSTGRES_PASSWORD=throwaway \
  VALKEY_PORT=59993 CLICKHOUSE_HTTP_PORT=59994 .venv/bin/pytest -c ../OspreyFlow_Build/pytest.ini -q -p no:cacheprovider -rf \
  ../OspreyFlow_Build/tests/services/api/test_case_views.py 2>&1); }
plant() { # name, perl substitution, the case
  local name="$1" sub="$2" case="$3" out
  perl -0pi -e "$sub" "$F"
  if cmp -s "$F" "$SAVED/case_views.py"; then echo "PLANT DID NOT APPLY: $name"; fails=1; return; fi
  out="$(run)"; cp "$SAVED/case_views.py" "$F"
  if grep -qE "^FAILED .*::$case" <<<"$out"; then echo "AS IT MUST BE (red): $name"; grep -m1 -E "^FAILED .*::$case" <<<"$out" | sed -E 's/^FAILED [^:]+::/    /; s/ - .*//'
  else echo "NOT RED FOR ITS REASON: $name (wanted $case)"; grep -E "^FAILED|passed|failed" <<<"$out" | head -4; fails=1; fi
}
plant "the first item read past the access step (any reader's first node named)" \
  's/seen = \{n.id: n for n in await graph.get_nodes\(candidates, principal\)\}/seen = {n.id: n for n in await graph.get_nodes(candidates, principal.model_copy(update={"clearance": "SECRET"}))}/' \
  "test_a_hidden_first_item_is_never_named_and_the_next_the_reader_may_see_is"
plant "the first item in the store's id order, not the order chosen" \
  's/return next\(\(canvas_label\(seen\[n\]\) for n in candidates if n in seen\), None\)/return next((canvas_label(n) for n in seen.values()), None)/' \
  "test_a_views_first_item_is_its_first_chosen_node_by_name"
plant "a view's whole selection read for its first item (no bound)" \
  's/candidates = \[n for n in view.node_ids if n not in added\]\[:FIRST_ITEM_READ\]/candidates = [n for n in view.node_ids if n not in added]/' \
  "test_a_views_first_item_is_read_within_its_bound"
plant "a filtered view given a first item" \
  's/    if view.node_ids is None:\n        return None\n/    if view.node_ids is None:\n        return view.name\n/' \
  "test_a_filtered_view_has_no_first_item"
out="$(run)"
if grep -qE "[0-9]+ passed" <<<"$out" && ! grep -qE "[0-9]+ failed" <<<"$out"; then echo "unplanted: $(grep -E '[0-9]+ passed' <<<"$out" | tail -1)"; else echo "UNPLANTED NOT GREEN"; fails=1; fi
[ "$fails" = 0 ] && echo "every plant red for its reason, unplanted green" || { echo "SOME PLANT WRONG"; exit 1; }
