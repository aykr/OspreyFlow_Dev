#!/usr/bin/env bash
# P7's exit (spec/06_DECISIONS.md ADR-148 decision 3): every third-party image the profile runs (ArcadeDB,
# ClickHouse, Keeper, LiteLLM, and postgres as the two init containers that make Keycloak's and the
# gateway's databases) started as the chart starts it: 10001:10001, every capability dropped, no new
# privileges, the stores on volumes given to group 10001 as a pod's fsGroup gives them, until each
# answers its own health check or does its own job. On the test server, from OspreyFlow_Core:
#   OspreyFlow_Build/scripts/stack_lease.sh offline platform -- bash ../OspreyFlow_Build/process/lanes/platform/gates/p7_stores_uid_proof.sh
# Everything is named osprey-p7-stores-* and removed at the end, pass or fail.
set -uo pipefail
P=osprey-p7-stores
fails=0
say() { printf '\n== %s\n' "$*"; }
ok() { printf 'PASS  %s\n' "$*"; }
bad() { printf 'FAIL  %s\n' "$*"; fails=$((fails + 1)); }
# As the chart's podSecurity and container securityContext run every container.
HARDEN=(--user 10001:10001 --cap-drop ALL --security-opt no-new-privileges)
cleanup() {
  docker network rm "$P" >/dev/null 2>&1
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
docker run -d --name "$P-arcadedb" "${HARDEN[@]}" \
  -v "$P-arcadedb-databases:/home/arcadedb/databases:nocopy" -v "$P-arcadedb-config:/home/arcadedb/config:nocopy" \
  -v "$P-arcadedb-log:/home/arcadedb/log:nocopy" -v "$P-arcadedb-backups:/home/arcadedb/backups:nocopy" \
  -v "$P-arcadedb-replication:/home/arcadedb/replication:nocopy" \
  -e JAVA_OPTS="-Darcadedb.server.rootPassword=throwaway-p7" arcadedata/arcadedb:26.10.1 >/dev/null
if wait_healthy "$P-arcadedb" wget -q -O /dev/null http://127.0.0.1:2480/api/v1/ready; then  # the render's own check
  ok "arcadedb answers ready as $(docker exec "$P-arcadedb" id)"
else bad "arcadedb as 10001"; docker logs "$P-arcadedb" 2>&1 | tail -15; fi
docker run -d --name "$P-clickhouse" "${HARDEN[@]}" \
  -v "$P-clickhouse-data:/var/lib/clickhouse:nocopy" -v "$P-clickhouse-log:/var/log/clickhouse-server:nocopy" \
  -e CLICKHOUSE_USER=osprey -e CLICKHOUSE_PASSWORD=throwaway-p7 clickhouse/clickhouse-server:25.8.33.6 >/dev/null
if wait_healthy "$P-clickhouse" wget -q -O /dev/null http://127.0.0.1:8123/ping; then
  ok "clickhouse answers ping as $(docker exec "$P-clickhouse" id)"
else bad "clickhouse as 10001"; docker logs "$P-clickhouse" 2>&1 | tail -15; fi
docker run -d --name "$P-keeper" "${HARDEN[@]}" \
  -v "$P-keeper-data:/var/lib/clickhouse:nocopy" -v "$P-keeper-coordination:/var/lib/clickhouse/coordination:nocopy" -v "$P-keeper-log:/var/log/clickhouse-keeper:nocopy" \
  clickhouse/clickhouse-keeper:25.8.33.6 >/dev/null
if wait_healthy "$P-keeper" sh -c 'echo ruok | nc -w 2 127.0.0.1 9181 | grep -q imok'; then
  ok "keeper answers imok as $(docker exec "$P-keeper" id)"
else bad "keeper as 10001"; docker logs "$P-keeper" 2>&1 | tail -15; fi

say "3. postgres as the init containers (keycloak-db, litellm-db), then LiteLLM, as 10001 with every capability dropped"
# The stand-in for RDS runs as its image's own user: it is the platform's, not one of our pods.
# The render's own references (harness/render.py's POSTGRES_IMAGE, which the render pins by the digest
# the registry gives, and the gateway's pin there). Until 11 November this named a postgres digest and a
# Docker Hub LiteLLM that do not exist ("not found"), so this section had never run as committed.
POSTGRES=postgres:16.4
LITELLM=ghcr.io/berriai/litellm@sha256:d295634e09c648dcdb72c4cc2dd226f5fb87823a73e88cbbed6f205e4deb044b
echo "postgres: $POSTGRES, image $(docker image inspect --format '{{.Id}}' "$POSTGRES" 2>/dev/null || echo 'not here')"
echo "litellm: $LITELLM"
docker network create "$P" >/dev/null
docker run -d --name "$P-rds" --network "$P" -e POSTGRES_USER=osprey -e POSTGRES_PASSWORD=throwaway-p7 "$POSTGRES" >/dev/null
wait_healthy "$P-rds" pg_isready -U osprey || bad "the RDS stand-in never answered"
for db in keycloak litellm; do  # the render's own init SQL, its role and database made if absent
  if docker run --rm --network "$P" "${HARDEN[@]}" -e PGPASSWORD=throwaway-p7 -e PW=throwaway-db "$POSTGRES" sh -c "
      id; psql -h $P-rds -U osprey -d postgres -v ON_ERROR_STOP=1 -v pw=\"\$PW\" <<'SQL'
SELECT 'CREATE ROLE $db LOGIN' WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$db')\\gexec
ALTER ROLE $db WITH LOGIN PASSWORD :'pw';
SELECT 'CREATE DATABASE $db OWNER $db' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$db')\\gexec
SQL"; then ok "the $db-db init container made its database as 10001, no capabilities"
  else bad "the $db-db init container as 10001"; fi
done
printf 'model_list: []\ngeneral_settings: {}\n' > "/tmp/$P-litellm.yaml"
docker run -d --name "$P-litellm" --network "$P" "${HARDEN[@]}" \
  -v "/tmp/$P-litellm.yaml:/app/config.yaml:ro" \
  -e LITELLM_MASTER_KEY=sk-throwaway-p7 -e LITELLM_SALT_KEY=throwaway-p7 -e LITELLM_LOCAL_MODEL_COST_MAP=True \
  -e STORE_MODEL_IN_DB=True -e DATABASE_URL="postgresql://litellm:throwaway-db@$P-rds:5432/litellm" \
  "$LITELLM" --config /app/config.yaml --port 4000 >/dev/null
if wait_healthy "$P-litellm" python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:4000/health/liveliness')"; then
  ok "litellm answers liveliness as $(docker exec "$P-litellm" id)"
else bad "litellm as 10001"; docker logs "$P-litellm" 2>&1 | tail -20; fi
rm -f "/tmp/$P-litellm.yaml"

say "result: $fails failure(s)"
exit $((fails > 0))
