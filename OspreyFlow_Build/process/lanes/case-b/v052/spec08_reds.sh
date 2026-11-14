#!/usr/bin/env bash
# The two seed-free halves split from spec 08's seeded cases (14 November 2026), each shown red on poc by a planted
# copy of the module, then the module as it is shown green. Runs spec08_live.sh, so: from OspreyFlow_Core, on R1's
# kind cluster after the install, under a lease (step 6's run, platform-b's run sheet).
#
#   bash ../OspreyFlow_Build/process/lanes/case-b/v052/spec08_reds.sh
#
# The planted copy sits beside the module (its imports are the module's) and is removed on exit.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
MODULE="$(cd "$HERE/../../../../tests/scenarios" && pwd)/test_phase8_exit_over_the_wire.py"
COPY="${MODULE%.py}_planted.py"
trap 'rm -f "$COPY"' EXIT
ok=1
plant() { # name, python that edits the text in s, the -k selection, the words its failure must hold
  python3 - "$MODULE" "$COPY" "$2" <<'PY' || { echo "MISS: $1"; ok=0; return; }
import sys
src, dst, edit = sys.argv[1:4]
s = open(src).read()
before = s
exec(edit)
assert s != before, "the plant changed nothing"
open(dst, "w").write(s)
PY
  out="$(OSPREY_V052_SPEC08_MODULE="$COPY" bash "$HERE/spec08_live.sh" -k "$3" 2>&1)"
  if grep -q "1 failed" <<<"$out" && grep -qE "$4" <<<"$out"; then echo "AS IT MUST BE (red): $1"; else echo "WRONG (not red as it must be): $1"; ok=0; fi
  grep -E "^FAILED|^E  " <<<"$out" | head -4
}
plant "A7's refusal half with the hostile field name made safe" \
  's = s.replace("\"item_type\x27); DROP TABLE events; --\"", "\"item_type\"", 1)' \
  "unknown_field_name_is_refused" "a field name carrying SQL was not refused in words: 200"
plant "the stream's seed-free half asking with ?token= in place of its ticket" \
  's = s.replace("?ticket={ticket.json()[\x27ticket\x27]}", "?token={ticket.json()[\x27ticket\x27]}", 1)' \
  "stream_opens_through_the_proxy" "stream_opens_through_the_proxy"
out="$(bash "$HERE/spec08_live.sh" -k "door_opens or stream_opens_through_the_proxy or unknown_field_name_is_refused" 2>&1)"
if grep -qE "(^| )3 passed" <<<"$out" && ! grep -qE "[0-9]+ failed" <<<"$out"; then echo "AS IT MUST BE (green): the door and both seed-free halves"; else echo "WRONG (not green): the door and both seed-free halves"; ok=0; fi
grep -E "passed|failed|^FAILED" <<<"$out" | tail -3
[ $ok = 1 ] && echo "both halves red when planted, green as built" || { echo "A STEP WENT THE WRONG WAY"; exit 1; }
