#!/usr/bin/env bash
# rules-b P3: the rebuild sheet's step 4 (process/lanes/demo/REBUILD_2026-11-18.md, "Before 07:00"),
# rehearsed on ospreyflow-test beside the leased stack, under the QUEUE. The image is built from this run
# copy's OspreyFlow_Core working tree (the branch's head, sent by stack_lease.sh remote), tagged
# ospreyflow-basemap:p3 (never Wednesday's :v0.6.0), and removed at the end. The tiles folder is a scratch
# one. The container is named rulesb-p3-basemap-tiles, not the sheet's osprey-basemap-tiles, so a leftover
# can never block Wednesday's real step by its name; otherwise the sheet's command runs as written.
# Never osprey-small: no container, volume, folder or image of it is named here.
# Every exit path (success, failure, stack_lease.sh stop) removes the container, the probe's database,
# the image and the scratch folder (the lane review's 1). Run by stack_lease.sh remote from OspreyFlow_Build.
set -u
TAG=ospreyflow-basemap:p3
NAME=rulesb-p3-basemap-tiles
SCR="$(cd ../.. && pwd)/rules-b.scratch/p3"
TILES="$SCR/tiles"
STOP="$SCR/stop"
JAR_URL=https://github.com/onthegomap/planetiler/releases/download/v0.10.2/planetiler.jar
JAR_SHA=f310bd0413e2e4512b27f4046d418664e8e1d3bf31603c2a70e23de06c167e4d
BASELINE_S=300
if docker image inspect "$TAG" >/dev/null 2>&1; then echo "$TAG exists already: not touched, stopping"; exit 1; fi
if docker ps -aq --filter "name=^${NAME}\$" | grep -q .; then echo "$NAME exists already: stopping"; exit 1; fi
PROBE=""; BUILT_IMAGE=""
cleanup() {
  rc=$?
  trap - EXIT INT TERM
  docker rm -f "$NAME" >/dev/null 2>&1 && echo "container $NAME removed"
  if [ -n "$PROBE" ]; then touch "$STOP" 2>/dev/null; wait "$PROBE" 2>/dev/null; fi
  [ -n "$BUILT_IMAGE" ] && docker image rm "$TAG" >/dev/null 2>&1 && echo "image $TAG removed"
  rm -rf "$SCR" && echo "scratch removed"
  echo "== EXIT $rc $(date -u +%FT%TZ)"
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 143' INT TERM
rm -rf "$SCR"; mkdir -p "$TILES/planetiler" "$TILES/built"
echo "== START $(date -u +%FT%TZ)"; uptime; free -m | head -2; nproc
echo "run copy's commit: $(cat ../.osprey-run-commit 2>/dev/null || git -C .. rev-parse HEAD 2>/dev/null || echo unknown)"
echo "disk before:"; df -h "$SCR" /var/lib/docker 2>/dev/null | awk 'NR==1 || !seen[$0]++'
echo "== 1. the image"
t0=$(date +%s)
( cd ../OspreyFlow_Core && docker build -q -t "$TAG" -f services/api/Dockerfile . ) | tail -1
docker image inspect "$TAG" >/dev/null 2>&1 || { echo "image build failed"; exit 1; }
BUILT_IMAGE=1
echo "image built in $(( $(date +%s) - t0 )) s: $(docker image inspect "$TAG" --format '{{.Id}} {{.Size}}')"
echo "== 2. the jar"
curl -fsSL -o "$TILES/planetiler/planetiler.jar" "$JAR_URL" || { echo "jar download failed"; exit 1; }
echo "$JAR_SHA  $TILES/planetiler/planetiler.jar" | sha256sum -c - || exit 1
chown -R 10001:10001 "$TILES/built"
echo "== 3. the stack's baseline, ${BASELINE_S} s"
rm -f "$STOP"
( cd ../OspreyFlow_Core && PYTHONPATH=.:packages .venv/bin/python -u \
    ../OspreyFlow_Build/process/lanes/rules-b/p3-rehearsal/probe.py "$STOP" \
    > "$SCR/probe.txt" 2> "$SCR/probe.err" ) &
PROBE=$!
sleep "$BASELINE_S"
kill -0 "$PROBE" 2>/dev/null || { echo "the probe died in the baseline:"; tail -5 "$SCR/probe.err"; exit 1; }
BASE=$(wc -l < "$SCR/probe.txt")
echo "== 4. the sheet's step 4, as written (the unit and by are placeholders' stand-ins; the name is the rehearsal's)"
t0=$(date +%s); peak=0; cg_peak=0; cg_swap=0
docker run --rm --name "$NAME" --label "osprey.run=${OSPREY_RUN_TAG:-rules-b-p3}" --memory 4g \
  -v "$TILES":/data/tiles:ro -v "$TILES/built":/data/tiles/built \
  --entrypoint python "$TAG" \
  -m services.api.map_admin build great-britain --stage tiles --unit unit-1 --by cli:rules-b \
  > "$SCR/tiles.log" 2>&1 &
RUN=$!
sleep 3
CID=$(docker ps -q --no-trunc --filter "name=^${NAME}\$")
CG=/sys/fs/cgroup/system.slice/docker-$CID.scope
while kill -0 "$RUN" 2>/dev/null; do
  m=$(docker stats --no-stream --format '{{.MemUsage}}' "$NAME" 2>/dev/null | awk '{print $1}')
  mb=$(echo "$m" | awk '/GiB/{sub("GiB","");printf "%d", $1*1024} /MiB/{sub("MiB","");printf "%d", $1}')
  [ -n "$mb" ] && [ "$mb" -gt "$peak" ] && peak=$mb
  # memory.peak is the cgroup's own high-water mark, so the last read before the exit is the true peak
  v=$(cat "$CG/memory.peak" 2>/dev/null) && [ -n "$v" ] && cg_peak=$(( v / 1048576 ))
  v=$(cat "$CG/memory.swap.peak" 2>/dev/null) && [ -n "$v" ] && cg_swap=$(( v / 1048576 ))
  sleep 2
done
wait "$RUN"; rc=$?
echo "step 4: exit $rc, $(( $(date +%s) - t0 )) s; cgroup memory.peak ${cg_peak} MB, memory.swap.peak ${cg_swap} MB (last read before exit); docker stats sampled peak ${peak} MB (limit 4 GiB)"
grep -E "Downloading|Running planetiler|Saving|Tiles built|Built |stopped|Error|Exception|OutOfMemory|overall" "$SCR/tiles.log" | grep -v "^\s*$" | tail -12
echo "last line: $(tail -1 "$SCR/tiles.log")"
touch "$STOP"; wait "$PROBE"; prc=$?; PROBE=""
echo "probe exit $prc$( [ -s "$SCR/probe.err" ] && echo "; its stderr: $(tail -3 "$SCR/probe.err" | tr '\n' ' ')")"
echo "== 5. the stack's latency (ms): baseline (samples 2 to $BASE) and during step 4 (warm-up sample dropped)"
awk -v b="$BASE" '$1=="sample" {print (NR<=b ? "base" : "run"), $3, $4}' "$SCR/probe.txt" > "$SCR/lat.txt"
for phase in base run; do
  for col in 2 3; do
    vals=$(awk -v p="$phase" -v c="$col" '$1==p {print $c}' "$SCR/lat.txt" | sort -n)
    n=$(echo "$vals" | grep -c .); [ "$n" -gt 0 ] || continue
    p50=$(echo "$vals" | awk -v n="$n" 'NR==int((n+1)/2)'); p95=$(echo "$vals" | awk -v n="$n" 'NR==int(n*0.95+0.999)'); mx=$(echo "$vals" | tail -1)
    echo "$phase $( [ $col = 2 ] && echo arcadedb || echo postgres ): n $n, p50 $p50, p95 $p95, max $mx"
  done
done
echo "== 6. what it wrote"; ls -l "$TILES/built" "$TILES/built/extracts" 2>/dev/null | awk '{print $3, $5, $9}'
du -sh "$TILES/built"/* 2>/dev/null
echo "disk after:"; df -h "$SCR" /var/lib/docker 2>/dev/null | awk 'NR==1 || !seen[$0]++'
echo "== END $(date -u +%FT%TZ)"; uptime; free -m | head -2
exit "$rc"
