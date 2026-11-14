#!/usr/bin/env bash
# Rule 15 for the batch job's panel under axe inside the real Glass (keyboard/batch-expansion-app.spec.ts): each
# plant breaks the panel's contrast, its name, or what is on top of it, ONLY inside the App's layout, scoped by
# what the App alone draws (its classification strip, a sibling of the panel, or the App's own markup around the
# panel). The named App case must go red with its own failure (each plant's expected words are checked, not only
# that the case failed); where a plant is scoped to one look, the same state in another look must stay green; and
# the panel's own harness scan (batch-expansion.spec.ts) must stay green under the same plant, which is what shows
# the App-layout scan sees what the harness cannot. Then all is put back and the App's nine are green.
# Run from the repository root at a clean commit, with the lane's Playwright slot (OSPREY_PORTS_SLOT: 3). Output is
# kept whole; nothing is filtered out of it, and the record picks lines from it.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
WS=OspreyFlow_Core/apps/workspace
APP=$WS/src/App.tsx
CSS=$WS/src/design/primitives.css
: "${OSPREY_PORTS_SLOT:?set the Playwright slot of this lane}"
git diff --quiet -- "$APP" "$CSS" || { echo "commit first: the plants restore from HEAD"; exit 2; }
trap 'git checkout -q HEAD -- "$APP" "$CSS"' EXIT
fails=0
pw() { (cd "$WS" && npx playwright test --config keyboard/playwright.config.ts "$1" --workers=1 --reporter=line ${2:+--grep "$2"} 2>&1); }
app_case() { echo "the batch job's panel in the App, $1, has no automated WCAG 2.2 A or AA violation \\($2\\)"; }

plant() { # name, file, perl substitution, state, look, expected failure (regex), control look ("" for none), harness grep
  local name="$1" file="$2" sub="$3" state="$4" look="$5" why="$6" control="$7" harness="$8" app own ctl title
  perl -0pi -e "$sub" "$file"
  if git diff --quiet -- "$file"; then echo "PLANT DID NOT APPLY: $name"; fails=1; return; fi
  title="$(app_case "$state" "$look")"
  app="$(pw batch-expansion-app.spec.ts "$state.*\\($look\\)")"
  [ -n "$control" ] && ctl="$(pw batch-expansion-app.spec.ts "$state.*\\($control\\)")"
  own="$(pw batch-expansion.spec.ts "$harness")"
  git checkout -q HEAD -- "$file"
  if grep -qE "^\s+[0-9]+\) .*› $title" <<<"$app" && grep -qE "$why" <<<"$app"; then
    echo "AS IT MUST BE (red in the App, for its reason): $name"
    grep -m1 -E "$why" <<<"$app" | sed 's/^ */    /'
  else
    echo "NOT RED FOR ITS REASON: $name (wanted: $title, failing on /$why/)"; grep -E "passed|failed|Error:" <<<"$app" | tail -6; fails=1
  fi
  if [ -n "$control" ]; then
    if grep -qE "^\s+1 passed" <<<"$ctl" && ! grep -qE "^\s+[0-9]+ failed" <<<"$ctl"; then
      echo "    the same state in the App, $control, same plant: green (the plant is the $look look's)"
    else echo "    CONTROL RED: $state in $control under the $look plant"; fails=1; fi
  fi
  if grep -qE "^\s+[0-9]+ passed" <<<"$own" && ! grep -qE "^\s+[0-9]+ failed" <<<"$own"; then
    echo "    the panel's own harness scan, same plant: $(grep -E '^\s+[0-9]+ passed' <<<"$own" | xargs)"
  else
    echo "    HARNESS ALSO RED (the plant is not App-only): $name"; grep -E "passed|failed" <<<"$own"; fails=1
  fi
}

plant "the stage's words 1:1 against the panel, in the App's layout only" "$CSS" \
  's/(\.batch-expansion__status \{ margin: 0 0 var\(--sp-8\); font-weight: 600; \})/$1\n.classification-strip ~ .batch-expansion .batch-expansion__status { color: var(--surface-raised); opacity: 0.6; }/' \
  running dark '1\.00:1 < 4\.5:1 \(axe: equalRatio\)' "" "running, has no automated.*\\(dark\\)"
plant "the failure's words faint, in the App's GOV.UK layout only" "$CSS" \
  's/(\.batch-expansion__message \{ margin: 0 0 var\(--sp-12\); font-weight: 600; \})/$1\n[data-brand="govuk"] .classification-strip ~ .batch-expansion .batch-expansion__message { color: #c8c8c8; }/' \
  failed govuk 'batch-expansion__message: 1\.[0-9]+:1 < 4\.5:1' dark "failed, has no automated.*\\(govuk\\)"
plant "the job's words faint, in the App's light layout only" "$CSS" \
  's/(\.batch-expansion__status \{ margin: 0 0 var\(--sp-8\); font-weight: 600; \})/$1\n[data-theme="light"] .classification-strip ~ .batch-expansion .batch-expansion__status { color: #d0d0d0; }/' \
  done light 'batch-expansion__status: 1\.[0-9]+:1 < 4\.5:1|"id": "color-contrast"' dark "done, has no automated.*\\(light\\)"
plant "the panel drawn under the App's page, in the App's layout only" "$CSS" \
  's/(\.batch-expansion__actions \{)/.classification-strip ~ .batch-expansion { z-index: -1; }\n$1/' \
  done light "is covered by the App's layout" "" "done, has no automated.*\\(light\\)"
plant "an opaque App overlay the pointer passes through, over the panel's foot" "$CSS" \
  's/(\.batch-expansion__actions \{)/.classification-strip::after { content: ""; position: fixed; right: 0; bottom: 0; width: 60vw; height: 60vh; background: #000; z-index: 30; pointer-events: none; }\n$1/' \
  done dark "is covered by the App's layout" "" "done, has no automated.*\\(dark\\)"
# Red at the case's closing check (the region reached by role and name, as assistive technology reaches it), not at
# axe: the scan is held to the panel by `include`, and the `aria-hidden` ancestor is outside it.
plant "the panel hidden from assistive technology by the App's markup around it" "$APP" \
  's/(      \{bearerToken && batchExpansion.asked && \()\n(        <BatchExpansion\n)/$1<div aria-hidden="true">\n$2/; s/(          onClose=\{batchExpansion.close\}\n        \/>\n)(      \)\})/$1        <\/div>\n$2/' \
  done dark 'toBeFocused\(\) failed' "" "done, has no automated.*\\(dark\\)"
# The App draws an element with the panel's heading's id before the panel, so the panel's `aria-labelledby` names
# it with that element's words: red at the closing check (the region by its name), since no axe rule in these
# tags requires a region's name to be its heading's.
plant "the panel named by another element of the App's (its heading's id taken first)" "$APP" \
  's/(      \{bearerToken && batchExpansion.asked && \()/      <span id="batch-expansion-title" hidden>Jobs<\/span>\n$1/' \
  running dark 'toBeFocused\(\) failed' "" "running, has no automated.*\\(dark\\)"

app="$(pw batch-expansion-app.spec.ts)"
if grep -qE "^\s+9 passed" <<<"$app" && ! grep -qE "^\s+[0-9]+ failed" <<<"$app"; then
  echo "unplanted: $(grep -E '^\s+[0-9]+ passed' <<<"$app" | xargs)"
else echo "UNPLANTED NOT GREEN"; grep -E "passed|failed" <<<"$app"; fails=1; fi
[ "$fails" = 0 ] && echo "every plant red in the App for its reason, its control and the harness green, unplanted green" || { echo "SOME PLANT WRONG"; exit 1; }
