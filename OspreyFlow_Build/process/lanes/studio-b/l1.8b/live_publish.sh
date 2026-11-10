#!/bin/sh
# Part 2's live run, narrowed by the orchestrator to what the publish and the recipe repository reach: the rights
# table, the publish pipeline (write_and_commit_recipe into a repository real git made), the watch routes that
# publish through the Conduit, and then the slow seed, the publish lock's real second writer.
cd ../OspreyFlow_Core || exit 2
.venv/bin/pytest -c ../OspreyFlow_Build/pytest.ini -p no:cacheprovider -q -rA --durations=30 \
  ../OspreyFlow_Build/tests/services/api/test_route_rights.py \
  ../OspreyFlow_Build/tests/ingest/test_studio_publish_pipeline.py \
  ../OspreyFlow_Build/tests/scenarios/test_phase7_stage6c_watch_routes.py
a=$?
echo "# live files exit $a"
OSPREYFLOW_RUN_SLOW=1 .venv/bin/pytest -c ../OspreyFlow_Build/pytest.ini -p no:cacheprovider -q -rA --durations=30 \
  ../OspreyFlow_Build/tests/ingest/test_pid_seed_live.py
b=$?
echo "# slow seed exit $b"
[ $a -eq 0 ] && [ $b -eq 0 ]
