#!/usr/bin/env bash
# rules-b P3: the rebuild sheet's step 4 (process/lanes/demo/REBUILD_2026-11-18.md, "Before 07:00"),
# rehearsed on ospreyflow-test beside the leased stack, under the QUEUE. The image is built from a
# git-archive copy of this run copy's OspreyFlow_Core (the branch's head), tagged as the sheet tags it,
# and removed at the end. The tiles folder is a scratch one. Never osprey-small: no container, volume,
# folder or image of it is named here. Run by stack_lease.sh remote from OspreyFlow_Build.
set -u
TAG=ospreyflow-basemap:p3   # the orchestrator: never Wednesday's name (ospreyflow-basemap:v0.6.0)
SCR="$(cd ../.. && pwd)/rules-b.scratch/p3"
TILES="$SCR/tiles"
JAR_URL=https://github.com/onthegomap/planetiler/releases/download/v0.10.2/planetiler.jar
JAR_SHA=f310bd0413e2e4512b27f4046d418664e8e1d3bf31603c2a70e23de06c167e4d
if docker image inspect "$TAG" >/dev/null 2>&1; then echo "$TAG exists already: not touched, stopping"; exit 1; fi
rm -rf "$SCR"; mkdir -p "$TILES/planetiler" "$TILES/built"
echo "== START $(date -u +%FT%TZ)"; uptime; free -m | head -2; nproc
echo "== 1. the image"
t0=$(date +%s)
( cd ../OspreyFlow_Core && docker build -q -t "$TAG" -f services/api/Dockerfile . ) | tail -1
echo "image built in $(( $(date +%s) - t0 )) s: $(docker image inspect "$TAG" --format '{{.Id}} {{.Size}}')"
echo "== 2. the jar"
curl -fsSL -o "$TILES/planetiler/planetiler.jar" "$JAR_URL" || { echo "jar download failed"; exit 1; }
echo "$JAR_SHA  $TILES/planetiler/planetiler.jar" | sha256sum -c - || exit 1
chown -R 10001:10001 "$TILES/built"
echo "== 3. the stack's baseline, 60 s"
STOP="$SCR/stop"; rm -f "$STOP"
( cd ../OspreyFlow_Core && PYTHONPATH=.:packages .venv/bin/python -u \
    ../OspreyFlow_Build/process/lanes/rules-b/p3-rehearsal/probe.py "$STOP" > "$SCR/probe.txt" 2>&1 ) &
PROBE=$!
sleep 60; BASE=$(wc -l < "$SCR/probe.txt")
echo "== 4. the sheet's step 4, as written (the unit and by are placeholders' stand-ins)"
t0=$(date +%s); peak=0
docker run --rm --name osprey-basemap-tiles --memory 4g \
  -v "$TILES":/data/tiles:ro -v "$TILES/built":/data/tiles/built \
  --entrypoint python "$TAG" \
  -m services.api.map_admin build great-britain --stage tiles --unit unit-1 --by cli:rules-b \
  > "$SCR/tiles.log" 2>&1 &
RUN=$!
sleep 5
while kill -0 "$RUN" 2>/dev/null; do
  m=$(docker stats --no-stream --format '{{.MemUsage}}' osprey-basemap-tiles 2>/dev/null | awk '{print $1}')
  mb=$(echo "$m" | awk '/GiB/{sub("GiB","");printf "%d", $1*1024} /MiB/{sub("MiB","");printf "%d", $1}')
  [ -n "$mb" ] && [ "$mb" -gt "$peak" ] && peak=$mb
  sleep 5
done
wait "$RUN"; rc=$?
echo "step 4: exit $rc, $(( $(date +%s) - t0 )) s, container peak ${peak} MB (limit 4 GiB)"
grep -E "Downloading|Running planetiler|Saving|Tiles built|Built |stopped|Error|Exception|OutOfMemory|overall" "$SCR/tiles.log" | grep -v "^\s*$" | tail -12
echo "last line: $(tail -1 "$SCR/tiles.log")"
touch "$STOP"; wait "$PROBE"
echo "== 5. the stack's latency (ms): baseline (first $BASE samples) and during step 4"
awk -v b="$BASE" 'NR<=b {print "base", $2, $3} NR>b {print "run", $2, $3}' "$SCR/probe.txt" | sort -k1,1 -k2,2n > "$SCR/lat.txt"
for phase in base run; do
  for col in 2 3; do
    vals=$(awk -v p="$phase" '$1==p' "$SCR/probe.txt" >/dev/null; awk -v p="$phase" -v c="$col" '$1==p {print $c}' "$SCR/lat.txt" | sort -n)
    n=$(echo "$vals" | grep -c .); [ "$n" -gt 0 ] || continue
    p50=$(echo "$vals" | awk -v n="$n" 'NR==int((n+1)/2)'); p95=$(echo "$vals" | awk -v n="$n" 'NR==int(n*0.95+0.999)'); mx=$(echo "$vals" | tail -1)
    echo "$phase $( [ $col = 2 ] && echo arcadedb || echo postgres ): n $n, p50 $p50, p95 $p95, max $mx"
  done
done
echo "== 6. what it wrote"; ls -l "$TILES/built" "$TILES/built/extracts" 2>/dev/null | awk '{print $3, $5, $9}'
du -sh "$TILES/built"/* 2>/dev/null
echo "== END $(date -u +%FT%TZ)"; uptime; free -m | head -2
docker image rm "$TAG" >/dev/null && echo "image $TAG removed"
rm -rf "$SCR"; echo "scratch removed"
