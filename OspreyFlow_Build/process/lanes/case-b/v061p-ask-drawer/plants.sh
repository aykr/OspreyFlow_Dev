#!/usr/bin/env bash
# Rule 15 for ADR-145 Amendment 20: each plant breaks one claim at its real call site, the cases that should catch it are
# run, and the file is restored from git. A plant is "red" when the run fails. Run from the worktree's root, on a clean
# tree with the registry patch applied: OSPREY_PORTS_SLOT=<slot> bash OspreyFlow_Build/process/lanes/case-b/v061p-ask-drawer/plants.sh
set -u
cd "$(git rev-parse --show-toplevel)/OspreyFlow_Core"
W=apps/workspace
PAGE=$W/src/questions/AskPage.tsx
HOOK=$W/src/questions/useAskPage.ts
APP=$W/src/App.tsx
PLACES=$W/keyboard/places-harness.tsx
red=0
total=0

# plant <name> <file> <old> <new> <kind: kb|unit> <spec or test file> <grep>
plant() {
  local name=$1 file=$2 old=$3 new=$4 kind=$5 where=$6 grep=$7
  total=$((total + 1))
  OLD="$old" NEW="$new" python3 - "$file" <<'EOF' || { echo "PLANT $name: old text not found"; return; }
import os, sys
p = sys.argv[1]
s = open(p).read()
pairs = [(os.environ["OLD"], os.environ["NEW"])]
if os.environ.get("OLD2"):
    pairs.append((os.environ["OLD2"], os.environ["NEW2"]))
for old, new in pairs:
    assert s.count(old) == 1, f"{old!r} found {s.count(old)} times"
    s = s.replace(old, new)
open(p, "w").write(s)
EOF
  if [ "$kind" = kb ]; then
    out=$(npx playwright test --config $W/keyboard/playwright.config.ts --workers 1 "$where" -g "$grep" --reporter=line 2>&1)
  else
    out=$(npx vitest run --root $W "$where" -t "$grep" 2>&1)
  fi
  git checkout -- "$file"
  if echo "$out" | grep -qE "[0-9]+ failed|Tests +[0-9]+ failed"; then
    red=$((red + 1))
    echo "RED   $name"
  else
    echo "GREEN $name   <- the cases did not see it"
  fi
  echo "$out" | grep -E "Error:|AssertionError|> +[0-9]+ \|" | head -3 | sed 's/^/        /'
}

plant "P1 Escape inside the drawer does nothing" "$PAGE" \
  "section.current?.contains(event.target)) onBackRef.current();" "section.current?.contains(event.target)) void 0;" \
  kb keyboard/shell.spec.ts "Escape from inside the Ask & Chat drawer"
plant "P1u Escape inside the drawer does nothing (App)" "$PAGE" \
  "section.current?.contains(event.target)) onBackRef.current();" "section.current?.contains(event.target)) void 0;" \
  unit src/App.search.test.tsx "Escape inside the drawer closes it"
plant "P2 the panel mounted again on a change of shape" "$PAGE" \
  '<div ref={body} className=' '<div key={form} ref={body} className=' \
  kb keyboard/questions.spec.ts "Expand and Show as a drawer keep"
plant "P2u the panel mounted again on a change of shape (App)" "$PAGE" \
  '<div ref={body} className=' '<div key={form} ref={body} className=' \
  unit src/App.search.test.tsx "Expand keeps the question typed in the same panel"
plant "P3 the scroll not kept across a change of shape" "$PAGE" \
  "restoreAnchor(anchor.current, drawer ? body.current : section.current);" "void restoreAnchor;" \
  kb keyboard/questions.spec.ts "Expand and Show as a drawer keep"
plant "P4 Show as a drawer leaves focus on the heading, not Expand" "$PAGE" \
  "(drawer ? expandButton.current : heading.current)?.focus({ preventScroll: true });" "heading.current?.focus({ preventScroll: true });" \
  kb keyboard/shell.spec.ts "Show as a drawer returns"
plant "P5 a view chosen closes the drawer" "$HOOK" \
  "      other.leave();
      leavePage();" "      other.leave();
      close();" \
  kb keyboard/shell.spec.ts "drawer beside the view"
plant "P5u a view chosen closes the drawer (App)" "$HOOK" \
  "      other.leave();
      leavePage();" "      other.leave();
      close();" \
  unit src/App.search.test.tsx "a view chosen keeps the drawer"
plant "P6 the rail opens the page" "$HOOK" \
  "if (!open) setExpanded(false);" "if (!open) setExpanded(true);" \
  kb keyboard/shell.spec.ts "drawer beside the view"
# Remembering takes both: closing resets the shape, and so does opening the drawer; with one left the claim still holds.
OLD2="    setOpen(false);
    setExpanded(false);
  };" NEW2="    setOpen(false);
  };" \
plant "P7 the shape remembered (closing and opening keep it)" "$HOOK" \
  "    if (!open) setExpanded(false);
    setOpen(true);" "    setOpen(true);" \
  kb keyboard/shell.spec.ts "Expand turns the Ask & Chat drawer"
plant "P8 the drawer over the top bar and the case line" "$PAGE" \
  "style={drawer && top !== null ? { top } : undefined}" "style={undefined}" \
  kb keyboard/shell.spec.ts "drawer beside the view"
plant "P9 the rail's opener says it opens no dialog (harness)" "$PLACES" \
  "onSelect: id === \"questions\" ? ask.toggle : () => toggle(id)," "onSelect: id === \"questions\" ? ask.toggle : () => toggle(id), opensPage: id === \"questions\"," \
  kb keyboard/shell.spec.ts "drawer beside the view"
plant "P9u the rail's opener says it opens no dialog (App)" "$APP" \
  "onSelect: ask.toggle, ...mark(\"questions\")" "onSelect: ask.toggle, opensPage: true, ...mark(\"questions\")" \
  unit src/App.chrome.test.tsx "the rail holds the panel openers alone"
plant "P10 the view inert beside the drawer" "$HOOK" \
  "viewInert: open && expanded && !reading," "viewInert: open && !reading," \
  kb keyboard/shell.spec.ts "drawer beside the view"
plant "P11 Escape closes the page too" "$PAGE" \
  "if (!drawer || hidden) return;" "if (hidden) return;" \
  kb keyboard/shell.spec.ts "Escape from inside the Ask & Chat drawer"
plant "P12 the results' heading keeps focus from the drawer opened over their reader" "$HOOK" \
  "      setTimeout(() => document.querySelector<HTMLElement>(ASK_HEADING)?.focus(), 0);" "" \
  unit src/App.search.test.tsx "shows its drawer at once, the reader closed"
plant "P13 focusing the page's heading undoes the scroll kept" "$PAGE" \
  "heading.current)?.focus({ preventScroll: true });" "heading.current)?.focus();" \
  kb keyboard/questions.spec.ts "Expand and Show as a drawer keep"
plant "P14 Help drawn inside the drawer as well as over the view (App)" "$APP" \
  'beside={welcomeOpen && welcome === "asked" && ask.viewInert ? welcomePanel : null}' 'beside={welcomeOpen && welcome === "asked" && !ask.pageHidden ? welcomePanel : null}' \
  unit src/App.search.test.tsx "drawn once, over the view, not inside the drawer"
plant "P15 the batch panel hidden beside the drawer (App)" "$APP" \
  '|| searching !== null || ask.expanded ||' '|| searching !== null || questionsOpen ||' \
  unit src/App.batchExpand.test.tsx "the panel stays beside"

echo "$red of $total plants red"
git status --short -- "$W/src" "$W/keyboard" | grep -v "actionRegistry.ts" && echo "WARNING: a plant was left in place" || true
