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
# `mv` and `rm` that fail for one path's source (FAIL_MV, FAIL_MV2) or target (FAIL_RM) alone, as
# a full or read-only claim would: the swap's own failures, which nothing else can cause here.
mkdir -p /work/shim
cat > /work/shim/mv <<'SHIM'
#!/bin/sh
for a in "$@"; do case "$a" in -*) ;; *) src="$a"; break;; esac; done
if [ -n "${FAIL_MV:-}" ] && [ "$src" = "$FAIL_MV" ]; then echo "mv: cannot move '$src': No space left on device" >&2; exit 1; fi
if [ -n "${FAIL_MV2:-}" ] && [ "$src" = "$FAIL_MV2" ]; then echo "mv: cannot move '$src': No space left on device" >&2; exit 1; fi
exec /bin/mv "$@"
SHIM
cat > /work/shim/rm <<'SHIM'
#!/bin/sh
for a in "$@"; do [ -n "${FAIL_RM:-}" ] && [ "$a" = "$FAIL_RM" ] && { echo "rm: cannot remove '$a': Read-only file system" >&2; exit 1; }; done
exec /bin/rm "$@"
SHIM
chmod +x /work/shim/mv /work/shim/rm
run() { PATH="/work/shim:$PATH" sh /src/restore-graph.sh ospreyflow "$1" $DBS "$2" > /work/out 2>&1; }
clear() { rm -rf $DBS/ospreyflow $DBS/ospreyflow.restoring $DBS/ospreyflow.before; }

clear; live; run /work/sets/ospreyflow.zip /src/CheckDatabase.java; state restored $?
clear; live; run /work/sets/half.zip /src/CheckDatabase.java; state truncated-zip $?
clear; live; run /work/sets/ospreyflow.zip /src/FailingCheck.java; state check-refuses $?
clear; live; mkdir $DBS/ospreyflow.before; run /work/sets/ospreyflow.zip /src/CheckDatabase.java; state before-left $?
clear; live; mkdir -p $DBS/ospreyflow.restoring; echo x > $DBS/ospreyflow.restoring/junk; run /work/sets/ospreyflow.zip /src/CheckDatabase.java; state restoring-left $?
clear; run /work/sets/ospreyflow.zip /src/CheckDatabase.java; state live-lost $?
clear; live; run /work/sets/missing.zip /src/CheckDatabase.java; state no-zip $?
clear; run /work/sets/missing.zip /src/CheckDatabase.java; state no-zip-no-live $?
clear; live; (export FAIL_MV=$DBS/ospreyflow.restoring; run /work/sets/ospreyflow.zip /src/CheckDatabase.java); state put-in-fails $?
clear; live; (export FAIL_MV=$DBS/ospreyflow.restoring FAIL_MV2=$DBS/ospreyflow.before; run /work/sets/ospreyflow.zip /src/CheckDatabase.java); state put-back-fails $?
clear; live; (export FAIL_RM=$DBS/ospreyflow.before; run /work/sets/ospreyflow.zip /src/CheckDatabase.java); state old-not-removed $?
