#!/usr/bin/env bash
# For the owner to run, not an agent. Sends GG6 back for a third builder round after the merge gate refused it.
#     bash OspreyFlow_Build/process/lanes/v062/slice-line/diffs/resume-gg6-round-3.sh
# Run it when no merge is running (the script refuses if one is). The conductor says when none is.
#
# What happened: the verifier passed GG6 at 654172a (round 2 of 2). The merge gate's `make -k ci` then failed in `lint`:
# `eslint .` (OspreyFlow_Core's `npm run lint`) read the production bundle that the acceptance command's `vite build` leaves
# in apps/workspace/map-build/dist inside the tree (895 errors in two built .js files). The slice added that folder to
# OspreyFlow_Core/.gitignore but not to eslint.config.js's `ignores`, where the other built folders
# (apps/workspace/dist, apps/harness/dist) are. Any developer running the acceptance run and then `make lint` would hit
# it. The slice's own commands never ran lint after the build, so neither the builder's Stop hook nor the verifier saw it.
# Everything else in the gate was green; the tiles, the performance gate and `make trivy` passed.
#
# It: (1) edits GG6's row in slices.tsv and commits it with the records trailer: `npm run lint` is added as the last step
# of the acceptance command (after the build, so it proves the folder is ignored), and the slice's support files are added
# to acceptance_files, so the merge script's red-before run copies them to the base (on 18 November its red was "Cannot
# find module mapTilesFixture", not the page running 4.7.1); (2) runs refreeze.py GG6; (3) writes the gate's failure as a
# findings record for the builder's prompt; (4) gives GG6 a third round (limit 3) and sets it to building.
# Not copied into the worktree: RULINGS.md (a copy committed on a branch conflicts with main later; see resume-bl6-merge-main.sh).
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
T=OspreyFlow_Build/process/lanes/v062/slices.tsv
R="${OSPREY_SLICE_HOME:-$HOME/.ospreyflow/slice-line}/records/GG6"
pgrep -f "slice_line/merge_slice.py" >/dev/null && { echo "a merge is running: wait for it, nothing changed"; exit 1; }
[ "$(git rev-parse --abbrev-ref HEAD)" = main ] || { echo "not on main"; exit 1; }
grep -q '"phase": "verified"' "$R/state.json" || { echo "GG6 is not in the verified phase: nothing changed"; exit 1; }
python3 - "$T" <<'PY'
import sys
p = sys.argv[1]
W = "OspreyFlow_Core/apps/workspace/"
more = [W + f for f in ("keyboard/mapTilesFixture.ts", "keyboard/map-tiles-harness.html", "keyboard/map-tiles-harness.tsx",
                         "keyboard/fixtures/map-tiles.pmtiles", "map-build/ports.ts", "map-build/vite.config.ts")]
rows = open(p).read().split("\n")
hit = [i for i, r in enumerate(rows) if r.startswith("GG6\t")]
assert len(hit) == 1, "GG6's row not found: nothing changed"
f = rows[hit[0]].split("\t")
assert len(f) == 10 and "npm run lint" not in f[8], "GG6's row is not as expected: nothing changed"
assert f[8].count("&& make trivy)") == 1 and f[8].count("&& make trivy; rc=$?") == 1, "GG6's acceptance is not as expected: nothing changed"
f[8] = f[8].replace("&& make trivy)", "&& make trivy && npm run lint)").replace("&& make trivy; rc=$?", "&& make trivy && npm run lint; rc=$?")
have = f[7].split(",")
f[7] = ",".join(have + [m for m in more if m not in have])
rows[hit[0]] = "\t".join(f)
open(p, "w").write("\n".join(rows))
PY
git add -- "$T"
git commit -q -m "docs(process): GG6's acceptance ends with lint after the build, and names its support files (the owner's refreeze)

Slice-Records: yes" -- "$T"
python OspreyFlow_Build/scripts/slice_line/refreeze.py GG6
TIP="$(git rev-parse lane/slice-GG6)"
python3 - "$R" "$TIP" <<'PY'
import json, sys, time
d, tip = sys.argv[1:]
finding = {
    "file": "OspreyFlow_Core/eslint.config.js",
    "what": ("The merge gate's `make -k ci` failed in `lint` (`eslint .`, `npm run lint` from OspreyFlow_Core): it read the "
             "production bundle that the acceptance run's `vite build` leaves in apps/workspace/map-build/dist inside the tree "
             "(895 errors in the two built .js files there: map-tiles-harness-*.js and maplibre-gl-worker-*.js). The slice "
             "added that folder to OspreyFlow_Core/.gitignore but not to the `ignores` list in eslint.config.js, which names "
             "the other built folders (apps/workspace/dist/**, apps/harness/dist/**). Add apps/workspace/map-build/dist/** there. "
             "The acceptance command now ends with `npm run lint` after the build, so the Stop hook proves it. Change nothing "
             "else: tiles, the performance gate and `make trivy` passed."),
    "evidence": ("merge log ~/.ospreyflow/slice-line/records/GG6/ (the newest merge-*.log): `make[1]: *** [lint] Error 1`, "
                 "`895 problems`, file paths under map-build/dist/assets/."),
}
rec = {"slice": "GG6", "commit": tip, "verdict": "findings", "passes": [], "findings": [finding],
       "note": "written by the owner's resume-gg6-round-3.sh from the merge gate's refusal; not a verifier session",
       "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
json.dump(rec, open(f"{d}/verify-gate-{tip}.json", "w"), indent=1)
s = json.load(open(f"{d}/state.json"))
s.update(phase="building", round=3, rounds_limit=3)
s.pop("note", None)
json.dump(s, open(f"{d}/state.json", "w"), indent=1)
PY
echo "GG6 is back to building for round 3 of 3; the conductor runs the builder."
