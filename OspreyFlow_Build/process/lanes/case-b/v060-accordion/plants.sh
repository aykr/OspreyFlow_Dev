#!/usr/bin/env bash
# Rule 15 for v0.6.0 #3, Ask & Chat's history as an accordion: each plant breaks one rule in QuestionsPanel.tsx in the
# code's own shape, and the named case goes red; restored from a saved copy, never `git checkout`. The keyboard ones
# apply the registry's id from registry-v060-accordion.patch for the run. Run from the repository root, with
# OSPREY_PORTS_SLOT.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
WS=OspreyFlow_Core/apps/workspace
P=$WS/src/questions/QuestionsPanel.tsx
REG=$WS/keyboard/actionRegistry.ts
HERE=OspreyFlow_Build/process/lanes/case-b/v060-accordion
: "${OSPREY_PORTS_SLOT:?set the Playwright slot of this lane}"
SAVED="$(mktemp -d)"; cp "$P" "$SAVED/QuestionsPanel.tsx"; cp "$REG" "$SAVED/actionRegistry.ts"
trap 'cp "$SAVED/QuestionsPanel.tsx" "$P"; cp "$SAVED/actionRegistry.ts" "$REG"; rm -rf "$SAVED"' EXIT
grep -q '"open-an-earlier-answer-by-keyboard"' "$REG" || git apply "$HERE/registry-v060-accordion.patch" || exit 2
fails=0
js() { (cd "$WS" && npx vitest run src/questions/QuestionsPanel.test.tsx 2>&1); }
kb() { (cd "$WS" && npx playwright test --config keyboard/playwright.config.ts questions.spec.ts --workers=1 --reporter=line 2>&1); }
plant() { # name, perl substitution, runner, the case (a substring of its name)
  local name="$1" sub="$2" runner="$3" case="$4" out
  perl -0pi -e "$sub" "$P"
  if cmp -s "$P" "$SAVED/QuestionsPanel.tsx"; then echo "PLANT DID NOT APPLY: $name"; fails=1; return; fi
  out="$($runner)"; cp "$SAVED/QuestionsPanel.tsx" "$P"
  if grep -E "×|^\s+[0-9]+\) " <<<"$out" | grep -qF "$case"; then echo "AS IT MUST BE (red): $name"; grep -E "×|^\s+[0-9]+\) " <<<"$out" | grep -F "$case" | head -1 | sed -E 's/^ *//'
  else echo "NOT RED FOR ITS REASON: $name (wanted: $case)"; grep -E "×|Tests |passed|failed" <<<"$out" | head -4; fails=1; fi
}
plant "every answer open (no accordion)" 's/const open = opened\[entry.id\] \?\? newest;/const open = opened[entry.id] ?? true;/' \
  js "opens only the newest answer"
plant "the newest closed too" 's/const open = opened\[entry.id\] \?\? newest;/const open = opened[entry.id] ?? false;/' \
  js "closes every earlier answer when a new question is answered"
plant "an earlier answer left open after a new question" 's/      setOpened\(\{\}\); \/\/ the new answer is the newest[^\n]*\n//' \
  js "closes every earlier answer when a new question is answered"
plant "a closed answer's body still in reach (not hidden)" 's/hidden=\{!open\}/hidden={false}/' \
  kb "an earlier answer is opened from its question's line by keyboard"
plant "the line not saying it is open or closed" 's/                  aria-expanded=\{open\}\n//' \
  js "opens only the newest answer"
plant "a closed line not counting its proposals" 's/\{!open && toDecide > 0 && \(/{false \&\& (/' \
  js "says on a closed answer's line how many of its proposals are still to decide"
j="$(js)"; k="$(kb)"
if grep -qE "Tests  [0-9]+ passed" <<<"$j" && ! grep -qE "Tests .*failed" <<<"$j" && grep -qE "^\s+[0-9]+ passed" <<<"$k" && ! grep -qE "^\s+[0-9]+ failed" <<<"$k"; then
  echo "unplanted: $(grep 'Tests ' <<<"$j" | xargs); keyboard $(grep -E '^\s+[0-9]+ passed' <<<"$k" | xargs)"; else echo "UNPLANTED NOT GREEN"; fails=1; fi
[ "$fails" = 0 ] && echo "every plant red for its reason, unplanted green" || { echo "SOME PLANT WRONG"; exit 1; }
