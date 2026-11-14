#!/usr/bin/env bash
# Rule 15 for the batch job's keyboard and axe cases (keyboard/batch-expansion.spec.ts): each plant
# breaks what one case proves, in the panel itself, and that case must go red with its words kept;
# then all is put back and the whole spec is green. Run from the repository root at a clean commit,
# with this lane's local Playwright slot (OSPREY_PORTS_SLOT, the orchestrator's: 3).
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
WS=OspreyFlow_Core/apps/workspace
UI=$WS/src/workingset/BatchExpansion.tsx
CSS=$WS/src/design/primitives.css
SPEC=keyboard/batch-expansion.spec.ts
: "${OSPREY_PORTS_SLOT:?set this lane's Playwright slot}"
git diff --quiet -- "$UI" "$CSS" || { echo "commit first: the plants restore from HEAD"; exit 2; }
fails=0
run() { (cd "$WS" && npx playwright test --config keyboard/playwright.config.ts "$SPEC" --workers=1 --reporter=line ${1:+--grep "$1"} 2>&1); }

plant() { # name, file, perl substitution, grep for the cases, a case that must go red
  local name="$1" file="$2" sub="$3" grep="$4" case="$5" out
  perl -0pi -e "$sub" "$file"
  if git diff --quiet -- "$file"; then echo "PLANT DID NOT APPLY: $name"; fails=1; return; fi
  out="$(run "$grep")"
  git checkout -q HEAD -- "$file"
  if grep -qE "^\s+[0-9]+\) .*› $case" <<<"$out"; then
    echo "AS IT MUST BE (red): $name"
    grep -m1 -E "Error:|expect\(" <<<"$out" | sed 's/^ */    /'
    grep -m1 -E '"id": "' <<<"$out" | sed 's/^ */    axe: /'
  else
    echo "NOT RED FOR ITS REASON: $name (wanted: $case)"; grep -E "passed|failed|›" <<<"$out" | tail -8; fails=1
  fi
}

plant "the panel not taking focus when it opens" "$UI" \
  's/headingRef.current\?\.focus\(\);/void 0;/' \
  "is closed by keyboard" "the batch job's panel is closed by keyboard while the job runs, and asks no more"
plant "Close out of the Tab order" "$UI" \
  's/<button type="button" className="btn" onClick=\{onClose\}>/<button type="button" className="btn" tabIndex={-1} onClick={onClose}>/' \
  "is closed by keyboard" "the batch job's panel is closed by keyboard while the job runs, and asks no more"
plant "Try the batch job again out of the Tab order" "$UI" \
  's/<button type="button" className="btn btn--primary" onClick=\{\(\) => setAttempt/<button type="button" className="btn btn--primary" tabIndex={-1} onClick={() => setAttempt/' \
  "tried again by keyboard" "a failed batch job is tried again by keyboard, and runs to its view"
plant "the stage's words faint against the panel (dark)" "$CSS" \
  's/\.batch-expansion__status \{ margin: 0 0 var\(--sp-8\); font-weight: 600; \}/.batch-expansion__status { margin: 0 0 var(--sp-8); font-weight: 600; color: var(--surface-raised); opacity: 0.6; }/' \
  "running, has no automated.*\\(dark\\)" "the batch job's panel, running, has no automated WCAG 2.2 A or AA violation \\(dark\\)"
plant "the refusal's words faint against the panel (GOV.UK)" "$CSS" \
  's/\.batch-expansion__message \{ margin: 0 0 var\(--sp-12\); font-weight: 600; \}/.batch-expansion__message { margin: 0 0 var(--sp-12); font-weight: 600; color: var(--surface-raised); opacity: 0.6; }/' \
  "refused, has no automated.*\\(govuk\\)" "the batch job's panel, refused, has no automated WCAG 2.2 A or AA violation \\(govuk\\)"
plant "the panel's region left without a name" "$UI" \
  's/role="region" aria-labelledby="batch-expansion-title"/role="region"/' \
  "done, has no automated.*\\(light\\)" "the batch job's panel, done, has no automated WCAG 2.2 A or AA violation \\(light\\)"

out="$(run)"
if grep -qE "^\s+[0-9]+ passed" <<<"$out" && ! grep -qE "^\s+[0-9]+ failed" <<<"$out"; then
  echo "unplanted: $(grep -E '^\s+[0-9]+ passed' <<<"$out" | xargs)"
else echo "UNPLANTED NOT GREEN"; grep -E "passed|failed" <<<"$out"; fails=1; fi
[ "$fails" = 0 ] && echo "every plant red for its reason, unplanted green" || { echo "SOME PLANT WRONG"; exit 1; }
