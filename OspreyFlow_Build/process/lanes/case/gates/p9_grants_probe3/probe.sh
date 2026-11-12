set -u
I=clickhouse/clickhouse-server:25.8.33.6
N=p9-grants-c
docker rm -f $N >/dev/null 2>&1
docker run -d --name $N -e CLICKHOUSE_USER=osprey -e CLICKHOUSE_PASSWORD=pw \
  -v "$PWD/users.xml:/etc/clickhouse-server/users.d/zz-p9.xml:ro" -v "$PWD/disk.xml:/etc/clickhouse-server/config.d/zz-disk.xml:ro" "$I" >/dev/null
for i in $(seq 1 60); do docker exec $N clickhouse-client -u osprey --password pw -q "SELECT 1" >/dev/null 2>&1 && break; sleep 1; done
q() { echo "-- [$1] $2"; docker exec $N clickhouse-client -u "$1" --password "$3" --max_execution_time 20 -q "$2" 2>&1 | sed 's/Received from localhost:9000. //' | cut -c1-400 | head -3; }
o() { q osprey "$1" pw; }; b() { q backup "$1" bpw; }
echo "=== the backup user's grants, with the wildcard"
b "SHOW GRANTS"
o "CREATE DATABASE ospreyflow"
o "CREATE TABLE ospreyflow.t (x UInt8) ENGINE=MergeTree ORDER BY x"
o "INSERT INTO ospreyflow.t VALUES (1),(2),(3)"
echo "=== the restore's own sequence as backup (Disk standing for S3; the grants are the same)"
b "BACKUP DATABASE ospreyflow TO Disk('backups', 's1')"
o "INSERT INTO ospreyflow.t VALUES (4)"
b "DROP DATABASE IF EXISTS ospreyflow_restoring_s1 SYNC"
b "CREATE DATABASE ospreyflow_restoring_s1"
b "RESTORE DATABASE ospreyflow AS ospreyflow_restoring_s1 FROM Disk('backups', 's1') SETTINGS allow_different_database_def = true"
b "RENAME DATABASE ospreyflow TO ospreyflow_before_s1"
b "RENAME DATABASE ospreyflow_restoring_s1 TO ospreyflow"
b "DROP DATABASE ospreyflow_before_s1 SYNC"
o "SELECT count() FROM ospreyflow.t"
echo "=== the prefix grant on the live database itself (ospreyflow*: matches ospreyflow, as intended)"
b "CREATE TABLE ospreyflow.u (x UInt8) ENGINE=MergeTree ORDER BY x"
b "DROP TABLE ospreyflow.u SYNC"
echo "=== the backup user outside its own (refused), a name merely containing the word included"
b "CREATE DATABASE x_ospreyflow"
o "CREATE DATABASE x_ospreyflow"
b "DROP DATABASE x_ospreyflow"
b "CREATE TABLE x_ospreyflow.t (x UInt8) ENGINE=MergeTree ORDER BY x"
o "DROP DATABASE x_ospreyflow"
b "CREATE DATABASE elsewhere"
o "CREATE DATABASE elsewhere"
b "DROP DATABASE elsewhere"
o "DROP DATABASE elsewhere"
echo "=== osprey's RESTORE (the kind finding), as the entrypoint's grants less S3, URL, BACKUP"
o "RESTORE DATABASE ospreyflow AS stolen FROM Disk('backups', 's1')"
o "RESTORE TABLE ospreyflow.t AS ospreyflow.t_stolen FROM Disk('backups', 's1')"
o "SELECT count() FROM ospreyflow.t_stolen"
docker rm -f $N >/dev/null
echo "left: $(docker ps -a --format '{{.Names}}' | grep -c p9-grants)"
