#!/usr/bin/env bash
# Rule 15 for ADR-044 Amendment 2's Glass cases (StatusBadge, HotlistPanel and MonitorPanel tests): each plant
# breaks the note's place in the code's own shape, and the named case goes red; restored from a saved copy.
# Run from the repository root.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
WS=OspreyFlow_Core/apps/workspace
B=$WS/src/watches/StatusBadge.tsx
HP=$WS/src/watches/HotlistPanel.tsx
MP=$WS/src/watches/MonitorPanel.tsx
SAVED="$(mktemp -d)"; for f in "$B" "$HP" "$MP"; do cp "$f" "$SAVED/$(basename "$f")"; done
restore() { for f in "$B" "$HP" "$MP"; do cp "$SAVED/$(basename "$f")" "$f"; done; }
trap 'restore; rm -rf "$SAVED"' EXIT
fails=0
run() { (cd "$WS" && npx vitest run src/watches 2>&1); }
plant() { # name, file, perl substitution, the case's words (as vitest prints its name)
  local name="$1" file="$2" sub="$3" case="$4" out
  perl -0pi -e "$sub" "$file"
  if cmp -s "$file" "$SAVED/$(basename "$file")"; then echo "PLANT DID NOT APPLY: $name"; fails=1; return; fi
  out="$(run)"; restore
  if grep -E "×" <<<"$out" | grep -qF "$case"; then echo "AS IT MUST BE (red): $name"; grep -E "×" <<<"$out" | grep -F "$case" | sed 's/^ */    /' | head -2
  else echo "NOT RED FOR ITS REASON: $name (wanted: $case)"; grep -E "×|Tests " <<<"$out" | head -4; fails=1; fi
}
plant "the note shown beside Stopped too, over the reason" "$B" \
  's/const beside = stopped \? why : note;/const beside = note ?? why;/' \
  "a stopped watch shows its reason, not a note left behind"
plant "the note never shown" "$B" \
  's/const beside = stopped \? why : note;/const beside = stopped ? why : null;/' \
  "the note is shown beside Active"
plant "the hotlist's list not passing the note" "$HP" \
  's/ note=\{hotlist.status_note\}//' \
  "says, while active, how many loads could not check its owner's sign-in"
plant "the watch's list not passing the note" "$MP" \
  's/ note=\{monitor.status_note\}//' \
  "says, while active, how many loads could not check its owner's sign-in"
out="$(run)"
if grep -qE "Tests  [0-9]+ passed" <<<"$out" && ! grep -qE "Tests .*failed" <<<"$out"; then echo "unplanted: $(grep 'Tests ' <<<"$out" | xargs)"; else echo "UNPLANTED NOT GREEN"; fails=1; fi
[ "$fails" = 0 ] && echo "every plant red for its reason, unplanted green" || { echo "SOME PLANT WRONG"; exit 1; }
