#!/usr/bin/env bash
# Rule 15 for the batch job wired into the App (ADR-151): each plant breaks one thing the App's jsdom cases
# (src/App.batchExpand.test.tsx), the App's hold on the panel (src/workingset/useBatchExpansion.test.ts), the
# panel's StrictMode and Open the view cases (src/workingset/BatchExpansion.test.tsx) or the keyboard case from the
# cap's refusal (keyboard/canvas-expand-cap.spec.ts) proves, and that case must go red; then all is put back and
# all are green. Run from the repository root at a
# clean commit, with this lane's local Playwright slot (OSPREY_PORTS_SLOT, the orchestrator's: 3). The registry's
# ids are applied from registry-ADR151.patch for the run and put back after it (a shared file, not committed).
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
WS=OspreyFlow_Core/apps/workspace
APP=$WS/src/App.tsx
CANVAS=$WS/src/canvas/GlassCanvas.tsx
UI=$WS/src/workingset/BatchExpansion.tsx
HOOK=$WS/src/workingset/useBatchExpansion.ts
REG=$WS/keyboard/actionRegistry.ts
: "${OSPREY_PORTS_SLOT:?set the Playwright slot of this lane}"
git diff --quiet -- "$APP" "$CANVAS" "$UI" "$HOOK" "$REG" "$WS/src/workingset/batchExpansionApi.ts" || { echo "commit first: the plants restore from HEAD"; exit 2; }
git apply OspreyFlow_Build/process/lanes/case-b/registry-ADR151.patch || exit 2
trap 'git checkout -q HEAD -- "$REG"' EXIT
fails=0
jsdom() { (cd "$WS" && npx vitest run src/App.batchExpand.test.tsx 2>&1); }
hook() { (cd "$WS" && npx vitest run src/workingset/useBatchExpansion.test.ts 2>&1); }
panel() { (cd "$WS" && npx vitest run src/workingset/BatchExpansion.test.tsx 2>&1); }
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
  's/const problem = await openLens\(viewId\);/const problem = null;/' \
  jsdom "FAIL  src/App.batchExpand.test.tsx > .* > opens the batch job's panel"
plant "the job's result opened around openLens (an earlier click wins)" "$APP" \
  's/const problem = await openLens\(viewId\);/const opened = await openView(API_BASE_URL, bearerToken, batchExpansion.asked!.caseId, viewId); if (opened.ok) showLens(opened.opened); const problem = null;/' \
  jsdom "FAIL  src/App.batchExpand.test.tsx > .* > a view asked for after Open the view wins"
plant "the App holding the panel for no person" "$APP" \
  's/useBatchExpansion\(investigationId, session\?\.sub \?\? null\)/useBatchExpansion(investigationId, null)/' \
  jsdom "FAIL  src/App.batchExpand.test.tsx > .* > someone else signing in in place takes the panel away"
plant "the App letting a failed job be tried again in a view" "$APP" \
  's/mayStartAgain=\{lens === null\}/mayStartAgain/' \
  jsdom "FAIL  src/App.batchExpand.test.tsx > .* > offers no second try of a failed job once a view is open"
plant "a second choice reusing the first's panel" "$APP" \
  's/key=\{batchExpansion.asked.n\}/key="batch"/' \
  jsdom "FAIL  src/App.batchExpand.test.tsx > .* > a second choice while the first runs opens its own panel"
plant "a 409 for a second choice not followed" "$WS/src/workingset/batchExpansionApi.ts" \
  's/response.status === 409 && body.error === "batch_expansion_running"/false/' \
  jsdom "FAIL  src/App.batchExpand.test.tsx > .* > a second choice while the first runs opens its own panel"
plant "the choice kept when another case is opened" "$HOOK" \
  's/asked.caseId === caseId && asked.who === who/asked.who === who/' \
  hook "FAIL  src/workingset/useBatchExpansion.test.ts > .* > drops the choice when another case is opened"
plant "the choice kept when someone else signs in in place" "$HOOK" \
  's/asked.caseId === caseId && asked.who === who/asked.caseId === caseId/' \
  hook "FAIL  src/workingset/useBatchExpansion.test.ts > .* > drops the choice when someone else signs in in place"
plant "a choice made again given the first's count" "$HOOK" \
  's/n: \(held\?\.n \?\? 0\) \+ 1/n: 1/' \
  hook "FAIL  src/workingset/useBatchExpansion.test.ts > .* > gives a choice made again its own panel"
plant "a done job's view opened unasked" "$UI" \
  's/(      setShown\(\{ phase: "done", words: job.words, view: \{ id: job.view.id, name: job.view.name \} \}\);)/$1\n      void openResult({ id: job.view.id, name: job.view.name }, job.words);/' \
  panel "FAIL  src/workingset/BatchExpansion.test.tsx > .* > says a done job in the server's words and offers Open the view, opening nothing unasked"
plant "a second POST under StrictMode" "$UI" \
  's/if \(startedRef.current\?\.attempt !== attempt\) \{/if (true) {/' \
  panel "FAIL  src/workingset/BatchExpansion.test.tsx > .* > sends one POST under React's StrictMode"
plant "a second try offered while a view is open" "$UI" \
  's/shown.again && mayStartAgain &&/shown.again \&\&/' \
  panel "FAIL  src/workingset/BatchExpansion.test.tsx > .* > offers no second try where a batch job may not be chosen"
plant "the canvas handing up another node than the one refused" "$CANVAS" \
  's/onRunExpansionAsBatch\(\{ nodeId, edgeType, depth, refused \}\)/onRunExpansionAsBatch({ nodeId: graph.nodes().find((n) => n !== nodeId) ?? nodeId, edgeType, depth, refused })/' \
  keys "^\s+[0-9]+\) .*› an expansion past the cap is run as a batch job by keyboard"
plant "Open the view out of the Tab order" "$UI" \
  's/(<button\n            type="button"\n            className="btn btn--primary"\n            onClick=\{\(\) => void openResult)/<button tabIndex={-1}\n            type="button"\n            className="btn btn--primary"\n            onClick={() => void openResult/' \
  keys "^\s+[0-9]+\) .*› an expansion past the cap is run as a batch job by keyboard"
plant "the canvas handing up another depth than the one refused" "$CANVAS" \
  's/onRunExpansionAsBatch\(\{ nodeId, edgeType, depth, refused \}\)/onRunExpansionAsBatch({ nodeId, edgeType, depth: depth + 1, refused })/' \
  keys "^\s+[0-9]+\) .*› an expansion past the cap is run as a batch job by keyboard"
plant "a second POST under StrictMode, by keyboard" "$UI" \
  's/if \(startedRef.current\?\.attempt !== attempt\) \{/if (true) {/' \
  keys "^\s+[0-9]+\) .*› an expansion past the cap is run as a batch job by keyboard, and its result opened as the view \(StrictMode\)"
plant "focus taken from the panel while the job runs" "$UI" \
  's/(  async function watch\(jobId: string\): Promise<void> \{\n)/$1      (document.activeElement as HTMLElement | null)?.blur();\n/' \
  keys "^\s+[0-9]+\) .*› an expansion past the cap is run as a batch job by keyboard"

a="$(jsdom)"; h="$(hook)"; u="$(panel)"; k="$(keys)"
if grep -q "Tests  7 passed" <<<"$a" && grep -q "Tests  5 passed" <<<"$h" && grep -q "Tests  28 passed" <<<"$u" \
  && grep -qE "^\s+2 passed" <<<"$k" && ! grep -qE "^\s+[0-9]+ failed" <<<"$k"; then
  echo "unplanted: App jsdom 7 passed, hook 5 passed, panel 28 passed, keyboard 2 passed (plain and StrictMode)"
else echo "UNPLANTED NOT GREEN"; grep -E "Tests |passed|failed" <<<"$a$h$u$k"; fails=1; fi
[ "$fails" = 0 ] && echo "every plant red for its reason, unplanted green" || { echo "SOME PLANT WRONG"; exit 1; }
