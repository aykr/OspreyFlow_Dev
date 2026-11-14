#!/usr/bin/env bash
# Rule 15 for the batch job's panel at the canvas's foot alone (spec 02 §3.1h; App.tsx): each plant breaks one half
# of `App.batchExpand.test.tsx`'s place case, and it must go red on its own words; then all is put back and green.
# Run from the repository root at a clean commit.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
WS=OspreyFlow_Core/apps/workspace
APP=$WS/src/App.tsx
UI=$WS/src/workingset/BatchExpansion.tsx
TEST=src/App.batchExpand.test.tsx
CASE="the panel is drawn at the canvas's foot alone"
git diff --quiet -- "$APP" "$UI" || { echo "commit first: the plants restore from HEAD"; exit 2; }
trap 'git checkout -q HEAD -- "$APP" "$UI"' EXIT
fails=0
run() { (cd "$WS" && npx vitest run "$TEST" 2>&1); }

plant() { # name, perl substitution, the failure's words (regex), the case (default: the place case), the file (default: App)
  local name="$1" sub="$2" why="$3" case="${4:-$CASE}" file="${5:-$APP}" out
  perl -0pi -e "$sub" "$file"
  if git diff --quiet -- "$file"; then echo "PLANT DID NOT APPLY: $name"; fails=1; return; fi
  out="$(run)"
  git checkout -q HEAD -- "$file"
  if grep -qF "FAIL  $TEST > an expansion the cap refused, run as a batch job (ADR-151) > $case" <<<"$out" && grep -qE "$why" <<<"$out"; then
    echo "AS IT MUST BE (red, for its reason): $name"; grep -m1 -E "$why" <<<"$out" | sed 's/^ */    /'
  else
    echo "NOT RED FOR ITS REASON: $name (wanted /$why/)"; grep -E "×|Tests |AssertionError" <<<"$out" | head -6; fails=1
  fi
}

plant "the panel drawn over every place in the case, as on main before" \
  's/<div hidden=\{view !== "graph" \|\| searching !== null \|\| readerDocumentId !== null\}>/<div>/' \
  "AssertionError: expected <section"
plant "the panel taken away off the Graph, so the way back starts another job" \
  's/\{bearerToken && batchExpansion.asked && \(\n        <div hidden=\{view !== "graph" \|\| searching !== null \|\| readerDocumentId !== null\}>/{bearerToken \&\& batchExpansion.asked \&\& view === "graph" \&\& (\n        <div>/' \
  "expected \[ \{ url: .* \} \] to have a length of 1 but got 2|to have a length of 1 but got 2"

plant "the panel drawn over the search results (they draw no view)" \
  's/ \|\| searching !== null//' \
  "expected <section" "the panel is hidden over the search results, which draw no view, and back when they close"
plant "a panel drawn again starting its job again (the job not kept by the App)" \
  's/if \(attempt === 0 && kept\) \{/if (false) {/' \
  "to have a length of 1 but got 2" "going Home and back on the same page follows the job already started, never starting it again" "$UI"

out="$(run)"
if grep -qE "Tests  10 passed" <<<"$out"; then echo "unplanted: Tests 10 passed (10)"; else echo "UNPLANTED NOT GREEN"; grep "Tests " <<<"$out"; fails=1; fi
[ "$fails" = 0 ] && echo "every plant red for its reason, unplanted green" || { echo "SOME PLANT WRONG"; exit 1; }
