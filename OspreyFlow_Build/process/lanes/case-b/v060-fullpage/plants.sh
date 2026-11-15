#!/usr/bin/env bash
# Rule 15 for v0.6.0 #4, Ask & Chat as a page over the view (ADR-145 Amendment 18). First the red-on-main record: main's
# App.tsx, LeftRail.tsx and places harness put back, every new case red. Then each plant breaks one rule in the code's
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
HARN=$WS/keyboard/places-harness.tsx
REG=$WS/keyboard/actionRegistry.ts
FILES=("$APP" "$RAIL" "$PAGE" "$CSS" "$HARN" "$REG")
: "${OSPREY_PORTS_SLOT:?set the Playwright slot of this lane}"
SAVED="$(mktemp -d)"
for f in "${FILES[@]}"; do cp "$f" "$SAVED/$(basename "$f")"; done
restore() { for f in "${FILES[@]}"; do cp "$SAVED/$(basename "$f")" "$f"; done; }
cp "$REG" "$SAVED/registry-as-found.ts"
trap 'restore; cp "$SAVED/registry-as-found.ts" "$REG"; rm -rf "$SAVED"' EXIT
grep -q '"ask-and-chat-page-by-keyboard"' "$REG" || git apply "$HERE/registry-v060-fullpage.patch" || exit 2
cp "$REG" "$SAVED/actionRegistry.ts"
fails=0
js() { (cd "$WS" && npx vitest run src/App.chrome.test.tsx src/App.help.test.tsx src/App.search.test.tsx 2>&1); }
kb() { (cd "$WS" && npx playwright test --config keyboard/playwright.config.ts shell.spec.ts --workers=1 --reporter=line 2>&1); }
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
plant() { # name, file, perl substitution, runner, cases (newline-separated)
  local name="$1" file="$2" sub="$3" runner="$4" cases="$5" out
  perl -0pi -e "$sub" "$file"
  if cmp -s "$file" "$SAVED/$(basename "$file")"; then echo "PLANT DID NOT APPLY: $name"; fails=1; return; fi
  out="$($runner)"; restore
  check "$name" "$out" "$cases"
}

echo "== red on main: main's App.tsx, LeftRail.tsx and places harness"
git show main:"$APP" >"$APP"; git show main:"$RAIL" >"$RAIL"; git show main:"$HARN" >"$HARN"
check "main's App (jsdom)" "$(js)" "Ask & Chat opens its panel without changing the view
Ask & Chat opens its page under its own name
the Ask line opens Ask & Chat with the words carried over
the rail's Ask & Chat over the results replaces them
the rail holds the panel openers alone"
check "main's harness (keyboard)" "$(kb)" "Ask & Chat opens as a page over the view by keyboard"
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
plant "the view beneath left in reach" "$APP" 's/const pageOver = results\.viewInert \|\| askOver;/const pageOver = results.viewInert;/' js \
  "the rail's Ask & Chat over the results replaces them"
plant "the Ask page opened over the results, both showing" "$APP" 's/(function openAskPage\(\): void \{\n)    results\.leave\(\);\n/$1/' js \
  "the Ask line opens Ask & Chat with the words carried over"
plant "a search leaving the Ask page showing" "$APP" 's/ *setQuestionsOpen\(false\); \/\/ the results replace Ask & Chat.s page[^\n]*\n//' js \
  "a search from the Ask & Chat page replaces it with the results"
plant "choosing a view leaving the Ask page showing" "$APP" 's/(function leavePages\(\): void \{\n    results\.leave\(\);\n)    setQuestionsOpen\(false\);\n/$1/' js \
  "choosing a view leaves the Ask & Chat page"
plant "the harness's page without its back link focus (keyboard)" "$RAIL" 's/\?\.focus\(\);\n\}/;\n}/' kb \
  "Ask & Chat opens as a page over the view by keyboard"
plant "the back link's words in a colour that fails contrast (axe, three looks)" "$CSS" 's/(\.ask-page__back \{[^}]*?)color: var\(--text-primary\);/$1color: #b8b8b8;/s' ax \
  "places-harness.html open=questions (dark)
places-harness.html open=questions (light)
places-harness.html open=questions (govuk)"

echo "== unplanted"
j="$(js)"; k="$(kb)"; a="$(ax)"; g="$(guide)"
if grep -qE "Tests  [0-9]+ passed" <<<"$j" && ! grep -qE "Tests .*failed" <<<"$j" \
  && grep -qE "^\s+[0-9]+ passed" <<<"$k" && ! grep -qE "^\s+[0-9]+ failed" <<<"$k" \
  && grep -qE "^\s+[0-9]+ passed" <<<"$a" && ! grep -qE "^\s+[0-9]+ failed" <<<"$a" \
  && grep -qE "[0-9]+ passed" <<<"$g" && ! grep -qE "failed" <<<"$g"; then
  echo "unplanted: $(grep 'Tests ' <<<"$j" | xargs); keyboard $(grep -E '^\s+[0-9]+ passed' <<<"$k" | xargs); axe $(grep -E '^\s+[0-9]+ passed' <<<"$a" | xargs); guide $(tail -1 <<<"$g")"
else echo "UNPLANTED NOT GREEN"; fails=1; fi
[ "$fails" = 0 ] && echo "every plant red for its reason, unplanted green" || { echo "SOME PLANT WRONG"; exit 1; }
