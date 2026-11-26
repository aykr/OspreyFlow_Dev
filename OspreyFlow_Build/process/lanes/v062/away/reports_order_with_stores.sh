#!/bin/sh
# Inside the D246 namespace (`REPO=~/away-ro bash ~/osprey-d246/d246_ns.sh sh <this> <command…>`): throwaway
# stores for test_reports.py, shaped as the `conformance` job's services start, then the command, then
# everything stopped and deleted. Derived from away/ci-reds's ci_reds_with_stores.sh, with two changes:
#   1. ArcadeDB is left FRESH: no `ospreyflow` database is created (the job's service starts with none;
#      ci_reds_with_stores.sh created one, which hides the order dependency this branch fixes). Postgres's
#      `ospreyflow` database is still created, as the job's POSTGRES_DB does.
#   2. The fixture passwords are read from the workflow file at run time (its published service values,
#      for these throwaway stores only) and never echoed or written outside the store's own temp folder.
# Binaries: ~/ci-reds-pg (PostgreSQL 16, ArcadeDB 26.10.1 on Temurin 21, Redis 7 for Valkey). Not run on CI.
set -eu
R=/home/ospreyflow_build/ci-reds-pg
export LD_LIBRARY_PATH=$R/root/usr/lib/x86_64-linux-gnu
PGB=$R/root/usr/lib/postgresql/16/bin
D=$(mktemp -d "$TMPDIR/stores.XXXXXX")
cleanup() {
  "$PGB/pg_ctl" -D "$D/data" -m immediate stop >/dev/null 2>&1 || true
  [ -n "${ARC:-}" ] && kill "$ARC" 2>/dev/null || true
  [ -n "${RED:-}" ] && kill "$RED" 2>/dev/null || true
  sleep 1; rm -rf "$D"
}
trap cleanup EXIT
WF=../.github/workflows/ci.yml
pw() { .venv/bin/python -c "
import re, sys
m = re.search(r'^\s*' + sys.argv[1] + r':\s*\"?([^\"\s]+)', open(sys.argv[2]).read(), re.M)
sys.stdout.write(m.group(1))" "$1" "$WF"; }
PGPW=$(pw POSTGRES_PASSWORD); ARPW=$(pw ARCADEDB_ROOT_PASSWORD)
[ -n "$PGPW" ] && [ -n "$ARPW" ] || { echo "stores: no fixture password found" >&2; exit 3; }
umask 077
printf %s "$PGPW" > "$D/pw"
"$PGB/initdb" -D "$D/data" -U osprey --pwfile="$D/pw" --auth-local=trust --auth-host=scram-sha-256 -E UTF8 >/dev/null
printf "listen_addresses='127.0.0.1,::1'\nport=58432\nunix_socket_directories='%s'\nmax_connections=400\nfsync=off\n" "$D" >> "$D/data/postgresql.conf"
"$PGB/pg_ctl" -D "$D/data" -l "$D/pg.log" -w start >/dev/null
"$R/root/usr/bin/redis-server" --port 56379 --bind 127.0.0.1 --save '' --appendonly no --dir "$D" >"$D/redis.log" 2>&1 &
RED=$!
cp -r "$R/opt/arcadedb-26.10.1" "$D/arcadedb"
( cd "$D/arcadedb" && JAVA_HOME="$R/opt/jdk-21.0.13.1+2-jre" PATH="$R/opt/jdk-21.0.13.1+2-jre/bin:$PATH" \
  JAVA_OPTS="-Darcadedb.server.rootPassword=$ARPW -Darcadedb.gremlin.engine=groovy -Darcadedb.server.httpIncomingPort=52480 -Darcadedb.server.httpIncomingHost=127.0.0.1" \
  ARCADEDB_OPTS_MEMORY="-Xms1G -Xmx4G" exec bin/server.sh ) >"$D/arcadedb.log" 2>&1 &
ARC=$!
PGPW="$PGPW" .venv/bin/python -c "
import asyncio, asyncpg, os, time, urllib.request
async def m():
    c = await asyncpg.connect(host='127.0.0.1', port=58432, user='osprey', password=os.environ['PGPW'], database='postgres')
    await c.execute('CREATE DATABASE ospreyflow'); await c.close()
asyncio.run(m())
for _ in range(120):
    try:
        urllib.request.urlopen('http://127.0.0.1:52480/api/v1/ready', timeout=2); break
    except Exception: time.sleep(1)
else: raise SystemExit('arcadedb did not become ready')
"
export POSTGRES_HOST=localhost POSTGRES_PORT=58432 POSTGRES_USER=osprey POSTGRES_PASSWORD="$PGPW" POSTGRES_DB=ospreyflow
export ARCADEDB_HOST=localhost ARCADEDB_HTTP_PORT=52480 ARCADEDB_ROOT_PASSWORD="$ARPW"
export VALKEY_HOST=localhost VALKEY_PORT=56379
export STORES_DIR="$D"
unset PGPW ARPW
"$@"
