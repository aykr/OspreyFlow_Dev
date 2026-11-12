#!/bin/sh
# restore-graph's scenarios, in ArcadeDB's own image: /src holds the script, the check and these
# helpers; /work is the test's own folder. Each scenario prints one line: <name> exit=<n>
# live=<mark count|none> restoring=<yes|no> before=<yes|no> | <the script's last words>.
cd /home/arcadedb
J() { java -cp "lib/*" "$@" 2>/dev/null; }
DBS=/work/databases
mkdir -p $DBS /work/sets
J /src/MakeDatabase.java /work/made/set 300 set
J com.arcadedb.integration.backup.Backup -d /work/made/set -f /work/sets/ospreyflow.zip > /dev/null 2>&1
s=$(wc -c < /work/sets/ospreyflow.zip); head -c $((s / 2)) /work/sets/ospreyflow.zip > /work/sets/half.zip
live() { J /src/MakeDatabase.java $DBS/ospreyflow 25 live; }
state() {
  echo "$1 exit=$2 live=$(J /src/CountPeople.java $DBS/ospreyflow | tail -1)" \
       "restoring=$([ -e $DBS/ospreyflow.restoring ] && echo yes || echo no)" \
       "before=$([ -e $DBS/ospreyflow.before ] && echo yes || echo no) | $(tail -1 /work/out | cut -c1-300)"
}
run() { sh /src/restore-graph.sh ospreyflow "$1" $DBS "$2" > /work/out 2>&1; }
clear() { rm -rf $DBS/ospreyflow $DBS/ospreyflow.restoring $DBS/ospreyflow.before; }

clear; live; run /work/sets/ospreyflow.zip /src/CheckDatabase.java; state restored $?
clear; live; run /work/sets/half.zip /src/CheckDatabase.java; state truncated-zip $?
clear; live; run /work/sets/ospreyflow.zip /src/FailingCheck.java; state check-refuses $?
clear; live; mkdir $DBS/ospreyflow.before; run /work/sets/ospreyflow.zip /src/CheckDatabase.java; state before-left $?
clear; live; mkdir -p $DBS/ospreyflow.restoring; echo x > $DBS/ospreyflow.restoring/junk; run /work/sets/ospreyflow.zip /src/CheckDatabase.java; state restoring-left $?
clear; run /work/sets/ospreyflow.zip /src/CheckDatabase.java; state live-lost $?
clear; live; run /work/sets/missing.zip /src/CheckDatabase.java; state no-zip $?
