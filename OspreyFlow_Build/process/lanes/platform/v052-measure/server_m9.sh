#!/usr/bin/env bash
# M9's live-file runs on the test server, where the docker CLI may be called (the Mac's guard refuses it, the stand-in's
# too). No container is touched: the live case's `docker` is a stand-in on PATH that stops and starts a stub's index.
#   OspreyFlow_Build/scripts/stack_lease.sh offline platform -- bash OspreyFlow_Build/process/lanes/platform/v052-measure/server_m9.sh
# Green: both live-run cases pass. Red: the live case's verdict check planted out, the silent fallback's case must fail;
# then the file put back.
set -uo pipefail
cd OspreyFlow_Core || exit 1
LIVE=../OspreyFlow_Build/tests/perf/test_search_budget_live.py
run() { .venv/bin/python -m pytest -c ../OspreyFlow_Build/pytest.ini -p no:cacheprovider -q -rfs \
  ../OspreyFlow_Build/tests/test_measure_search.py -k "$1" 2>&1 | tail -3; return "${PIPESTATUS[0]}"; }
echo "# green: the live M9 case, passing and failing as it should"
run "live_gate and m9"; green=$?
echo "# green exit $green"
cp "$LIVE" "$LIVE.orig"
python3 - "$LIVE" <<'PY'
import sys
p = sys.argv[1]; s = open(p).read()
old = '    assert found["verdict"] == "met", "M9: " + "; ".join(found["failures"])'
assert s.count(old) == 1
open(p, "w").write(s.replace(old, "    assert found"))
PY
echo "# red: the live M9 case's verdict check planted out"
run "fails_m9_when_the_fallback_is_silent"; red=$?
echo "# red exit $red"
mv "$LIVE.orig" "$LIVE"
[ "$green" -eq 0 ] && [ "$red" -ne 0 ]
