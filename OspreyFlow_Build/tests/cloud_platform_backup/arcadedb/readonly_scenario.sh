#!/bin/sh
# restore-graph as the restore Job runs it (R1, finding 11): as the chart's user (10001), who cannot
# write the image's own folders (`docker run --user 10001:10001`); /work is the
# claim and the scratch. Prints: readonly exit=<n> denied=<count> traces=<count> | <the script's last words>.
cd /home/arcadedb
J() { java -cp "lib/*" "$@" 2>/dev/null; }
mkdir -p /work/databases /work/sets
J /src/MakeDatabase.java /work/made/set 30 set
J com.arcadedb.integration.backup.Backup -d /work/made/set -f /work/sets/ospreyflow.zip > /dev/null 2>&1
J /src/MakeDatabase.java /work/databases/ospreyflow 5 live
sh /src/restore-graph.sh ospreyflow /work/sets/ospreyflow.zip /work/databases /src/CheckDatabase.java > /work/out 2>&1
code=$?
echo "readonly exit=$code denied=$(grep -c AccessDeniedException /work/out)" \
     "traces=$(grep -c '^[[:space:]]*at ' /work/out) | $(tail -1 /work/out | cut -c1-300)"
