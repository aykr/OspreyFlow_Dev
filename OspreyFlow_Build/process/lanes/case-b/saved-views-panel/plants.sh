#!/usr/bin/env bash
# Rule 15 for the saved views panel (ADR-145 Amendment 17): each plant breaks one rule in ViewsPanel.tsx or App.tsx's
# Drawer block, in the code's own shape, and the named case must go red; restored from a saved copy, never `git
# checkout`. Run from the repository root, with OSPREY_PORTS_SLOT for the keyboard ones. The registry's ids are
# applied from registry-saved-views-panel.patch for the run and put back.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
WS=OspreyFlow_Core/apps/workspace
P=$WS/src/views/ViewsPanel.tsx
A=$WS/src/App.tsx
REG=$WS/keyboard/actionRegistry.ts
H=$WS/keyboard/saved-views-panel-harness.tsx
HERE=OspreyFlow_Build/process/lanes/case-b/saved-views-panel
: "${OSPREY_PORTS_SLOT:?set the Playwright slot of this lane}"
SAVED="$(mktemp -d)"; for f in "$P" "$A" "$REG" "$H"; do cp "$f" "$SAVED/$(basename "$f")"; done
restore() { cp "$SAVED/ViewsPanel.tsx" "$P"; cp "$SAVED/App.tsx" "$A"; cp "$SAVED/saved-views-panel-harness.tsx" "$H"; }
trap 'restore; cp "$SAVED/actionRegistry.ts" "$REG"; rm -rf "$SAVED"' EXIT
grep -q "SAVED_VIEWS_PANEL_ACTIONS" "$REG" || git apply "$HERE/registry-saved-views-panel.patch" || exit 2
fails=0
jsdom() { (cd "$WS" && npx vitest run src/views/ViewsPanel.test.tsx src/App.views.test.tsx src/App.chrome.test.tsx 2>&1); }
keys() { (cd "$WS" && npx playwright test --config keyboard/playwright.config.ts saved-views-panel.spec.ts --workers=1 --reporter=line 2>&1); }
plant() { # name, file, perl substitution, runner, the case's words
  local name="$1" file="$2" sub="$3" runner="$4" case="$5" out
  perl -0pi -e "$sub" "$file"
  if cmp -s "$file" "$SAVED/$(basename "$file")"; then echo "PLANT DID NOT APPLY: $name"; fails=1; return; fi
  out="$($runner)"; restore
  if grep -E "×|^\s+[0-9]+\) " <<<"$out" | grep -qF "$case"; then echo "AS IT MUST BE (red): $name"; grep -E "×|^\s+[0-9]+\) " <<<"$out" | grep -F "$case" | head -2 | sed 's/^ */    /'
  else echo "NOT RED FOR ITS REASON: $name (wanted: $case)"; grep -E "×|Tests |passed|failed" <<<"$out" | head -4; fails=1; fi
}
plant "the whole case not listed first (standard look)" "$P" \
  's/          <li className="case-views__row" data-view-id="whole-case">.*?<\/li>\n//s' \
  jsdom "starts with the whole case, open now while no saved view is open"
plant "the whole case always open now" "$P" \
  's/\{openViewId === null && <span className="view-tag view-tag--open">Open now<\/span>\}/<span className="view-tag view-tag--open">Open now<\/span>/' \
  jsdom "marks the saved view open now as Open now, and offers it no Open"
plant "the open saved view still offering Open" "$P" \
  's/      \{!isOpen && \(\n        <button/      {true \&\& (\n        <button/' \
  keys "the whole case is opened from the panel by keyboard while a saved view is open"
plant "the whole case's Open not doing what the way back does" "$A" \
  's/              onOpenWholeCase=\{\(\) => \{\n                setCasesOpen\(false\);\n                closeLens\(\);/              onOpenWholeCase={() => {\n                setCasesOpen(false);/' \
  jsdom "the Saved views drawer holds the saved views alone, and The whole case closes the open view"
plant "every view told apart, a named one too" "$P" \
  's/  if \(!DEFAULT_NAME.test\(view.name\)\) return null;\n//' \
  jsdom "tells a view saved under the default name apart"
plant "the first item not said" "$P" \
  's/view.first_item \? `\$\{view.first_item\} · saved \$\{when\}` : `Saved \$\{when\}`/`Saved \${when}`/' \
  keys "a view saved under the default name says its first item and when it was saved"
plant "the drawer still titled Cases from the case line" "$A" \
  's/title=\{casesOpen === "views" \? "Saved views" : "Cases"\}/title="Cases"/' \
  jsdom "Views in this case opens the Cases panel at its views list"
plant "the case list and Browse all cases in the Saved views drawer" "$A" \
  's/\{casesOpen !== "views" && \(\n            <>/{true \&\& (\n            <>/' \
  jsdom "the Saved views drawer holds the saved views alone"
plant "focus not given back to Saved views" "$H" \
  's/returnFocusTo=\{\(\) => document.querySelector<HTMLElement>\("\[data-saved-views-button\]"\)\}//' \
  keys "a saved view is opened from the panel by keyboard, and focus goes back to Saved views"
cp "$SAVED/ViewsPanel.tsx" "$P"
a="$(jsdom)"; k="$(keys)"
if grep -qE "Tests  [0-9]+ passed" <<<"$a" && ! grep -qE "Tests .*failed" <<<"$a" && grep -qE "^\s+10 passed" <<<"$k"; then echo "unplanted: $(grep 'Tests ' <<<"$a" | xargs); keyboard 10 passed"; else echo "UNPLANTED NOT GREEN"; fails=1; fi
[ "$fails" = 0 ] && echo "every plant red for its reason, unplanted green" || { echo "SOME PLANT WRONG"; exit 1; }
