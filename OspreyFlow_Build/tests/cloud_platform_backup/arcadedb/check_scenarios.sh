#!/bin/sh
# The check's scenarios, in ArcadeDB's own image: a database restored from a real set's zip, then
# damaged the ways ArcadeDB itself opens with only a warning. One line each: <name> exit=<n> | <words>.
cd /home/arcadedb
J() { java -cp "lib/*" "$@" 2>/dev/null; }
J /src/MakeDatabase.java /work/made 2000 set
J com.arcadedb.integration.backup.Backup -d /work/made -f /work/set.zip > /dev/null 2>&1
./bin/restore.sh -f file:///work/set.zip -d /work/restored > /dev/null 2>&1
check() { java -cp "lib/*" /src/CheckDatabase.java "$2" "${3:-/work/set.zip}" > /work/out 2>&1; e=$?; echo "$1 exit=$e | $(grep -v WARN /work/out | grep . | tail -1 | cut -c1-300)"; }
damaged() { rm -rf /work/d; cp -r /work/restored /work/d; }
check restored /work/restored
big=$(ls -S /work/restored | grep bucket | head -1)
[ "$(wc -c < /work/restored/$big)" -gt 65536 ] || echo "setup exit=1 | $big is one page: the cuts below would prove nothing"
damaged; head -c 1000 /work/restored/$big > /work/d/$big; check bucket-cut-mid-page /work/d
damaged; head -c 65536 /work/restored/$big > /work/d/$big; check bucket-cut-to-one-page /work/d
damaged; : > /work/d/schema.json; check schema-empty /work/d
damaged; rm /work/d/$big; check bucket-missing /work/d
check no-database /work/none
# A page file the zip does not name, not a whole number of pages: only the page check sees it.
damaged; head -c 1000 /work/restored/$big > /work/d/Stray_0.99.65536.v0.bucket; check stray-short-page-file /work/d
# A zip holding no file at all (its end record alone, 22 bytes): only the entries check refuses it.
printf 'PK\005\006\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000' > /work/empty.zip
check empty-zip /work/restored /work/empty.zip
