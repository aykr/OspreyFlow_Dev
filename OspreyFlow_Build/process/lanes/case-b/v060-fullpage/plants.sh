#!/usr/bin/env bash
# Rule 15 for v0.6.0 #4, Ask & Chat as a page over the view (ADR-145 Amendment 18). First the red-on-main record: main's
# App.tsx, LeftRail.tsx and the three harnesses put back, every new case red. Then each plant breaks one rule in the code's
# own shape, and the named case goes red; restored from saved copies, never `git checkout`. The keyboard ones apply the
# registry's id from registry-v060-fullpage.patch for the run. Run from the repository root, with OSPREY_PORTS_SLOT.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
WS=OspreyFlow_Core/apps/workspace
HERE=OspreyFlow_Build/process/lanes/case-b/v060-fullpage
APP=$WS/src/App.tsx
RAIL=$WS/src/shell/LeftRail.tsx
PAGE=$WS/src/questions/AskPage.tsx
CSS=$WS/src/questions/askPage.css
HOOK=$WS/src/questions/useAskPage.ts
HARN=$WS/keyboard/places-harness.tsx
QHARN=$WS/keyboard/questions-harness.tsx
CHARN=$WS/keyboard/harness.tsx
SRHARN=$WS/keyboard/search-results-harness.tsx
SHOW=$WS/src/questions/showAnswer.ts
OVER=$WS/src/search/useSearchResultsOverlay.ts
REG=$WS/keyboard/actionRegistry.ts
FILES=("$APP" "$RAIL" "$PAGE" "$CSS" "$HOOK" "$HARN" "$QHARN" "$CHARN" "$SRHARN" "$SHOW" "$OVER" "$REG")
: "${OSPREY_PORTS_SLOT:?set the Playwright slot of this lane}"
SAVED="$(mktemp -d)"
for f in "${FILES[@]}"; do cp "$f" "$SAVED/$(basename "$f")"; done
restore() { for f in "${FILES[@]}"; do cp "$SAVED/$(basename "$f")" "$f"; done; }
cp "$REG" "$SAVED/registry-as-found.ts"
trap 'restore; cp "$SAVED/registry-as-found.ts" "$REG"; rm -rf "$SAVED"' EXIT
grep -q '"ask-and-chat-page-by-keyboard"' "$REG" || git apply "$HERE/registry-v060-fullpage.patch" || exit 2
cp "$REG" "$SAVED/actionRegistry.ts"
fails=0
js() { (cd "$WS" && npx vitest run src/App.chrome.test.tsx src/App.help.test.tsx src/App.search.test.tsx src/App.batchExpand.test.tsx 2>&1); }
kb() { (cd "$WS" && npx playwright test --config keyboard/playwright.config.ts shell.spec.ts questions.spec.ts --workers=2 --reporter=line 2>&1); }
# The stacking case (lane review 2 item 2): nothing of the canvas drawn over the Ask page, in the three looks.
st() { (cd "$WS" && npx playwright test --config keyboard/playwright.config.ts search-results.spec.ts -g "Ask & Chat's page is drawn over" --workers=1 --reporter=line 2>&1); }
# A page opened while a document is read (the orchestrator, 15 November 2026), by keyboard on the results harness.
sr() { (cd "$WS" && npx playwright test --config keyboard/playwright.config.ts search-results.spec.ts -g "while a document is read" --workers=2 --reporter=line 2>&1); }
ax() { (cd "$WS" && npx playwright test --config a11y/playwright.config.ts every-harness.spec.ts -g "places-harness.html open=questions" --workers=1 --reporter=line 2>&1); }
guide() { (cd OspreyFlow_Core && env -u OSPREY_LANE ARCADEDB_HTTP_PORT=59991 POSTGRES_PORT=59992 VALKEY_PORT=59993 CLICKHOUSE_HTTP_PORT=59994 POSTGRES_PASSWORD=throwaway \
  .venv/bin/pytest -c ../OspreyFlow_Build/pytest.ini -q -p no:cacheprovider -rf ../OspreyFlow_Build/tests/test_user_guide_ask_chat.py 2>&1); }
red() { # output, the case (a substring of its name)
  grep -E "×|^\s+[0-9]+\) |^FAILED" <<<"$1" | grep -qF "$2"
}
check() { # name, output, cases (newline-separated)
  local name="$1" out="$2" cases="$3" c ok=1
  while IFS= read -r c; do [ -z "$c" ] && continue; red "$out" "$c" || { ok=0; echo "NOT RED FOR ITS REASON: $name (wanted: $c)"; }; done <<<"$cases"
  if [ "$ok" = 1 ]; then echo "AS IT MUST BE (red): $name"; while IFS= read -r c; do [ -n "$c" ] && echo "    $c"; done <<<"$cases"
  else grep -E "×|Tests |passed|failed|^FAILED" <<<"$out" | head -6; fails=1; fi
}
plant() { # name, file, perl substitution, runner, cases (newline-separated), and optionally the failure's own words
  local name="$1" file="$2" sub="$3" runner="$4" cases="$5" reason="${6:-}" out
  perl -0pi -e "$sub" "$file"
  if cmp -s "$file" "$SAVED/$(basename "$file")"; then echo "PLANT DID NOT APPLY: $name"; fails=1; return; fi
  out="$($runner)"; restore
  check "$name" "$out" "$cases"
  if [ -n "$reason" ] && ! grep -qF -- "$reason" <<<"$out"; then echo "NOT RED FOR ITS REASON: $name (its failure never says: $reason)"; fails=1; fi
}

# The branch's base, not main as it is now: a later main's App imports what this branch never had.
BASE="$(git merge-base HEAD main)"
echo "== red on main ($(git rev-parse --short "$BASE")): main's App.tsx, LeftRail.tsx and the four harnesses"
for f in "$APP" "$RAIL" "$HARN" "$QHARN" "$CHARN" "$SRHARN"; do git show "$BASE":"$f" >"$f"; done
check "main's App (jsdom)" "$(js)" "Ask & Chat opens its panel without changing the view
Ask & Chat opens its page under its own name
the Ask line opens Ask & Chat with the words carried over
the rail's Ask & Chat over the results replaces them
the rail holds the panel openers alone
a document opened from an answer is read over the view, the page hidden
a marker in an answer leaves the page for the graph, focus on the canvas
the case line's cross-link to the Ingest Studio leaves the page
Escape on the page does nothing
Show all on graph closes a saved view open beneath the page first
a case opened to ask the model (the hand-off's view=questions
the panel is hidden under the Ask & Chat page"
check "main's harnesses (keyboard)" "$(kb)" "Ask & Chat opens as a page over the view by keyboard
Ask & Chat's page is left by its visible Back to Graph
a [G-n] chosen on Ask & Chat's page leaves it
Show all on graph on Ask & Chat's page leaves it
Show all on graph on Ask & Chat's page past the cap leaves the page"
check "main's results harness (the stacking case)" "$(st)" "ospreyflow dark: Ask & Chat's page is drawn over
ospreyflow light: Ask & Chat's page is drawn over
govuk light: Ask & Chat's page is drawn over"
check "main's App (the guide's case)" "$(guide)" "test_section_6_says_ask_and_chat_is_a_page"
restore

echo "== plants"
plant "the heading not focused on opening" "$PAGE" 's/if \(takeFocus\) heading\.current\?\.focus\(\);/void takeFocus;/' js \
  "the rail's Ask & Chat over the results replaces them"
plant "the heading focused even with words carried (the question box loses focus)" "$PAGE" 's/if \(takeFocus\) heading/if (true) heading/' js \
  "the Ask line opens Ask & Chat with the words carried over"
plant "focus not returned to the rail's opener" "$RAIL" 's/\?\.focus\(\);\n\}/;\n}/' js \
  "Ask & Chat opens its panel without changing the view"
plant "the opener still announcing a dialog" "$RAIL" 's/item\.expanded === undefined \|\| item\.opensPage \?/item.expanded === undefined ?/' js \
  "the rail holds the panel openers alone"
plant "the view beneath left in reach" "$APP" 's/const pageOver = results\.viewInert \|\| ask\.viewInert;/const pageOver = results.viewInert;/' js \
  "the rail's Ask & Chat over the results replaces them"
plant "the Ask page opened over the results, both showing" "$HOOK" 's/(const openPage = \(\) => \{\n)    other\.leave\(\);\n/$1/' js \
  "the Ask line opens Ask & Chat with the words carried over"
plant "a search leaving the Ask page showing" "$APP" 's/ *ask\.leave\(\); \/\/ the results replace Ask & Chat.s page[^\n]*\n//' js \
  "a search from the Ask & Chat page replaces it with the results"
plant "choosing a view leaving the Ask page showing" "$HOOK" 's/(    leaveBoth: \(\) => \{\n      other\.leave\(\);\n)      setOpen\(false\);\n/$1/' js \
  "choosing a view leaves the Ask & Chat page"
plant "focus left on the view beneath when a document read from an answer closes" "$HOOK" 's/if \(was && !reading && open\) document\.querySelector<HTMLElement>\(ASK_HEADING\)\?\.focus\(\);/void ASK_HEADING;/' js \
  "a document opened from an answer is read over the view, the page hidden"
plant "focus lost with the marker when the page goes" "$HOOK" 's/        document\.querySelector<HTMLElement>\(CANVAS\)\?\.focus\(\);\n//' js \
  "a marker in an answer leaves the page for the graph, focus on the canvas"
plant "Show all on graph leaving the page over the graph it changed (App off the hook)" "$APP" 's/    ask\.showOnGraph\(\n      \(\) =>\n        void showAnswerOnCanvas\(/    ((show: () => void) => show())(\n      () =>\n        void showAnswerOnCanvas(/' js \
  "Show all on graph under an answer leaves the page for the graph"
# Lane review 3: App's Show all body, each part held (the lens closed, the Graph current, the items read by id).
plant "Show all on graph leaving a saved view open beneath (App)" "$APP" 's/(  const showAnswerOnGraph = \(ids: AnswerIds\): void => \{\n    if \(!investigationId\) return;\n)    if \(lens\) closeLens\(\);\n/$1/' js \
  "Show all on graph closes a saved view open beneath the page first"
plant "Show all on graph leaving the view the page was opened over current (App)" "$APP" 's/(    if \(lens\) closeLens\(\);\n)    setView\("graph"\);\n(    \/\/ ADR-145 Amendment 18: the answer)/$1$2/' js \
  "Show all on graph under an answer leaves the page for the graph, reads the answer"
plant "Show all on graph leaving the page and showing nothing (App, the hook handed a no-op)" "$APP" 's/    ask\.showOnGraph\(\n      \(\) =>\n        void showAnswerOnCanvas\(/    ask.showOnGraph(\n      () => undefined,\n      () =>\n        void showAnswerOnCanvas(/' js \
  "Show all on graph under an answer leaves the page for the graph, reads the answer
Show all on graph closes a saved view open beneath the page first"
plant "the cap's words pointing at Save as a view without saying where, the page gone (keyboard)" "$SHOW" 's/Save as a view, under the answer in Ask & Chat, keeps them all\./Save as a view keeps them all./' kb \
  "Show all on graph on Ask & Chat's page past the cap leaves the page"
# The orchestrator's two fixes before merge (15 November 2026): a page opened while a document is read shows at once,
# and Help's panel takes focus only as it is asked for.
plant "the Ask page opened over a document read, left hidden behind the reader (jsdom)" "$HOOK" 's/      stopReading\(\);\n//' js \
  "the rail's Ask & Chat while a document read from the results is open shows the page at once"
plant "the Ask page opened over a document read, left hidden behind the reader (keyboard)" "$HOOK" 's/      stopReading\(\);\n//' sr \
  "Ask & Chat opened while a document is read over the view shows its page at once"
plant "a search over a document read, its results left hidden behind the reader (jsdom)" "$OVER" 's/      if \(reading\) stopReading\?\.\(\);\n//' js \
  "a search while a document read from an answer is open shows the results at once"
plant "a search over a document read, its results left hidden behind the reader (keyboard)" "$OVER" 's/      if \(reading\) stopReading\?\.\(\);\n//' sr \
  "a search while a document is read over the view shows the results at once"
plant "Help's panel taking focus whenever it is drawn (App, as it was)" "$APP" 's/takeFocus=\{welcome === "asked" && helpJustAskedRef\.current\}/takeFocus={welcome === "asked"}/' js \
  "a document read from an answer with Help's panel open keeps focus in the reader"
plant "Help's panel handed App's changing takeFocus (the wrapper passing it through)" "$APP" 's/  const \[takeFocus\] = useState\(props\.takeFocus \?\? false\);\n  return <WorkspaceWelcome \{\.\.\.props\} takeFocus=\{takeFocus\} \/>;/  return <WorkspaceWelcome {...props} \/>;/' js \
  "Help's panel keeps the focus it took through App's later renders"
# Case's review of 052e265, n1: one Help panel mounted while a document is read over either page, never two.
plant "Help's panel kept in the hidden Ask page beside the one App draws over the view" "$APP" 's/ && !ask\.pageHidden \? welcomePanel/ ? welcomePanel/' js \
  "Help's panel is mounted once while a document read from an answer is open"
plant "Help's panel kept in the hidden results beside the one App draws over the view" "$APP" 's/ && !results\.resultsHidden \? welcomePanel/ ? welcomePanel/' js \
  "Help's panel is mounted once while a document read from the results is open"
plant "the cross-link leaving the page showing, both ways" "$APP" 's/(          toStudio: \(\) => \{\n)            leavePages\(\);\n/$1/; s/(          toGlass: \(\) => \{\n)            leavePages\(\);\n/$1/' js \
  "the case line's cross-link to the Ingest Studio leaves the page"
plant "Escape closing the page as a dialog would" "$PAGE" 's/<section className=/<section onKeyDown={(e) => { if (e.key === "Escape") onBack(); }} className=/' js \
  "Escape on the page does nothing"
plant "the hand-off's view=questions not opening the page" "$APP" 's/useAskPage\(readerDocumentId !== null, results, handoff\.view === "questions", stopReading\)/useAskPage(readerDocumentId !== null, results, false, stopReading)/' js \
  "a case opened to ask the model (the hand-off's view=questions"
plant "the batch job's panel left showing under the page" "$APP" 's/searching !== null \|\| questionsOpen \|\| readerDocumentId/searching !== null || readerDocumentId/' js \
  "the panel is hidden under the Ask & Chat page"
plant "the harness's page without its back link focus (keyboard)" "$RAIL" 's/\?\.focus\(\);\n\}/;\n}/' kb \
  "Ask & Chat opens as a page over the view by keyboard"
plant "a marker on the page leaving it open (keyboard, the real canvas)" "$HOOK" 's/    showOnGraph: \(show\) => \{\n      setOpen\(false\);\n/    showOnGraph: (show) => {\n/' kb \
  "a [G-n] chosen on Ask & Chat's page leaves it"
plant "Show all on graph on the harness's page off the hook (keyboard, the real canvas)" "$CHARN" 's/onShowAll=\{\(ids\) => ask\.showOnGraph\(\(\) => void showAllOnCanvas\(ids\)\)\}/onShowAll={(ids) => void showAllOnCanvas(ids)}/' kb \
  "Show all on graph on Ask & Chat's page leaves it"
plant "the Ask page below the canvas's toolbar (the stacking case, three looks)" "$CSS" 's/  z-index: 19;/  z-index: 1;/' st \
  "ospreyflow dark: Ask & Chat's page is drawn over
ospreyflow light: Ask & Chat's page is drawn over
govuk light: Ask & Chat's page is drawn over" ".canvas-toolbar ("
plant "a drawer titled Ask & Chat put back in App's own shape (the guide's case)" "$APP" 's/(      <Drawer open=\{exploreOpen\})/      <Drawer open={questionsOpen} onClose={() => ask.leave()} title={RAIL_LABELS.questions}><p \/><\/Drawer>\n$1/' guide \
  "test_section_6_says_ask_and_chat_is_a_page" "match='title={RAIL_LABELS.questions'"
plant "the back link's words in the page's own background token (no contrast; axe, three looks)" "$CSS" 's/(\.ask-page__back \{[^}]*?)color: var\(--text-primary\);/$1color: var(--surface-app);/s' ax \
  "places-harness.html open=questions (dark)
places-harness.html open=questions (light)
places-harness.html open=questions (govuk)"

echo "== unplanted"
j="$(js)"; k="$(kb)"; a="$(ax)"; g="$(guide)"; t="$(st)"; r="$(sr)"
if grep -qE "Tests  [0-9]+ passed" <<<"$j" && ! grep -qE "Tests .*failed" <<<"$j" \
  && grep -qE "^\s+[0-9]+ passed" <<<"$k" && ! grep -qE "^\s+[0-9]+ failed" <<<"$k" \
  && grep -qE "^\s+[0-9]+ passed" <<<"$a" && ! grep -qE "^\s+[0-9]+ failed" <<<"$a" \
  && grep -qE "^\s+3 passed" <<<"$t" && ! grep -qE "^\s+[0-9]+ failed" <<<"$t" \
  && grep -qE "^\s+2 passed" <<<"$r" && ! grep -qE "^\s+[0-9]+ failed" <<<"$r" \
  && grep -qE "[0-9]+ passed" <<<"$g" && ! grep -qE "failed" <<<"$g"; then
  echo "unplanted: $(grep 'Tests ' <<<"$j" | xargs); keyboard $(grep -E '^\s+[0-9]+ passed' <<<"$k" | xargs); axe $(grep -E '^\s+[0-9]+ passed' <<<"$a" | xargs); stacking $(grep -E '^\s+[0-9]+ passed' <<<"$t" | xargs); over a reader $(grep -E '^\s+[0-9]+ passed' <<<"$r" | xargs); guide $(tail -1 <<<"$g")"
else echo "UNPLANTED NOT GREEN"; grep -E "×|Tests |^\s+[0-9]+\) |^\s+[0-9]+ (passed|failed)|^FAILED|passed|failed" <<<"$j
$k
$a
$t
$r
$g" | head -12; fails=1; fi
[ "$fails" = 0 ] && echo "every plant red for its reason, unplanted green" || { echo "SOME PLANT WRONG"; exit 1; }
