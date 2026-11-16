#!/usr/bin/env bash
# v0.6.1 glass-rows B (ADR-145 Amendment 19 decisions 1-4): each plant puts one fault into the real code, in the shape
# its own call site has, runs the cases that prove it, and must see them red; then the file is put back from HEAD.
# Unplanted, the same cases are green. Run from the worktree root on a clean tree; local Playwright slot 7.
set -u
ROOT="$(git rev-parse --show-toplevel)"; W="$ROOT/OspreyFlow_Core/apps/workspace"; cd "$W"
export OSPREY_PORTS_SLOT=7 LANG=en_GB.UTF-8 CI=1
git -C "$ROOT" diff --quiet || { echo "Refused: the tree is not clean." >&2; exit 2; }
git -C "$ROOT" apply "$ROOT/OspreyFlow_Build/process/lanes/case/glass-rows/registry-glass-rows.patch"
trap 'git -C "$ROOT" checkout -q -- "$W/keyboard/actionRegistry.ts"' EXIT
fails=0
plant() { # name file python-old python-new vitest-files vitest-grep keyboard-specs keyboard-grep
  local name="$1" file="$2" old="$3" new="$4" vfiles="$5" vgrep="$6" kspecs="$7" kgrep="$8" red=0
  python3 - "$file" "$old" "$new" <<'PY' || { echo "PLANT $name: its shape is not in $2" ; fails=$((fails+1)); return; }
import sys
p, old, new = sys.argv[1:]
s = open(p).read()
assert s.count(old) == 1, f"{old!r} found {s.count(old)} times"
open(p, "w").write(s.replace(old, new))
PY
  if [ -n "$vfiles" ]; then npx vitest run $vfiles -t "$vgrep" >/tmp/plant.$$ 2>&1 || red=$((red+1)); fi
  if [ -n "$kspecs" ]; then npx playwright test --config keyboard/playwright.config.ts $kspecs -g "$kgrep" --reporter=line >/tmp/plant.$$ 2>&1 || red=$((red+1)); fi
  git -C "$ROOT" checkout -q -- "$W/$file"
  local want=0; [ -n "$vfiles" ] && want=$((want+1)); [ -n "$kspecs" ] && want=$((want+1))
  if [ "$red" -eq "$want" ]; then echo "red   $name"; else echo "GREEN $name (red $red of $want)"; fails=$((fails+1)); fi
}
plant "App passes no state to the case line" src/App.tsx 'caseState={caseState}' 'caseState={null}' \
  src/App.views.test.tsx "said on the case line" "" ""
plant "the saved view's name takes no focus" src/views/SavedViewOnTheLine.tsx 'if (id !== null) named.current?.focus();' 'if (id === "") named.current?.focus();' \
  src/shell/caseLine.test.tsx "takes focus to its name" views.spec "ospreyflow dark 1440"
plant "Esc does not close Details" src/shell/ContextBanner.tsx 'if (event.key !== "Escape" || !detailsOpen) return;' 'if (event.key !== "Escape" || detailsOpen) return;' \
  src/shell/caseLine.test.tsx "Esc closes it" views.spec "closed by Esc"
plant "Details without the count" src/views/SavedViewOnTheLine.tsx '{note && <p className="case-line-details__line">{note}</p>}' '' \
  src/shell/caseLine.test.tsx "Details opens over the canvas" views.spec "closed by Esc"
plant "the fold wraps after the name (no steps 4 and 5, as before ruling 10)" src/shell/ContextBanner.tsx '      setFold((current) => ({ ...current, step: current.step + 1 }));' '      setFold((current) => ({ ...current, step: current.step === 3 ? 6 : current.step + 1 }));' \
  "" "" views.spec "1024: a saved view"
plant "Back to the whole case low on contrast" src/shell/places.css 'text-decoration: underline; text-underline-offset: 2px; cursor: pointer; font: inherit;
}
:is(.context-banner, .context-banner--govuk) .govuk-back-link.context-banner__whole' 'text-decoration: underline; text-underline-offset: 2px; cursor: pointer; font: inherit; color: var(--border-subtle);
}
:is(.context-banner, .context-banner--govuk) .govuk-back-link.context-banner__whole' \
  "" "" views.spec "contrast probe \\(dark\\)"
plant "the slim line keeps reads" src/shell/ContextBanner.tsx '{place === "glass" && datasets && !slim && (' '{place === "glass" && datasets && (' \
  src/shell/caseLine.test.tsx "drops You are in and reads" "" ""
plant "the canvas pushed by a strip again" src/App.tsx '            {/* ADR-145 Amendment 19: no strip over the canvas; what is open is said on the case line (`caseState`). */}' '            {view === "graph" && investigationId && <div role="region" aria-label="The whole case" className="view-lens-banner">You are looking at the whole case.</div>}' \
  src/App.views.test.tsx "said on the case line" "" ""
echo "unplanted:"
npx vitest run src/shell/caseLine.test.tsx src/App.views.test.tsx >/tmp/plant.$$ 2>&1 && echo "green vitest" || { echo "RED vitest unplanted"; fails=$((fails+1)); }
npx playwright test --config keyboard/playwright.config.ts views.spec --reporter=line >/tmp/plant.$$ 2>&1 && echo "green views.spec" || { echo "RED views.spec unplanted"; fails=$((fails+1)); }
rm -f /tmp/plant.$$
echo "plants failing to go red, or unplanted red: $fails"; exit "$fails"
