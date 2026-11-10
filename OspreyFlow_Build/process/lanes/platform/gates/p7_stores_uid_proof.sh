#!/usr/bin/env bash
# P7's exit (spec/06_DECISIONS.md ADR-148 decision 3): ArcadeDB, ClickHouse and Keeper, the third-party
# images the profile runs, each started as 10001:10001 on volumes given to group 10001, as a pod's
# fsGroup gives them, until it answers its own health check. On the test server, from OspreyFlow_Core:
#   OspreyFlow_Build/scripts/stack_lease.sh offline platform -- bash ../OspreyFlow_Build/process/lanes/platform/gates/p7_stores_uid_proof.sh
# Everything is named osprey-p7-stores-* and removed at the end, pass or fail.
set -uo pipefail
P=osprey-p7-stores
fails=0
say() { printf '\n== %s\n' "$*"; }
ok() { printf 'PASS  %s\n' "$*"; }
bad() { printf 'FAIL  %s\n' "$*"; fails=$((fails + 1)); }
cleanup() {
  docker rm -f $(docker ps -aq --filter "name=^$P") >/dev/null 2>&1
  docker volume rm $(docker volume ls -q --filter "name=^$P") >/dev/null 2>&1
}
trap cleanup EXIT
say "3. ArcadeDB, ClickHouse and Keeper as 10001:10001, their volumes given to group 10001 (a pod's fsGroup)"
# Mounted `nocopy`: Docker would otherwise copy the image folder's own owner (1000) onto an empty
# volume, which a Kubernetes claim never does; the kubelet gives it to the pod's fsGroup instead.
given() {  # given <volume> : make it, owned root:10001 and group-writable, as the kubelet's fsGroup does
  docker volume create "$1" >/dev/null
  docker run --rm -v "$1:/v" busybox:1.36 sh -c 'chgrp 10001 /v && chmod 2775 /v'
}
wait_healthy() {  # wait_healthy <name> <command…>
  local n="$1"; shift
  for i in $(seq 1 90); do docker exec "$n" "$@" >/dev/null 2>&1 && return 0; sleep 2; done; return 1
}
for v in arcadedb-databases arcadedb-config arcadedb-log arcadedb-backups arcadedb-replication clickhouse-data clickhouse-log keeper-data keeper-coordination keeper-log; do given "$P-$v"; done
docker run -d --name "$P-arcadedb" --user 10001:10001 \
  -v "$P-arcadedb-databases:/home/arcadedb/databases:nocopy" -v "$P-arcadedb-config:/home/arcadedb/config:nocopy" \
  -v "$P-arcadedb-log:/home/arcadedb/log:nocopy" -v "$P-arcadedb-backups:/home/arcadedb/backups:nocopy" \
  -v "$P-arcadedb-replication:/home/arcadedb/replication:nocopy" \
  -e JAVA_OPTS="-Darcadedb.server.rootPassword=throwaway-p7" arcadedata/arcadedb:26.10.1 >/dev/null
if wait_healthy "$P-arcadedb" wget -q -O /dev/null http://127.0.0.1:2480/api/v1/ready; then  # the render's own check
  ok "arcadedb answers ready as $(docker exec "$P-arcadedb" id)"
else bad "arcadedb as 10001"; docker logs "$P-arcadedb" 2>&1 | tail -15; fi
docker run -d --name "$P-clickhouse" --user 10001:10001 \
  -v "$P-clickhouse-data:/var/lib/clickhouse:nocopy" -v "$P-clickhouse-log:/var/log/clickhouse-server:nocopy" \
  -e CLICKHOUSE_USER=osprey -e CLICKHOUSE_PASSWORD=throwaway-p7 clickhouse/clickhouse-server:25.8.33.6 >/dev/null
if wait_healthy "$P-clickhouse" wget -q -O /dev/null http://127.0.0.1:8123/ping; then
  ok "clickhouse answers ping as $(docker exec "$P-clickhouse" id)"
else bad "clickhouse as 10001"; docker logs "$P-clickhouse" 2>&1 | tail -15; fi
docker run -d --name "$P-keeper" --user 10001:10001 \
  -v "$P-keeper-data:/var/lib/clickhouse:nocopy" -v "$P-keeper-coordination:/var/lib/clickhouse/coordination:nocopy" -v "$P-keeper-log:/var/log/clickhouse-keeper:nocopy" \
  clickhouse/clickhouse-keeper:25.8.33.6 >/dev/null
if wait_healthy "$P-keeper" sh -c 'echo ruok | nc -w 2 127.0.0.1 9181 | grep -q imok'; then
  ok "keeper answers imok as $(docker exec "$P-keeper" id)"
else bad "keeper as 10001"; docker logs "$P-keeper" 2>&1 | tail -15; fi

say "result: $fails failure(s)"
exit $((fails > 0))
