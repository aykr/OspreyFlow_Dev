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

CSS=$W/src/questions/askPage.css
QSPEC=keyboard/questions.spec.ts
SSPEC=keyboard/shell.spec.ts
RSPEC=keyboard/search-results.spec.ts

plant "P1 Escape does nothing in the drawer" "$PAGE" \
  "(inside ? onBackRef : onDismissRef).current();" "void inside;" \
  kb $SSPEC "Escape from inside the Ask & Chat drawer"
plant "P1u Escape does nothing in the drawer (App)" "$PAGE" \
  "(inside ? onBackRef : onDismissRef).current();" "void inside;" \
  unit src/App.search.test.tsx "Escape inside the drawer closes it"
plant "P2 the panel mounted again on a change of shape" "$PAGE" \
  '<div ref={body} className=' '<div key={form} ref={body} className=' \
  kb $QSPEC "Expand and Show as a drawer keep"
plant "P2u the panel mounted again on a change of shape (App)" "$PAGE" \
  '<div ref={body} className=' '<div key={form} ref={body} className=' \
  unit src/App.search.test.tsx "Expand keeps the question typed in the same panel"
plant "P3 the scroll not kept across a change of shape" "$PAGE" \
  "restoreAnchor(anchor.current, drawer ? body.current : section.current);" "void restoreAnchor;" \
  kb $QSPEC "Expand and Show as a drawer keep"
plant "P4 Show as a drawer leaves focus on the heading, not Expand" "$PAGE" \
  "(drawer ? expandButton.current : heading.current)?.focus({ preventScroll: true });" "heading.current?.focus({ preventScroll: true });" \
  kb $SSPEC "Show as a drawer returns"
plant "P4b Expand leaves focus on Expand, not the page's heading" "$PAGE" \
  "(drawer ? expandButton.current : heading.current)?.focus({ preventScroll: true });" "if (drawer) expandButton.current?.focus({ preventScroll: true });" \
  kb $SSPEC "Expand turns the Ask & Chat drawer"
plant "P5 a view chosen closes the drawer" "$HOOK" \
  "      other.leave();
      leavePage();" "      other.leave();
      close();" \
  kb $SSPEC "drawer beside the view"
plant "P5u a view chosen closes the drawer (App)" "$HOOK" \
  "      other.leave();
      leavePage();" "      other.leave();
      close();" \
  unit src/App.search.test.tsx "a view chosen keeps the drawer"
plant "P6 the rail opens the page" "$HOOK" \
  "if (!open) setExpanded(false);" "if (!open) setExpanded(true);" \
  kb $SSPEC "drawer beside the view"
# Remembering takes both: closing resets the shape, and so does opening the drawer; with one left the claim still holds.
OLD2="    setOpen(false);
    setExpanded(false);
  };" NEW2="    setOpen(false);
  };" \
plant "P7 the shape remembered (closing and opening keep it)" "$HOOK" \
  "    if (!open) setExpanded(false);
    setOpen(true);" "    setOpen(true);" \
  kb $SSPEC "Expand turns the Ask & Chat drawer"
plant "P8 the drawer over the top bar and the case line" "$PAGE" \
  "style={drawer && top !== null ? { top } : undefined}" "style={undefined}" \
  kb $SSPEC "drawer beside the view"
plant "P9 the rail's opener announces no dialog for the drawer (harness)" "$PLACES" \
  'opensPage: id === "questions" && ask.expanded,' 'opensPage: id === "questions",' \
  kb $SSPEC "drawer beside the view"
plant "P9u the rail's opener announces no dialog for the drawer (App)" "$APP" \
  "onSelect: ask.toggle, opensPage: ask.expanded," "onSelect: ask.toggle, opensPage: true," \
  unit src/App.chrome.test.tsx "the rail holds the panel openers alone"
plant "P9b the opener announces a dialog while it is the page (harness)" "$PLACES" \
  'opensPage: id === "questions" && ask.expanded,' 'opensPage: false,' \
  kb $SSPEC "Expand turns the Ask & Chat drawer"
plant "P9bu the opener announces a dialog while it is the page (App)" "$APP" \
  "onSelect: ask.toggle, opensPage: ask.expanded," "onSelect: ask.toggle, opensPage: false," \
  unit src/App.search.test.tsx "while it is the page, the rail's opener announces no dialog"
plant "P10 the view inert beside the drawer" "$HOOK" \
  "viewInert: open && expanded && !reading," "viewInert: open && !reading," \
  kb $SSPEC "drawer beside the view"
plant "P10b the view in reach under the page" "$HOOK" \
  "viewInert: open && expanded && !reading," "viewInert: false," \
  kb $SSPEC "Expand turns the Ask & Chat drawer"
plant "P11 Escape closes the page too" "$PAGE" \
  "if (!drawer || hidden) return;" "if (hidden) return;" \
  kb $SSPEC "Escape from inside the Ask & Chat drawer"
plant "P12 the results' heading keeps focus from the drawer opened over their reader" "$HOOK" \
  "      setTimeout(() => document.querySelector<HTMLElement>(ASK_HEADING)?.focus(), 0);" "" \
  unit src/App.search.test.tsx "shows its drawer at once, the reader closed"
plant "P13 focusing the page's heading undoes the scroll kept" "$PAGE" \
  "heading.current)?.focus({ preventScroll: true });" "heading.current)?.focus();" \
  kb $QSPEC "Expand and Show as a drawer keep"
plant "P14 Help drawn inside the drawer as well as over the view (App)" "$APP" \
  'beside={welcomeOpen && welcome === "asked" && ask.viewInert ? welcomePanel : null}' 'beside={welcomeOpen && welcome === "asked" && !ask.pageHidden ? welcomePanel : null}' \
  unit src/App.search.test.tsx "drawn once, over the view, not inside the drawer"
plant "P15 the batch panel hidden beside the drawer (App)" "$APP" \
  '|| searching !== null || ask.expanded ||' '|| searching !== null || questionsOpen ||' \
  unit src/App.batchExpand.test.tsx "the panel stays beside"
plant "P16 Escape from the canvas leaves the drawer open" "$PAGE" \
  "(inside ? onBackRef : onDismissRef).current();" "if (inside) onBackRef.current();" \
  kb $QSPEC "chosen in Ask & Chat's drawer selects"
plant "P16u Escape from the canvas leaves the drawer open (App)" "$PAGE" \
  "(inside ? onBackRef : onDismissRef).current();" "if (inside) onBackRef.current();" \
  unit src/App.search.test.tsx "Escape from the canvas closes the drawer"
plant "P16b Escape from the canvas moves focus to the rail" "$PAGE" \
  "(inside ? onBackRef : onDismissRef).current();" "onBackRef.current();" \
  unit src/App.search.test.tsx "Escape from the canvas closes the drawer"
plant "P17 a marker closes the drawer (R1)" "$HOOK" \
  "      if (expanded) close();
      other.leave();" "      close();
      other.leave();" \
  kb $QSPEC "chosen in Ask & Chat's drawer selects"
plant "P17b Show all closes the drawer (R1)" "$HOOK" \
  "      if (expanded) close();
      other.leave();" "      close();
      other.leave();" \
  kb $QSPEC "Show all on graph in Ask & Chat's drawer"
plant "P17u a marker closes the drawer (R1, App)" "$HOOK" \
  "      if (expanded) close();
      other.leave();" "      close();
      other.leave();" \
  unit src/App.search.test.tsx "a marker in an answer in the drawer"
plant "P18 closing always sends focus to the rail (R2)" "$HOOK" \
  'if (to?.isConnected && !to.closest("nav")) {' "if (false) {" \
  unit src/App.search.test.tsx "closing returns focus to that button"
plant "P19 a document from the results or the view takes focus into the drawer" "$HOOK" \
  "if (answer && open) document" "if (open) document" \
  kb $RSPEC "with the drawer open"
plant "P19u a document from the results takes focus into the drawer (App)" "$HOOK" \
  "if (answer && open) document" "if (open) document" \
  unit src/App.search.test.tsx "gives focus back to their heading, not the drawer"
plant "P19b a document from an answer no longer brings focus back to Ask & Chat (App)" "$HOOK" \
  "if (answer && open) document" "if (false) document" \
  unit src/App.search.test.tsx "shown again when it closes, focus on its heading"
plant "P20 no room for the drawer beside the results" "$CSS" \
  ":root[data-ask-drawer] .search-results {" ":root[data-ask-drawer-off] .search-results {" \
  kb $RSPEC "beside Ask & Chat's drawer no control"
plant "P21 no room for the drawer beside the batch panel" "$CSS" \
  ":root[data-ask-drawer] .batch-expansion {" ":root[data-ask-drawer-off] .batch-expansion {" \
  kb keyboard/batch-expansion.spec.ts "beside Ask & Chat's drawer the batch"
plant "P22 a search closes the drawer" "$HOOK" \
  "    leave: leavePage," "    leave: close," \
  unit src/App.search.test.tsx "a search keeps the drawer beside the results"
plant "P23 another place and the cross-link leave the drawer open" "$HOOK" \
  "      other.leave();
      close();
    }," "      other.leave();
      leavePage();
    }," \
  unit src/App.search.test.tsx "closes the drawer"
plant "P24 the results' Ask line opens the drawer, not the page" "$HOOK" \
  "      closeReader();
      setExpanded(true);" "      closeReader();" \
  unit src/App.search.test.tsx "Ask line used with the drawer open"
plant "P25 the hand-off opens the page" "$APP" \
  'handoff.view === "questions" ? "drawer" : null' 'handoff.view === "questions" ? "page" : null' \
  unit src/App.search.test.tsx "opens on the drawer"
plant "P26 Ask the model about these… opens the page" "$APP" \
  "                  ask.openDrawer();" "                  openAskPage();" \
  unit src/App.search.test.tsx "Ask the model about these… opens the drawer"
plant "P27 Expand leaves the results showing" "$HOOK" \
  "    expand: () => {
      other.leave();" "    expand: () => {" \
  unit src/App.search.test.tsx "Expand over the results leaves them"
plant "P28 a saved view closes the drawer" "$APP" \
  "    viewChosen();
    setView(\"graph\");" "    leavePages();
    setView(\"graph\");" \
  unit src/App.search.test.tsx "a saved view opened from the case line keeps the drawer"
plant "P29 the results' Show on graph closes the drawer" "$APP" \
  "            setSelectedNode(nodes[0] ?? null);
            viewChosen();" "            setSelectedNode(nodes[0] ?? null);
            leavePages();" \
  unit src/App.search.test.tsx "the results' Show on graph keeps the drawer"
plant "P30 T beside the drawer refused (App)" "$APP" \
  "const pageOver = results.viewInert || ask.viewInert;" "const pageOver = results.viewInert || ask.open;" \
  unit src/App.chrome.test.tsx "under the Ask & Chat page"

echo "$red of $total plants red"
git status --short -- "$W/src" "$W/keyboard" | grep -v "actionRegistry.ts" && echo "WARNING: a plant was left in place" || true
