#!/usr/bin/env bash
# Red first for the timed cases' move to the budget run (case-b, 14 November 2026). Each plant is
# applied, the named run is made, the verdict is read from vitest's own assertion line, and the
# file is put back from HEAD (commit the change under test first). Run from the repository root; runs vitest only, no stack.
set -u
W=OspreyFlow_Core/apps/workspace
ok=1
verdict() { # name, want (red|green), log, the line that makes it red
  # Red only for the reason named: the assertion's own line. Green only with nothing failed at all.
  if [ "$2" = red ]; then
    if grep -qE "$4" "$3"; then echo "AS IT MUST BE (red): $1"; else echo "WRONG (not red by its own assertion): $1"; ok=0; fi
  else
    if grep -qE "(Tests|Test Files) .*failed|FAIL " "$3"; then echo "WRONG (something failed): $1"; ok=0; else echo "AS IT MUST BE (green): $1"; fi
  fi
}
run() { (cd $W && npx vitest run "$@" 2>&1 | sed 's/\x1b\[[0-9;]*m//g'); }
L=$(mktemp)

# 1. The guard, against main's tree: the two timed cases back in their ordinary files.
git show main:$W/src/canvas/settledAnchor.test.ts > $W/src/canvas/settledAnchor.test.ts
git show main:$W/src/canvas/communityLinks.test.ts > $W/src/canvas/communityLinks.test.ts
run src/testing/budgetRun.test.ts > $L
verdict "guard: main's timed cases in the parallel run" red $L "FAIL .*has no timed case left in the parallel run"
grep -E "settledAnchor.test.ts|communityLinks.test.ts" $L | grep -E '^\s*[+-]?\s*"' | head -2
git checkout -q HEAD -- $W/src/canvas/settledAnchor.test.ts $W/src/canvas/communityLinks.test.ts

# 2. settledAnchors made slow (1.1 s more than it takes): its budget file red, run alone in the budget run.
python3 - "$W/src/canvas/settledAnchor.ts" <<'PY'
import sys; p=sys.argv[1]; s=open(p).read()
s=s.replace("  const anchors = new Map<string, string>();", "  const anchors = new Map<string, string>();\n  for (const t = performance.now(); performance.now() - t < 1100; );", 1)
open(p,"w").write(s)
PY
run --config vitest.budget.config.ts src/canvas/settledAnchor.budget.test.ts > $L
verdict "plant: settledAnchors 1.1 s slower, budget run alone" red $L "expected .* to be less than 1000"
grep -m1 -E "expected .* to be less than" $L
git checkout -q HEAD -- $W/src/canvas/settledAnchor.ts

# 3. packBubbles made slow (2.1 s more): its budget file red, run alone.
python3 - "$W/src/canvas/layoutModes.ts" <<'PY'
import sys,re; p=sys.argv[1]; s=open(p).read()
m=re.search(r"^export function packBubbles\(.*\{$", s, re.M); assert m, "packBubbles not found"
s=s[:m.end()]+"\n  for (const t = performance.now(); performance.now() - t < 2100; );"+s[m.end():]
open(p,"w").write(s)
PY
run --config vitest.budget.config.ts src/canvas/communityLinks.budget.test.ts > $L
verdict "plant: packBubbles 2.1 s slower, budget run alone" red $L "expected .* to be less than 2000"
grep -m1 -E "expected .* to be less than" $L
git checkout -q HEAD -- $W/src/canvas/layoutModes.ts

# 4. Unplanted: both runs green.
run src/testing/budgetRun.test.ts src/canvas/settledAnchor.test.ts src/canvas/communityLinks.test.ts > $L
verdict "unplanted: the guard and the two ordinary files" green $L
run --config vitest.budget.config.ts > $L
verdict "unplanted: the budget run" green $L
grep -E "Test Files|Tests " $L
rm -f $L
git status --short $W
[ $ok = 1 ] && echo "every plant red, unplanted green" || { echo "A PLANT WENT THE WRONG WAY"; exit 1; }
