#!/usr/bin/env bash
# Rule 15 for the batch job wired into the App (ADR-151): each plant breaks one thing the App's jsdom case
# (src/App.batchExpand.test.tsx) or the keyboard case from the cap's refusal (keyboard/canvas-expand-cap.spec.ts)
# proves, and that case must go red; then all is put back and both are green. Run from the repository root at a
# clean commit, with this lane's local Playwright slot (OSPREY_PORTS_SLOT, the orchestrator's: 3). The registry's
# ids are applied from registry-ADR151.patch for the run and put back after it (a shared file, not committed).
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
WS=OspreyFlow_Core/apps/workspace
APP=$WS/src/App.tsx
CANVAS=$WS/src/canvas/GlassCanvas.tsx
UI=$WS/src/workingset/BatchExpansion.tsx
REG=$WS/keyboard/actionRegistry.ts
: "${OSPREY_PORTS_SLOT:?set the Playwright slot of this lane}"
git diff --quiet -- "$APP" "$CANVAS" "$UI" "$REG" || { echo "commit first: the plants restore from HEAD"; exit 2; }
git apply OspreyFlow_Build/process/lanes/case-b/registry-ADR151.patch || exit 2
trap 'git checkout -q HEAD -- "$REG"' EXIT
fails=0
jsdom() { (cd "$WS" && npx vitest run src/App.batchExpand.test.tsx 2>&1); }
keys() { (cd "$WS" && npx playwright test --config keyboard/playwright.config.ts canvas-expand-cap.spec.ts --workers=1 --reporter=line --grep "run as a batch job by keyboard" 2>&1); }

plant() { # name, file, perl substitution, runner, a pattern the named case's failure matches
  local name="$1" file="$2" sub="$3" runner="$4" red="$5" out
  perl -0pi -e "$sub" "$file"
  if git diff --quiet -- "$file"; then echo "PLANT DID NOT APPLY: $name"; fails=1; return; fi
  out="$($runner)"
  git checkout -q HEAD -- "$file"
  if grep -qE "$red" <<<"$out"; then
    echo "AS IT MUST BE (red): $name"
    grep -m1 -E "AssertionError|Error:" <<<"$out" | sed 's/^ */    /'
  else
    echo "NOT RED FOR ITS REASON: $name"; grep -E "✓|×|FAIL|Tests |passed|failed|›" <<<"$out" | tail -8; fails=1
  fi
}

plant "the App giving the canvas no batch handler" "$APP" \
  's/bearerToken && investigationId && lens === null\n/false\n/' \
  jsdom "FAIL  src/App.batchExpand.test.tsx > .* > opens the batch job's panel"
plant "a batch job offered while a view is open" "$APP" \
  's/bearerToken && investigationId && lens === null\n/bearerToken \&\& investigationId\n/' \
  jsdom "FAIL  src/App.batchExpand.test.tsx > .* > offers no batch job while a view is open"
plant "the job's result not shown as the lens" "$APP" \
  's/(key=\{batchExpansion.asked\}.*?)showLens\(opened\);/$1/s' \
  jsdom "FAIL  src/App.batchExpand.test.tsx > .* > opens the batch job's panel"
plant "the canvas handing up another depth than the one refused" "$CANVAS" \
  's/onRunExpansionAsBatch\(\{ nodeId, edgeType, depth, refused \}\)/onRunExpansionAsBatch({ nodeId, edgeType, depth: depth + 1, refused })/' \
  keys "^\s+[0-9]+\) .*› an expansion past the cap is run as a batch job by keyboard"
plant "the panel's Close out of the Tab order" "$UI" \
  's/<button type="button" className="btn" onClick=\{onClose\}>/<button type="button" className="btn" tabIndex={-1} onClick={onClose}>/' \
  keys "^\s+[0-9]+\) .*› an expansion past the cap is run as a batch job by keyboard"

a="$(jsdom)"; k="$(keys)"
if grep -q "Tests  2 passed" <<<"$a" && grep -qE "^\s+1 passed" <<<"$k" && ! grep -qE "^\s+[0-9]+ failed" <<<"$k"; then
  echo "unplanted: App jsdom 2 passed, keyboard 1 passed"
else echo "UNPLANTED NOT GREEN"; grep -E "Tests |passed|failed" <<<"$a$k"; fails=1; fi
[ "$fails" = 0 ] && echo "every plant red for its reason, unplanted green" || { echo "SOME PLANT WRONG"; exit 1; }
