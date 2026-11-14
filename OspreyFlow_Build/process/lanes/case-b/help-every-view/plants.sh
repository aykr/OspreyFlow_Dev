#!/usr/bin/env bash
# Rule 15 for keyboard/help-every-view.spec.ts (CARRIES 224): each plant puts back one half of the row's defect in
# App.tsx, and the case must go red on its own words; then all is put back and green. Restored from a saved copy,
# never `git checkout` (the orchestrator, 14 Nov: a server copy's .git can be stale). The registry's id is applied
# from registry-help.patch for the run, and put back after. Run from the repository root, with OSPREY_PORTS_SLOT.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
WS=OspreyFlow_Core/apps/workspace
APP=$WS/src/App.tsx
REG=$WS/keyboard/actionRegistry.ts
HERE=OspreyFlow_Build/process/lanes/case-b/help-every-view
: "${OSPREY_PORTS_SLOT:?set the Playwright slot of this lane}"
SAVED="$(mktemp -d)"; cp "$APP" "$SAVED/App.tsx"; cp "$REG" "$SAVED/actionRegistry.ts"
trap 'cp "$SAVED/App.tsx" "$APP"; cp "$SAVED/actionRegistry.ts" "$REG"; rm -rf "$SAVED"' EXIT
grep -q "HELP_ACTIONS" "$REG" || git apply "$HERE/registry-help.patch" || exit 2
fails=0
run() { (cd "$WS" && npx playwright test --config keyboard/playwright.config.ts help-every-view.spec.ts --workers=1 --reporter=line 2>&1); }
plant() { # name, perl substitution, the failure's words
  local name="$1" sub="$2" why="$3" out
  perl -0pi -e "$sub" "$APP"
  if cmp -s "$APP" "$SAVED/App.tsx"; then echo "PLANT DID NOT APPLY: $name"; fails=1; return; fi
  out="$(run)"; cp "$SAVED/App.tsx" "$APP"
  if grep -qF "$why" <<<"$out"; then echo "AS IT MUST BE (red, for its reason): $name"; echo "    $why"
  else echo "NOT RED FOR ITS REASON: $name (wanted: $why)"; grep -E "passed|failed|Error:" <<<"$out" | head -4; fails=1; fi
}
plant "Help's panel in the Graph alone (CARRIES 224 as found)" \
  's/\(welcome === "asked" \|\| \(welcome === "auto" && view === "graph" && !lens\)\)/(view === "graph" \&\& (welcome === "asked" || (welcome === "auto" \&\& !lens)))/' \
  "Help did not open its panel in Map"
plant "Help never closing an open panel" \
  's/if \(shownWelcomeRef.current\) closeWelcomeRef.current\(\);\n    else setWelcome\("asked"\);/setWelcome("asked");/' \
  "Help did not close its panel in Graph"
out="$(run)"
if grep -qE "^\s+2 passed" <<<"$out" && ! grep -qE "^\s+[0-9]+ failed" <<<"$out"; then echo "unplanted: 2 passed"; else echo "UNPLANTED NOT GREEN"; fails=1; fi
[ "$fails" = 0 ] && echo "every plant red for its reason, unplanted green" || { echo "SOME PLANT WRONG"; exit 1; }
