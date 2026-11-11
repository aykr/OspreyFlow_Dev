#!/usr/bin/env bash
# P12 round 2: the --live plants alone, rerun after the first leased run printed no tally for them
# (process/lanes/case-b/P12_RED_RECORD.md). Same gateway pair and lease as p12_live_run.sh. Run from
# OspreyFlow_Build under `scripts/stack_lease.sh remote case-b -- bash process/lanes/case-b/p12_live_plants.sh`.
set -u
export OSPREY_LIVE_GATEWAY_URL=http://127.0.0.1:24000 OSPREY_LIVE_GATEWAY_MASTER=sk-ospreyflow-dev
cd ../OspreyFlow_Core || exit 1
echo "settings present (values hidden):"
env | grep -E '^OSPREY_(LANE|LEASE)|_PORT=' | sed 's/=.*/=(set)/' | sort
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python ../OspreyFlow_Build/process/lanes/case-b/plants_P12.py --live
echo "plants --live: exit $?"
echo "adapter put back: $(grep -c 'token = laurium_key(self._master)' packages/adapters/extract_laurium/adapter.py)"
echo "keys put back: $(grep -c 'fields = {"key": key, "models": list(models)}$' packages/adapters/extract_laurium/keys.py)"
