#!/usr/bin/env bash
# For the owner to run, not an agent. Brings main into BL6's branch so it merges cleanly, and sends it for one more check.
#     bash OspreyFlow_Build/process/lanes/v062/slice-line/diffs/resume-bl6-merge-main.sh
# Run it when no merge is running (the script refuses if one is).
#
# What happened: `merge_slice.py merge BL6` refused ("does not merge cleanly onto main"). The only conflict is RULINGS.md:
# allow-bl6-round-3.sh committed a copy of main's RULINGS.md on BL6's branch (so the builder and verifier would read the
# owner's ruling on the three compressed files), and main's RULINGS.md has changed several times since. The conductor's
# design error; resume-ad2-round-2.sh no longer does it, and the line-fixes brief says how the rulings should reach a
# worktree (not as a commit on its branch).
#
# It: (1) merges main into BL6's branch in its worktree, taking main's text for the conflicting RULINGS.md hunks, and
# checks that RULINGS.md then equals main's exactly (otherwise it undoes the merge and stops); (2) writes a findings
# record so the builder's prompt says what happened and to change nothing else; (3) sets BL6 back to building (round 3 of 3).
# The new tip needs a green test record (the builder's Stop hook writes it) and a new verifier pass; the old pass was for the
# old tip.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
R="${OSPREY_SLICE_HOME:-$HOME/.ospreyflow/slice-line}/records/BL6"
W="$HOME/dev/osprey-wt/slice-BL6"
RULINGS=OspreyFlow_Build/process/lanes/v062/RULINGS.md
pgrep -f "slice_line/merge_slice.py" >/dev/null && { echo "a merge is running: wait for it, nothing changed"; exit 1; }
[ "$(git rev-parse --abbrev-ref HEAD)" = main ] || { echo "not on main"; exit 1; }
grep -q '"phase": "verified"' "$R/state.json" || { echo "BL6 is not in the verified phase: nothing changed"; exit 1; }
[ -z "$(git -C "$W" status --porcelain --untracked-files=no)" ] || { echo "BL6's worktree has uncommitted changes: nothing changed"; exit 1; }
OLD="$(git -C "$W" rev-parse HEAD)"
git -C "$W" merge --no-edit -X theirs main >/dev/null || { git -C "$W" merge --abort || true; echo "the merge failed beyond RULINGS.md: nothing changed"; exit 1; }
if ! git -C "$W" diff --quiet main -- "$RULINGS"; then
  git -C "$W" reset -q --hard "$OLD"
  echo "RULINGS.md is not main's after the merge: undone, nothing changed"; exit 1
fi
TIP="$(git -C "$W" rev-parse HEAD)"
python3 - "$R" "$TIP" <<'PY'
import json, sys, time
d, tip = sys.argv[1:]
finding = {
    "file": "OspreyFlow_Build/process/lanes/v062/RULINGS.md",
    "what": ("The merge script refused the branch (\"does not merge cleanly onto main\"): main's RULINGS.md had changed since a "
             "copy of it was committed on this branch. Main has now been merged into this branch, taking main's text for "
             "RULINGS.md. Change nothing else. Run the checks and the acceptance command; if either is red, the cause is in "
             "what main brought in (for example a new document that names the client), and the fix is a reword."),
    "evidence": "git log --oneline -3 shows the merge commit; RULINGS.md equals main's.",
}
rec = {"slice": "BL6", "commit": tip, "verdict": "findings", "passes": [], "findings": [finding],
       "note": "written by the owner's resume-bl6-merge-main.sh; not a verifier session",
       "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
json.dump(rec, open(f"{d}/verify-gate-{tip}.json", "w"), indent=1)
s = json.load(open(f"{d}/state.json"))
s.update(phase="building")
s.pop("note", None)
json.dump(s, open(f"{d}/state.json", "w"), indent=1)
PY
echo "main is merged into BL6's branch ($OLD -> $TIP); BL6 is building again. The conductor runs the builder, then the verifier."
