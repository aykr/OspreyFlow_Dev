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
# Each refusal says what it did and did not do. Before the swap nothing of the live database has
# moved; once it has, the words say where each copy is. A <database>.before already there is a
# restore stopped between its renames, and this refuses until an operator has looked (the
# recovery runbook decides by whether <database>.restoring is still there).
set -u
db="$1"
zip="$2"
dbs="$3"
check="$4"
live="$dbs/$db"
new="$dbs/$db.restoring"
old="$dbs/$db.before"

# Before anything of the live database has moved: the restored copy removed, the live one as it was.
refuse() {
    rm -rf "$new"
    if [ -e "$live" ]; then
        echo "restore-graph refused: $1; the live database ($live) was not touched" >&2
    else
        echo "restore-graph refused: $1; there was no live database ($live) to keep" >&2
    fi
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
# The check from the zip's own folder (the Job's scratch): ArcadeDB opens ./log where it runs, and the
# Job's user (the chart's, not the image's) cannot write /home/arcadedb (R1, finding 11).
(cd "$(dirname "$zip")" && java -cp "/home/arcadedb/lib/*" "$check" "$new" "$zip") \
    || refuse "the restored database is not the set's"
aside=no
if [ -e "$live" ]; then
    mv "$live" "$old" || refuse "the live database could not be set aside"
    aside=yes
fi
# From here the live database has moved (when there was one): the words say where each copy is.
if ! mv "$new" "$live"; then
    if [ "$aside" = no ]; then
        echo "restore-graph refused: the restored database could not be put in place; it is at $new;" \
            "there was no live database" >&2
    elif mv "$old" "$live"; then
        echo "restore-graph refused: the restored database could not be put in place; the live one" \
            "was put back at $live; the restored one is at $new" >&2
    else
        echo "restore-graph refused: the restored database could not be put in place, nor the live" \
            "one put back: the live data is at $old, the restored at $new (the recovery runbook)" >&2
    fi
    exit 1
fi
if [ "$aside" = yes ] && ! rm -rf "$old"; then
    echo "restore-graph: $db restored from the set, checked and put in place; the old copy at $old" \
        "could not be removed: remove it before the next restore (the recovery runbook)" >&2
    exit 1
fi
if [ "$aside" = yes ]; then
    echo "restore-graph: $db restored from the set, checked and put in place; the old one removed"
else
    echo "restore-graph: $db restored from the set, checked and put in place; there was no live database"
fi
