#!/usr/bin/env bash
# Rule 15 for v0.6.1 glass-rows A and C (ADR-145 Amendment 19 decisions 5 and 6). The red-first runs are in gates/
# (a-*-reds.log, c-*-reds.log), each taken before its code. Here each plant breaks one rule in the code's own shape at its
# real call site, and the named cases go red; restored from saved copies, never `git checkout`. The keyboard cases apply
# the registry's ids from registry.patch for the run. Run from the repository root, with OSPREY_PORTS_SLOT.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
WS=OspreyFlow_Core/apps/workspace
HERE=OspreyFlow_Build/process/lanes/case-b/v061-glass-rows-ac
APP=$WS/src/App.tsx
CANVAS=$WS/src/canvas/GlassCanvas.tsx
CTRL=$WS/src/resolution/ThresholdControl.tsx
VIS=$WS/src/canvas/toolbarVisibility.ts
COMPACT=$WS/src/canvas/toolbarCompact.ts
TOGGLE=$WS/src/canvas/ToolbarToggle.tsx
CSS=$WS/src/design/primitives.css
KEYS=$WS/src/welcome/WorkspaceWelcome.tsx
REG=$WS/keyboard/actionRegistry.ts
FILES=("$APP" "$CANVAS" "$CTRL" "$VIS" "$COMPACT" "$TOGGLE" "$CSS" "$KEYS" "$REG")
: "${OSPREY_PORTS_SLOT:?set the Playwright slot of this lane}"
SAVED="$(mktemp -d)"
cp "$REG" "$SAVED/registry-as-found.ts"
grep -q '"hide-and-show-the-toolbar-by-keyboard"' "$REG" || git apply "$HERE/registry.patch" || exit 2
for f in "${FILES[@]}"; do cp "$f" "$SAVED/$(basename "$f")"; done
restore() { for f in "${FILES[@]}"; do cp "$SAVED/$(basename "$f")" "$f"; done; }
trap 'restore; cp "$SAVED/registry-as-found.ts" "$REG"; rm -rf "$SAVED"' EXIT
fails=0
js() { (cd "$WS" && npx vitest run src/App.chrome.test.tsx src/resolution src/canvas/toolbarVisibility.test.ts src/welcome/WorkspaceWelcome.test.tsx 2>&1); }
kb() { (cd "$WS" && npx playwright test --config keyboard/playwright.config.ts keyboard.spec.ts -g "Match strictness|Hide toolbar is reached|Alt\+Shift\+T on the canvas" --workers=2 --reporter=line 2>&1); }
gt() { (cd "$WS" && npx playwright test --config keyboard/playwright.config.ts glass-toolbar.spec.ts --workers=4 --reporter=line 2>&1); }
red() { grep -E "×|^\s+[0-9]+\) |^FAILED" <<<"$1" | grep -qF "$2"; }
check() {
  local name="$1" out="$2" cases="$3" c ok=1
  while IFS= read -r c; do [ -z "$c" ] && continue; red "$out" "$c" || { ok=0; echo "NOT RED FOR ITS REASON: $name (wanted: $c)"; }; done <<<"$cases"
  if [ "$ok" = 1 ]; then echo "AS IT MUST BE (red): $name"; while IFS= read -r c; do [ -n "$c" ] && echo "    $c"; done <<<"$cases"
  else grep -E "×|Tests |passed|failed|^FAILED" <<<"$out" | head -6; fails=1; fi
}
plant() {
  local name="$1" file="$2" sub="$3" runner="$4" cases="$5" out
  perl -0pi -e "$sub" "$file"
  if cmp -s "$file" "$SAVED/$(basename "$file")"; then echo "PLANT DID NOT APPLY: $name"; fails=1; return; fi
  out="$($runner)"; restore
  check "$name" "$out" "$cases"
}

echo "== A: Match strictness in the canvas toolbar"
plant "A1 strictness back in the Graph's own row" "$APP" \
  's/\{view === "map" && \(\n(\s*\/\/ ADR-097 step 1)/{(view === "map" || view === "graph") \&\& (\n$1/; s/(<div role="toolbar" aria-label=)"Map view"( className="view-toolbar")/$1\{view === "graph" ? "Graph view" : "Map view"\}$2/' js \
  "the Graph draws no row of its own"
plant "A2 the control handed to no toolbar" "$CANVAS" \
  's/\{toolbarAfterLayout && <div className="canvas-toolbar__group">\{toolbarAfterLayout\}<\/div>\}//' kb \
  "Match strictness is reached by Tab in the canvas toolbar"
plant "A3 the short words never taken" "$CTRL" 's/const compact = useContext\(CanvasToolbarCompact\);/const compact = false;/' js \
  "on a narrow toolbar shows the shorter words"
plant "A4 the toolbar's width not measured into its words" "$CANVAS" 's/if \(width > 0\) setToolbarCompact\(isCompactToolbar\(width\)\);/setToolbarCompact(false);/' gt \
  "at 1219 px of toolbar (dark) the words are short
at 1024 px of toolbar (govuk) the words are short"
plant "A5 the rulings' 1132 px line" "$COMPACT" 's/TOOLBAR_COMPACT_BELOW_PX = 1220;/TOOLBAR_COMPACT_BELOW_PX = 1132;/' gt \
  "at 1219 px of toolbar (dark) the words are short"
plant "A6 the captions kept on a narrow toolbar" "$CANVAS" 's/\{!toolbarCompact && (<span className="canvas-toolbar__label" aria-hidden="true">Layout<\/span>)\}/$1/' gt \
  "at 1024 px of toolbar (dark) the words are short"
plant "A7 Last change back in View, wrapping the row" "$CSS" 's/flex: 1 1 0; min-width: 0; text-align: right;/flex: 0 0 auto; min-width: 0; text-align: right;/' gt \
  "at 1240 px of toolbar (dark) the words are whole"
plant "A8 an unchanged stop sent again" "$CTRL" 's/if \(!detent \|\| detent\.value === threshold\) return;/if (!detent) return;/' js \
  "sends nothing: the setting it already has is not re-projected"

echo "== C: a toolbar that can be hidden"
plant "C1 the canvas toolbar never hidden" "$CANVAS" 's/hidden=\{toolbarHidden\}\n/hidden={false}\n/' gt \
  "hidden means out of the tab order and the accessibility tree"
plant "C2 hidden only by the attribute the toolbar's display overrides" "$CSS" 's/\.canvas-toolbar\[hidden\], \.view-toolbar\[hidden\] \{ display: none; \}\n//' gt \
  "hidden means out of the tab order and the accessibility tree
the Map's row hides the same way"
plant "C3 focus left where it was" "$VIS" 's/\(which === "show" \? showRef : hideRef\)\.current\?\.focus\(\);//' kb \
  "Hide toolbar is reached by Tab and pressed with Enter
Alt+Shift+T on the canvas hides the toolbar"
plant "C4 one setting for every analyst" "$VIS" 's/`ospreyflow\.glass\.toolbar\.\$\{username\}`/"ospreyflow.glass.toolbar"/' js \
  "is kept under ospreyflow.glass.toolbar.<username>
is one analyst's"
plant "C5 hidden on the Drawing board too" "$VIS" 's/const hidden = here && setting;/const hidden = setting;/' js \
  "the Drawing board is not hidden"
plant "C6 the key heard where there is no toolbar" "$VIS" 's/if \(!here\) return;\n(\s*const onKey)/$1/' js \
  "the Drawing board is not hidden"
plant "C7 the key heard in a text field" "$VIS" 's/if \(target && \(\["INPUT", "TEXTAREA", "SELECT"\]\.includes\(target\.tagName\) \|\| target\.isContentEditable\)\) return;//' js \
  "Alt+Shift+T hides and shows it"
plant "C8 Ctrl+Shift+T taken as well" "$VIS" 's/event\.altKey && event\.shiftKey && !event\.ctrlKey && !event\.metaKey/(event.altKey || event.ctrlKey) \&\& event.shiftKey \&\& !event.metaKey/' js \
  "is not Ctrl+Shift+T
Alt+Shift+T hides and shows it"
plant "C9 the Map's row never hidden" "$APP" 's/(id=\{VIEW_TOOLBAR_ID\}) hidden=\{toolbarHidden\}>/$1>/' js \
  "the Map has the same control and the same setting"
plant "C10 the case line not slimmed" "$APP" 's/slim=\{toolbarHidden\}/slim={false}/' js \
  "Hide toolbar hides the canvas toolbar, slims the case line"
plant "C11 Show toolbar not saying what it controls" "$TOGGLE" 's/(Show toolbar.*?\n.*?)aria-controls=\{VIEW_TOOLBAR_ID\}/$1/s; s/(className=\{govuk \? "govuk-link toolbar-toggle toolbar-toggle--show".*?\n\s*aria-expanded=\{false\}\n)\s*aria-controls=\{VIEW_TOOLBAR_ID\}\n/$1/s' js \
  "Hide toolbar hides the canvas toolbar"
plant "C12 nothing hidden where storage is refused or nobody signed in" "$VIS" 's/  thisPage\.set\(username \?\? "", hidden\);\n//' js \
  "is not remembered for nobody, but still hides for this page
still hides for this page where the browser's storage refuses it"
plant "C13 the key not listed in ?" "$KEYS" 's/  \["Alt\+Shift\+T", "Hide or show the toolbar \(Option\+Shift\+T on a Mac\)"\],\n//' js \
  "lists the keys worth knowing"
plant "C15 the width read off the toolbar, 0 while it is hidden (the first build's shape)" "$CANVAS" 's/const width = containerRef\.current\?\.getBoundingClientRect\(\)\.width \?\? 0;\n(\s*)if \(width > 0\) setToolbarCompact\(isCompactToolbar\(width\)\);/setToolbarCompact(isCompactToolbar(bar.getBoundingClientRect().width));/' gt \
  "hiding and showing moves the drawing area's top once each way, by the toolbar's height, keeping the graph's centre and zoom (640 px)"

echo "== unplanted: every case green"
out="$(js)"; grep -E "Tests " <<<"$out"; grep -q "×" <<<"$out" && { echo "UNPLANTED RED (jsdom)"; fails=1; }
out="$(kb)"; grep -E "passed|failed" <<<"$out" | tail -2; grep -q "failed" <<<"$out" && { echo "UNPLANTED RED (keyboard)"; fails=1; }
out="$(gt)"; grep -E "passed|failed" <<<"$out" | tail -2; grep -q "failed" <<<"$out" && { echo "UNPLANTED RED (glass-toolbar)"; fails=1; }
exit $fails
