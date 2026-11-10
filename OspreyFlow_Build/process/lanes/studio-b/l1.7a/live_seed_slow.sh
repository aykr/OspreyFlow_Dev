#!/bin/sh
# L1.7a's slow seed: the Prison Intelligence seed is the second process the publish flock serialises, so its
# live file runs in full (OSPREYFLOW_RUN_SLOW=1), after live_set.sh, in the same leased run.
cd ../OspreyFlow_Core && OSPREYFLOW_RUN_SLOW=1 exec .venv/bin/pytest -c ../OspreyFlow_Build/pytest.ini \
  -p no:cacheprovider -q -rA ../OspreyFlow_Build/tests/ingest/test_pid_seed_live.py
