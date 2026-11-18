#!/usr/bin/env bash
# For the owner to run, not an agent. Gives BL6 one more round after its verifier's second set of findings.
#     bash OspreyFlow_Build/process/lanes/v062/slice-line/diffs/allow-bl6-round-3.sh
# Run it only after answering the conductor's question on the three compressed files, and when no merge is running.
#
# It raises BL6's rounds limit to 3, sets its round to 3 and its phase back to building. Nothing is frozen again; the
# verifier's findings file stays where it is, and the builder reads it as it did for round 2. No script does this
# today (F7 in LINE_FAULTS_2026-11-18.md): the line stops at the limit and leaves the decision to the owner by hand.
set -euo pipefail
R="${OSPREY_SLICE_HOME:-$HOME/.ospreyflow/slice-line}/records/BL6"
pgrep -f "slice_line/merge_slice.py" >/dev/null && { echo "a merge is running: wait for it, nothing changed"; exit 1; }
python3 - "$R/state.json" <<'PY'
import json, sys
p = sys.argv[1]
s = json.load(open(p))
assert s.get("phase") == "stopped" and s.get("round") == 2 and s.get("rounds_limit") == 2, "BL6 is not stopped after round 2"
s.update(phase="building", round=3, rounds_limit=3)
s.pop("note", None)
json.dump(s, open(p, "w"), indent=1)
PY
# The builder's worktree is a snapshot from the slice's start, so it cannot see the ruling recorded since. Bring the
# ruling in: main's RULINGS.md, committed on the slice's branch. It is the same text main has, so the merge is clean.
W="$HOME/dev/osprey-wt/slice-BL6"
REL=OspreyFlow_Build/process/lanes/v062/RULINGS.md
cp "$(git rev-parse --show-toplevel)/$REL" "$W/$REL"
git -C "$W" add -- "$REL"
git -C "$W" commit -q -m "docs(process): the owner's ruling on the three compressed files, as on main (RULINGS.md)" -- "$REL"
echo "BL6 may have a third round; the conductor runs the builder."
