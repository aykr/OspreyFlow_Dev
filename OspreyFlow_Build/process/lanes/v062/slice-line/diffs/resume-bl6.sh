#!/usr/bin/env bash
# For the owner to run, not an agent. Corrects BL6's frozen checks command and puts the slice back to building.
#     bash OspreyFlow_Build/process/lanes/v062/slice-line/diffs/resume-bl6.sh
# Run it when no merge is running (a commit on main during one makes that merge refuse: "main moved").
#
# What was wrong: BL6's checks end with `&& make -C OspreyFlow_Build client-name-check`, but the command has already
# done `cd OspreyFlow_Core`, so the path must be `../OspreyFlow_Build`. The builder's three commits are done and its
# pytest part of the checks passed; only that last step failed, six times, so the Stop hook stopped the slice.
# The conductor's error in the checks text (18 November 2026), not the builder's.
#
# It: (1) corrects that one string in BL6's row of slices.tsv and commits it with the records trailer (records mode
# refuses a change to a started slice's frozen commands, so this is the owner's commit); (2) runs refreeze.py BL6, which
# keeps the old commands in the record's history; (3) clears the red-stop records and sets the slice back to building,
# which no script does yet (LINE_FAULTS_2026-11-18.md, F7). Then the conductor runs the builder once more: its Stop
# hook runs the corrected checks and writes the green test record the verifier needs.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
T=OspreyFlow_Build/process/lanes/v062/slices.tsv
R="${OSPREY_SLICE_HOME:-$HOME/.ospreyflow/slice-line}/records/BL6"
pgrep -f "slice_line/merge_slice.py" >/dev/null && { echo "a merge is running: wait for it, nothing changed"; exit 1; }
[ "$(git rev-parse --abbrev-ref HEAD)" = main ] || { echo "not on main"; exit 1; }
python3 - "$T" <<'PY'
import sys
p = sys.argv[1]
old, new = "&& make -C OspreyFlow_Build client-name-check", "&& make -C ../OspreyFlow_Build client-name-check"
rows = open(p).read().split("\n")
hit = [i for i, r in enumerate(rows) if r.startswith("BL6\t")]
assert len(hit) == 1 and rows[hit[0]].count(old) == 1, "BL6's row is not as expected: nothing changed"
rows[hit[0]] = rows[hit[0]].replace(old, new)
open(p, "w").write("\n".join(rows))
PY
git add -- "$T"
git commit -q -m "docs(process): BL6's frozen checks name the right path for its last step (the owner's refreeze)

Slice-Records: yes" -- "$T"
python OspreyFlow_Build/scripts/slice_line/refreeze.py BL6
rm -rf "$R/red_stops" "$R/red_stop.json"
python3 - "$R/state.json" <<'PY'
import json, sys
p = sys.argv[1]
s = json.load(open(p))
s.update(phase="building")
s.pop("note", None)
json.dump(s, open(p, "w"), indent=1)
PY
echo "BL6 is building again; the checks are corrected."
