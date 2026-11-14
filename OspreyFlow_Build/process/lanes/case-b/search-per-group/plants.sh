#!/usr/bin/env bash
# Rule 15 for the search results page's line that the counts are each group's own (the owner, 14 November 2026):
# each plant breaks one thing SearchResults.test.tsx's three cases hold, and that case must go red on its own words;
# then all is put back and green. Run from the repository root at a clean commit.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
WS=OspreyFlow_Core/apps/workspace
UI=$WS/src/search/SearchResults.tsx
TEST=src/search/SearchResults.test.tsx
git diff --quiet -- "$UI" || { echo "commit first: the plants restore from HEAD"; exit 2; }
trap 'git checkout -q HEAD -- "$UI"' EXIT
fails=0
run() { (cd "$WS" && npx vitest run "$TEST" 2>&1); }
plant() { # name, perl substitution, the case (as vitest names it), the failure's words (regex)
  local name="$1" sub="$2" case="$3" why="$4" out
  perl -0pi -e "$sub" "$UI"
  if git diff --quiet -- "$UI"; then echo "PLANT DID NOT APPLY: $name"; fails=1; return; fi
  out="$(run)"
  git checkout -q HEAD -- "$UI"
  if grep -qF "FAIL  $TEST > $case" <<<"$out" && grep -qE "$why" <<<"$out"; then
    echo "AS IT MUST BE (red, for its reason): $name"; grep -m1 -E "$why" <<<"$out" | sed 's/^ */    /'
  else echo "NOT RED FOR ITS REASON: $name (wanted: $case)"; grep -E "×|Tests " <<<"$out" | head -6; fails=1; fi
}
plant "the line left out" \
  's/\{counts && counts.groups.length > 1 && \(/{false \&\& (/' \
  "says the counts are each group's own where there is more than one group" "Unable to find an element with the text"
plant "the line said with one group, where it is noise" \
  's/counts.groups.length > 1 && \(\n            <p/counts.groups.length > 0 \&\& (\n            <p/' \
  "says nothing of it with one group, where All and the group count the same records" "expected .* to be null"
plant "the line in the OspreyFlow look's class under GOV.UK" \
  's/govuk \? "govuk-body-s search-results__per-group" : /false ? "govuk-body-s search-results__per-group" : /' \
  "under the GOV.UK brand > says the counts are each group's own in the GOV.UK look's body text" "to contain 'govuk-body-s'"
out="$(run)"
if grep -qE "Tests  [0-9]+ passed" <<<"$out" && ! grep -qE "Tests .*failed" <<<"$out"; then echo "unplanted: $(grep -E 'Tests ' <<<"$out" | xargs)"; else echo "UNPLANTED NOT GREEN"; fails=1; fi
[ "$fails" = 0 ] && echo "every plant red for its reason, unplanted green" || { echo "SOME PLANT WRONG"; exit 1; }
