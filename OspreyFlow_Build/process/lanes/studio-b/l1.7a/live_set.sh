#!/bin/sh
# L1.7a's live set: every live file the publish commit reaches, and the rights table.
cd ../OspreyFlow_Core && exec .venv/bin/pytest -c ../OspreyFlow_Build/pytest.ini -p no:cacheprovider -q -rfE \
  ../OspreyFlow_Build/tests/services/api/test_route_rights.py \
  ../OspreyFlow_Build/tests/ingest/test_studio_publish_pipeline.py \
  ../OspreyFlow_Build/tests/ingest/test_pipeline_run.py \
  ../OspreyFlow_Build/tests/ingest/test_staged_run.py \
  ../OspreyFlow_Build/tests/ingest/test_staged_pipeline_run.py \
  ../OspreyFlow_Build/tests/ingest/test_phase7_exit.py \
  ../OspreyFlow_Build/tests/ingest/test_pid_seed_live.py \
  ../OspreyFlow_Build/tests/scenarios/test_phase7_stage6c_watch_routes.py \
  ../OspreyFlow_Build/tests/scenarios/test_phase8_exit_criterion_end_to_end.py \
  ../OspreyFlow_Build/tests/scenarios/test_phase8_exit_over_the_wire.py \
  ../OspreyFlow_Build/tests/services/api/test_recipe_pins_lifespan.py \
  ../OspreyFlow_Build/tests/services/api/test_pin_calls_refresh_live.py \
  ../OspreyFlow_Build/tests/services/api/test_snapshot_withdrawal_tells_nothing_live.py \
  ../OspreyFlow_Build/tests/services/api/test_source_refresh_snapshot_live.py \
  ../OspreyFlow_Build/tests/services/api/test_studio_load_stamps_its_case_dataset_live.py \
  ../OspreyFlow_Build/tests/services/api/test_studio_run_now_stamps_its_case_dataset_live.py \
  ../OspreyFlow_Build/tests/services/api/test_packs.py
