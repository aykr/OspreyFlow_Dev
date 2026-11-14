#!/usr/bin/env bash
# Rule 15 for the batch job's panel under axe inside the real Glass (keyboard/batch-expansion-app.spec.ts): each
# plant breaks the panel's contrast, label or visibility ONLY inside the App's layout, scoped by what the App alone
# draws (its classification strip, a sibling of the panel; or the App's own markup around the panel). The named App
# case must go red, and the panel's own harness scan (batch-expansion.spec.ts) must stay green under the same
# plant, which is what shows the App-layout scan sees what the harness cannot. Then all is put back and green.
# Run from the repository root at a clean commit, with the lane's Playwright slot (OSPREY_PORTS_SLOT: 3). The
# registry's ids are on main (c2199bb), so nothing is applied for the run.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
WS=OspreyFlow_Core/apps/workspace
APP=$WS/src/App.tsx
CSS=$WS/src/design/primitives.css
: "${OSPREY_PORTS_SLOT:?set the Playwright slot of this lane}"
git diff --quiet -- "$APP" "$CSS" || { echo "commit first: the plants restore from HEAD"; exit 2; }
fails=0
pw() { (cd "$WS" && npx playwright test --config keyboard/playwright.config.ts "$1" --workers=1 --reporter=line ${2:+--grep "$2"} 2>&1 | grep -v '^\[WebServer\]'); }

plant() { # name, file, perl substitution, App case grep, App case title, harness grep
  local name="$1" file="$2" sub="$3" grep="$4" title="$5" harness="$6" app own
  perl -0pi -e "$sub" "$file"
  if git diff --quiet -- "$file"; then echo "PLANT DID NOT APPLY: $name"; fails=1; return; fi
  app="$(pw batch-expansion-app.spec.ts "$grep")"
  own="$(pw batch-expansion.spec.ts "$harness")"
  git checkout -q HEAD -- "$file"
  if grep -qE "^\s+[0-9]+\) .*› $title" <<<"$app"; then
    echo "AS IT MUST BE (red in the App): $name"
    grep -m1 -E "Error:|expect\(" <<<"$app" | sed 's/^ */    /'
    grep -m1 -E '"id": "|unlisted|:1 <|covered' <<<"$app" | sed 's/^ */    /'
  else
    echo "NOT RED FOR ITS REASON: $name (wanted: $title)"; grep -E "passed|failed|›" <<<"$app" | tail -6; fails=1
  fi
  if grep -qE "^\s+[0-9]+ passed" <<<"$own" && ! grep -qE "^\s+[0-9]+ failed" <<<"$own"; then
    echo "    the panel's own harness scan, same plant: $(grep -E '^\s+[0-9]+ passed' <<<"$own" | xargs)"
  else
    echo "    HARNESS ALSO RED (the plant is not App-only): $name"; grep -E "passed|failed" <<<"$own"; fails=1
  fi
}

plant "the stage's words 1:1 against the panel, in the App's layout only (dark)" "$CSS" \
  's/(\.batch-expansion__status \{ margin: 0 0 var\(--sp-8\); font-weight: 600; \})/$1\n.classification-strip ~ .batch-expansion .batch-expansion__status { color: var(--surface-raised); opacity: 0.6; }/' \
  "running.*\\(dark\\)" "the batch job's panel in the App, running, has no automated WCAG 2.2 A or AA violation \\(dark\\)" \
  "running, has no automated.*\\(dark\\)"
plant "the failure's words faint, in the App's layout only (GOV.UK)" "$CSS" \
  's/(\.batch-expansion__message \{ margin: 0 0 var\(--sp-12\); font-weight: 600; \})/$1\n[data-brand="govuk"] .classification-strip ~ .batch-expansion .batch-expansion__message { color: #c8c8c8; }/' \
  "failed.*\\(govuk\\)" "the batch job's panel in the App, failed, has no automated WCAG 2.2 A or AA violation \\(govuk\\)" \
  "failed, has no automated.*\\(govuk\\)"
plant "the panel drawn under the App's page, in the App's layout only (light)" "$CSS" \
  's/(\.batch-expansion__actions \{)/.classification-strip ~ .batch-expansion { z-index: -1; }\n$1/' \
  "done.*\\(light\\)" "the batch job's panel in the App, done, has no automated WCAG 2.2 A or AA violation \\(light\\)" \
  "done, has no automated.*\\(light\\)"
# Red at the case's closing check (the named region reached by role, as assistive technology reaches it), not at
# axe: the scan is held to the panel by `include`, and the `aria-hidden` ancestor is outside it.
plant "the panel hidden from assistive technology by the App's markup around it (dark)" "$APP" \
  's/(      \{bearerToken && batchExpansion.asked && \()\n(        <BatchExpansion\n)/$1<div aria-hidden="true">\n$2/; s/(          onClose=\{batchExpansion.close\}\n        \/>\n)(      \)\})/$1        <\/div>\n$2/' \
  "done.*\\(dark\\)" "the batch job's panel in the App, done, has no automated WCAG 2.2 A or AA violation \\(dark\\)" \
  "done, has no automated.*\\(dark\\)"

app="$(pw batch-expansion-app.spec.ts)"
if grep -qE "^\s+9 passed" <<<"$app" && ! grep -qE "^\s+[0-9]+ failed" <<<"$app"; then
  echo "unplanted: $(grep -E '^\s+[0-9]+ passed' <<<"$app" | xargs)"
else echo "UNPLANTED NOT GREEN"; grep -E "passed|failed" <<<"$app"; fails=1; fi
[ "$fails" = 0 ] && echo "every plant red in the App for its reason, the harness green under each, unplanted green" || { echo "SOME PLANT WRONG"; exit 1; }
