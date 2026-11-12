#!/bin/sh
# restore-graph (ADR-148 Amendment 7): ArcadeDB's database replaced from a set's zip, the live one
# kept until the restored one is proven. Run by the restore Job in ArcadeDB's own image, with the
# database's claim at $3 and ArcadeDB stopped:
#
#   sh restore-graph.sh <database> <zip> <databases folder> <check source>
#
# 1. ArcadeDB's restore writes the zip into <database>.restoring beside the live one (same claim).
# 2. The check (CheckDatabase.java) holds it to the zip's own index and opens it read-only, every
#    record read; a database ArcadeDB would open with a warning (a short or missing file) fails.
# 3. Only then the swap, by rename on the one claim: the live one to <database>.before, the
#    restored one in its place; the old one removed last.
#
# Any failure before the swap removes <database>.restoring and leaves the live database as it
# was, refused in words. A <database>.before already there is a restore stopped between its two
# renames: it holds the old data (the live folder may be missing), and this refuses until an
# operator has looked (the recovery runbook).
set -u
db="$1"
zip="$2"
dbs="$3"
check="$4"
live="$dbs/$db"
new="$dbs/$db.restoring"
old="$dbs/$db.before"

refuse() {
    rm -rf "$new"
    echo "restore-graph refused: $1; the live database ($live) was not touched" >&2
    exit 1
}

[ -n "$db" ] && [ -f "$zip" ] || refuse "no set's zip at $zip"
if [ -e "$old" ]; then
    echo "restore-graph refused: $old is there, a restore stopped between its renames; it holds" \
        "the old data: see the recovery runbook before restoring again" >&2
    exit 1
fi
rm -rf "$new" # a killed run's, never the live one
cd /home/arcadedb || refuse "no ArcadeDB in this image"
./bin/restore.sh -f "file://$zip" -d "$new" || refuse "ArcadeDB's restore of the set's zip failed"
java -cp "lib/*" "$check" "$new" "$zip" || refuse "the restored database is not the set's"
if [ -e "$live" ]; then
    mv "$live" "$old" || refuse "the live database could not be set aside"
fi
if ! mv "$new" "$live"; then
    [ -e "$old" ] && mv "$old" "$live"
    refuse "the restored database could not be put in place; the live one was put back"
fi
rm -rf "$old"
echo "restore-graph: $db restored from the set, checked and put in place; the old one removed"
