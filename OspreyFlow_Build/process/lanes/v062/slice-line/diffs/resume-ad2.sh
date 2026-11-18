#!/usr/bin/env bash
# For the owner to run, not an agent. Corrects AD2's frozen acceptance and checks and puts the slice back to building.
#     bash OspreyFlow_Build/process/lanes/v062/slice-line/diffs/resume-ad2.sh
# Run it when no merge is running (a commit on main during one makes that merge refuse: "main moved").
#
# What was wrong: both commands run Playwright (`npm run test:keyboard`) in a linked worktree, which refuses to start
# without OSPREY_PORTS_SLOT (apps/lanePorts.ts). The merge script's acceptance run sets none either. The builder's
# vitest part passed; the keyboard step failed six times, so the Stop hook stopped the slice. The conductor's error in
# the commands (18 November 2026), not the builder's.
# Proof of the corrected form: on main in a scratch worktree, with slot 16 exported before the `if`, the checks ran
# `npm ci`, vitest src/admin and keyboard/admin.spec.ts (47 passed), exit 0, and left no node_modules behind.
# (Slot 16 is not in scripts/lane_ports.tsv; 17 is GG1's. Playwright's ports are a base plus 100 x the slot, clear of
# the test stacks' ports in lane_stacks.tsv.)
#
# It: (1) adds `export OSPREY_PORTS_SLOT=16 &&` to AD2's two commands in slices.tsv, committed with the records
# trailer; (2) runs refreeze.py AD2 (the old commands stay in the record's history); (3) clears the red-stop records
# and sets the slice back to building (F7 in LINE_FAULTS_2026-11-18.md: nothing else does).
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
T=OspreyFlow_Build/process/lanes/v062/slices.tsv
R="${OSPREY_SLICE_HOME:-$HOME/.ospreyflow/slice-line}/records/AD2"
pgrep -f "slice_line/merge_slice.py" >/dev/null && { echo "a merge is running: wait for it, nothing changed"; exit 1; }
[ "$(git rev-parse --abbrev-ref HEAD)" = main ] || { echo "not on main"; exit 1; }
python3 - "$T" <<'PY'
import sys
p = sys.argv[1]
old, new = "cd OspreyFlow_Core && if [ -d node_modules ]", "cd OspreyFlow_Core && export OSPREY_PORTS_SLOT=16 && if [ -d node_modules ]"
rows = open(p).read().split("\n")
hit = [i for i, r in enumerate(rows) if r.startswith("AD2\t")]
assert len(hit) == 1 and rows[hit[0]].count(old) == 2, "AD2's row is not as expected: nothing changed"
rows[hit[0]] = rows[hit[0]].replace(old, new)
open(p, "w").write("\n".join(rows))
PY
git add -- "$T"
git commit -q -m "docs(process): AD2's frozen commands set the Playwright port slot (the owner's refreeze)

Slice-Records: yes" -- "$T"
python OspreyFlow_Build/scripts/slice_line/refreeze.py AD2
rm -rf "$R/red_stops" "$R/red_stop.json"
python3 - "$R/state.json" <<'PY'
import json, sys
p = sys.argv[1]
s = json.load(open(p))
s.update(phase="building")
s.pop("note", None)
json.dump(s, open(p, "w"), indent=1)
PY
echo "AD2 is building again; the commands are corrected."
