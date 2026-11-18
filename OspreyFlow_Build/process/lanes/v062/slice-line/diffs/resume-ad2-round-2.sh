#!/usr/bin/env bash
# For the owner to run, not an agent. Sends AD2 back for one more builder round after the merge gate refused it, with the
# server-side scan that caught it added to its checks.
#     bash OspreyFlow_Build/process/lanes/v062/slice-line/diffs/resume-ad2-round-2.sh
# Run it when no merge is running (the script refuses if one is). The conductor says when none is.
#
# What happened: the verifier passed AD2 at 993a434, then the merge gate's `make test` failed on the merge result:
# tests/services/api/test_admin_sections.py reads 69 more routes into the People section, and `schedule_preview_route`
# is now read by People as well as Operations. AD2's new code in People.tsx pulls other workspace modules into the section's
# walk. The slice's checks did not include that scan, so neither the builder's Stop hook nor the verifier saw it.
#
# It: (1) adds the pytest step for test_admin_sections.py to AD2's checks in slices.tsv and commits that one row with the
# records trailer (the step was proved green on main in a scratch worktree before this script was written); (2) runs
# refreeze.py AD2; (3) writes the gate's failure as a findings record, so the builder's prompt carries it (the builder
# reads only the newest verify-*.json for findings); (4) sets AD2 back to building for round 2 of 2. The verifier's pass
# record for 993a434 stays; a new tip needs a new pass. (It does NOT copy RULINGS.md into the worktree: a copy committed on a
# slice's branch conflicts with main the next time main's RULINGS.md changes, which is what refused BL6's merge.)
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
T=OspreyFlow_Build/process/lanes/v062/slices.tsv
R="${OSPREY_SLICE_HOME:-$HOME/.ospreyflow/slice-line}/records/AD2"
W="$HOME/dev/osprey-wt/slice-AD2"
RULINGS=OspreyFlow_Build/process/lanes/v062/RULINGS.md
pgrep -f "slice_line/merge_slice.py" >/dev/null && { echo "a merge is running: wait for it, nothing changed"; exit 1; }
[ "$(git rev-parse --abbrev-ref HEAD)" = main ] || { echo "not on main"; exit 1; }
[ "$(python3 -c "import json;print(json.load(open('$R/state.json'))['phase'])")" = verified ] || { echo "AD2 is not in the verified phase: nothing changed"; exit 1; }
python3 - "$T" <<'PY'
import sys
p = sys.argv[1]
step = (" && ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9 UV_PYTHON=3.12 UV_PROJECT_ENVIRONMENT=$HOME/dev/osprey-acceptance/AD2 "
        "uv run --frozen pytest -c ../OspreyFlow_Build/pytest.ini -q "
        "../OspreyFlow_Build/tests/services/api/test_admin_sections.py")
rows = open(p).read().split("\n")
hit = [i for i, r in enumerate(rows) if r.startswith("AD2\t")]
assert len(hit) == 1, "AD2's row not found: nothing changed"
f = rows[hit[0]].split("\t")
assert len(f) == 10 and "test_admin_sections" not in f[9], "AD2's row is not as expected: nothing changed"
f[9] += step
rows[hit[0]] = "\t".join(f)
open(p, "w").write("\n".join(rows))
PY
git add -- "$T"
git commit -q -m "docs(process): AD2's checks include test_admin_sections.py, the scan that refused its first merge (the owner's refreeze)

Slice-Records: yes" -- "$T"
python OspreyFlow_Build/scripts/slice_line/refreeze.py AD2
TIP="$(git rev-parse lane/slice-AD2)"
python3 - "$R" "$TIP" <<'PY'
import json, sys, time
d, tip = sys.argv[1:]
finding = {
    "file": "OspreyFlow_Core/apps/workspace/src/admin/sections/People.tsx",
    "what": ("The merge gate's `make test` failed on the merge result: "
             "OspreyFlow_Build/tests/services/api/test_admin_sections.py fails for the people section "
             "(test_each_built_section_s_routes_need_its_right[people]: 69 more routes are read than the section's right "
             "guards, the first POST /v1/investigations; test_each_section_s_routes_refuse_a_principal_without_its_right[people]; "
             "test_each_shared_read_is_read_by_exactly_the_sections_named: `schedule_preview_route` is now read by people as "
             "well as operations). The new code in People.tsx imports something that pulls other workspace modules into the "
             "section's walk. Fix the imports, not the test: read what the form needs (the inviter's clearance and "
             "receivable codes) without importing the modules that carry those other routes, for example through a prop the "
             "place already holds. That test is now in the slice's checks, so the Stop hook runs it."),
    "evidence": ("merge log ~/.ospreyflow/slice-line/records/AD2/ (the newest merge-*.log): "
                 "`make test: exit 2`; the invitation tests (vitest and keyboard) passed on the merge result."),
}
rec = {"slice": "AD2", "commit": tip, "verdict": "findings", "passes": [], "findings": [finding],
       "note": "written by the owner's resume-ad2-round-2.sh from the merge gate's refusal; not a verifier session",
       "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
json.dump(rec, open(f"{d}/verify-gate-{tip}.json", "w"), indent=1)
PY
python3 - "$R/state.json" <<'PY'
import json, sys
p = sys.argv[1]
s = json.load(open(p))
s.update(phase="building", round=2)
s.pop("note", None)
json.dump(s, open(p, "w"), indent=1)
PY
echo "AD2 is back to building for round 2 of 2; the conductor runs the builder."
