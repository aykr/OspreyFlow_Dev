#!/usr/bin/env bash
# tests/test_stack_lease.py with the host as busy as a night of lane runs leaves it: 2,000 more processes (idle
# sleeps), ended when the file has run. Offline, on closed ports. Run from OspreyFlow_Build.
set -u
pids=(); for i in $(seq 1 2000); do sleep 900 & pids+=($!); done
# With busy as the first argument, CPU taken too, as make test -n auto on a shared host takes it: one burner for
# every two cores, for as long as the file runs, ended with the sleeps.
if [ "${1:-}" = busy ]; then shift; for i in $(seq 1 $(( $(nproc) / 2 ))); do ( while :; do :; done ) & pids+=($!); done; echo "burners: $(( $(nproc) / 2 )) of $(nproc) cores"; fi
echo "processes on the host: $(ls -d /proc/[0-9]* | wc -l)"
cd ../OspreyFlow_Core && .venv/bin/pytest -c ../OspreyFlow_Build/pytest.ini -p no:cacheprovider -q ../OspreyFlow_Build/tests/test_stack_lease.py "$@"
rc=$?
kill "${pids[@]}" 2>/dev/null; wait 2>/dev/null
exit $rc
