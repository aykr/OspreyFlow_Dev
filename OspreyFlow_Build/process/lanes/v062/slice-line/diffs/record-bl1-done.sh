#!/usr/bin/env bash
# For the owner to run, not an agent (the guard refuses an agent the line's records). Records BL1, the slice line's
# set-up, as done, with the owner's hand merge as its evidence. Run from the main checkout:
#     bash OspreyFlow_Build/process/lanes/v062/slice-line/diffs/record-bl1-done.sh
#
# Why a record is needed: board.py shows a slice done only from records/<slice id>/merged.json, with a test-run name,
# plus a verify-<tip>.json whose verdict is pass for that tip. BL1's merge was written by hand (a0dc7ac, the owner's
# word, 18 November 2026) under the id "setup-a0dc7ac", and no verifier session ever ran, so neither exists under the
# id BL1. This writes them, saying exactly what they are:
#   - the merge record moves to records/BL1, naming its tip (f4aded4) and, as its test run, the GitHub run that went
#     green on the merge commit (44257704285), which is the full gate's evidence on a0dc7ac;
#   - a verify record that says in its own words it is the owner's attestation, with no verifier session.
# Nothing else is changed. merge_slice.py would refuse that verify record for a merge (it needs a verifier session
# that did not build the slice); only the board reads it, and only to show BL1 done.
set -euo pipefail
R="${OSPREY_SLICE_HOME:-$HOME/.ospreyflow/slice-line}/records"
TIP=f4aded488eb9f0c7a6ef9abfb232990bfbb6c253
MERGE=a0dc7ac385fb1da0b66a5aa80fa139583721a34c
BASE=79b9095bd9a5e4cc4b027518867f0fc019b6e931
RUN=github-run-44257704285
[ -d "$R/setup-a0dc7ac" ] || { echo "no $R/setup-a0dc7ac: already moved?"; exit 1; }
[ ! -e "$R/BL1" ] || { echo "$R/BL1 already exists: nothing changed"; exit 1; }
git rev-parse --verify -q "$MERGE^{commit}" >/dev/null && [ "$(git rev-parse "$MERGE^2")" = "$TIP" ] \
  || { echo "a0dc7ac's second parent is not $TIP: nothing changed"; exit 1; }
mv "$R/setup-a0dc7ac" "$R/BL1"
python3 - "$R/BL1" "$TIP" "$MERGE" "$BASE" "$RUN" <<'PY'
import json, sys, datetime
d, tip, merge, base, run = sys.argv[1:]
m = json.load(open(f"{d}/merged.json"))
m.update(slice="BL1", build="BL1", tip=tip, base=base, acceptance_run=run, gate_run=run,
         verifier=[{"session": "owner-attestation", "note": "no verifier session ran"}],
         recorded_by="owner", recorded_at=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
json.dump(m, open(f"{d}/merged.json", "w"), indent=1)
v = {"slice": "BL1", "commit": tip, "verdict": "pass", "passes": [],
     "attested_by": "owner",
     "note": ("The owner's attestation, not a verifier's pass: the set-up was merged by hand on the owner's word "
              "(a0dc7ac, 18 November 2026) after the full gate was green; GitHub's run 44257704285 on that merge "
              "commit succeeded. No verifier session ran on BL1."),
     "at": m["recorded_at"]}
json.dump(v, open(f"{d}/verify-{tip}.json", "w"), indent=1)
PY
echo "BL1 recorded. The board:"
python OspreyFlow_Build/scripts/slice_line/board.py | head -8
