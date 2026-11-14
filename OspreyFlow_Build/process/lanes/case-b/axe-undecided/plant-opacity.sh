#!/usr/bin/env bash
# Rule 15 for the axe-undecided guard: the limited-suggestions line faded with `opacity: 0.35`, the
# shape axe leaves `incomplete` (its background cannot be read through the fade). Read as main read
# it, violations only, the planted scan passes; through checkUndecidedContrast it is red. Then the
# spec is run unplanted. Run from the repository root at a clean commit, with OSPREY_PORTS_SLOT set.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
WS=OspreyFlow_Core/apps/workspace
CSS=$WS/src/design/primitives.css
SPEC=$WS/keyboard/top-bar.spec.ts
: "${OSPREY_PORTS_SLOT:?set the Playwright slot of this lane}"
git diff --quiet -- "$CSS" "$SPEC" || { echo "commit first: the plants restore from HEAD"; exit 2; }
run() { (cd "$WS" && npx playwright test --config keyboard/playwright.config.ts keyboard/top-bar.spec.ts --workers=1 --reporter=line ${1:+--grep "$1"} 2>&1); }
LOOKS="says its suggestions are limited when the index did not answer"
fails=0
printf '\n.global-search__limited { opacity: 0.35; }\n' >> "$CSS"

perl -0pi -e 's/    const contrast = await checkUndecidedContrast\(page, results\);\n    expect\(contrast.unlisted, "colour contrast axe left undecided"\).toEqual\(\[\]\);\n//' "$SPEC"
git diff --quiet -- "$SPEC" && { echo "PLANT DID NOT APPLY: violations only"; exit 1; }
out="$(run "$LOOKS")"
if grep -qE "^\s+3 passed" <<<"$out" && ! grep -qE "^\s+[0-9]+ failed" <<<"$out"; then
  echo "AS MAIN READ IT (violations only), the faded line passes in every look: $(grep -E '^\s+[0-9]+ passed' <<<"$out" | xargs)"
else echo "VIOLATIONS-ONLY NOT GREEN"; grep -E "passed|failed|Error" <<<"$out" | head; fails=1; fi
git checkout -q HEAD -- "$SPEC"

out="$(run "$LOOKS")"
if grep -qE "^\s+3 failed" <<<"$out"; then
  echo "AS IT MUST BE (red) through checkUndecidedContrast, in every look:"
  grep -E "global-search__limited" <<<"$out" | sort -u | head -3 | sed 's/^ */    /'
else echo "NOT RED THROUGH THE CHECK"; grep -E "passed|failed" <<<"$out"; fails=1; fi
git checkout -q HEAD -- "$CSS"

out="$(run)"
if grep -qE "^\s+[0-9]+ passed" <<<"$out" && ! grep -qE "^\s+[0-9]+ failed" <<<"$out"; then
  echo "unplanted: $(grep -E '^\s+[0-9]+ passed' <<<"$out" | xargs)"
else echo "UNPLANTED NOT GREEN"; grep -E "passed|failed" <<<"$out"; fails=1; fi
[ "$fails" = 0 ] && echo "the faded line passes violations alone and fails the check; unplanted green" || { echo "SOME STEP WRONG"; exit 1; }
