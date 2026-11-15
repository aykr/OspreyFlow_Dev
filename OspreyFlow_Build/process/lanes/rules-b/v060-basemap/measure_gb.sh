#!/usr/bin/env bash
# rules-b v060-basemap: the great-britain basemap measured under the lease (v0.6.0 item 10; the
# orchestrator's word, 15 Nov). Run by stack_lease.sh remote from OspreyFlow_Build. planetiler runs in
# the Conduit's own image (ospreyflow/api:ci, its digest-pinned Temurin runtime, ADR-147 Am 2) with only
# the scratch folder mounted; the loader runs from this run copy against the leased stack. Never
# osprey-small: no container, volume or file of it is named here. The scratch folder is removed at the
# end, after its sizes are recorded.
set -u
SCR="$(cd ../.. && pwd)/rules-b.scratch/v060-basemap"
IMAGE=ospreyflow/api:ci
JAR_URL=https://github.com/onthegomap/planetiler/releases/download/v0.10.2/planetiler.jar
PBF_URL="$(cd ../OspreyFlow_Core && .venv/bin/python -c 'from scripts.build_local_basemap import GEOFABRIK_REGIONS as G; print(G["great-britain"])')"
mkdir -p "$SCR/out"
echo "== START $(date -u +%FT%TZ)"; uptime; free -m | head -2; df -h / | tail -1; nproc
echo "== image"; docker image inspect "$IMAGE" --format '{{.Id}} {{.Created}}'
docker run --rm --entrypoint /opt/java/bin/java "$IMAGE" -version 2>&1 | head -2
echo "== downloads"
t0=$(date +%s)
curl -fsSL -o "$SCR/planetiler.jar" "$JAR_URL" || { echo "jar download failed"; exit 1; }
curl -fsSL -o "$SCR/great-britain.osm.pbf" "$PBF_URL" || { echo "extract download failed"; exit 1; }
echo "downloads: $(( $(date +%s) - t0 )) s"; ls -l "$SCR"/planetiler.jar "$SCR"/great-britain.osm.pbf | awk '{print $5, $9}'
sha256sum "$SCR/planetiler.jar" | cut -c1-64

planetiler() {  # $1 heap
  local name="rulesb-planetiler-$$" peak=0 t0 rc
  t0=$(date +%s)
  docker run -d --name "$name" --user 0:0 -v "$SCR:/work" --entrypoint /opt/java/bin/java "$IMAGE" \
    "-Xmx$1" -jar /work/planetiler.jar --osm-path=/work/great-britain.osm.pbf \
    --output=/work/out/great-britain.pmtiles --download --download_dir=/work/out/sources --force >/dev/null
  while [ "$(docker inspect -f '{{.State.Running}}' "$name" 2>/dev/null)" = "true" ]; do
    m=$(docker stats --no-stream --format '{{.MemUsage}}' "$name" 2>/dev/null | awk '{print $1}')
    mb=$(echo "$m" | awk '/GiB/{sub("GiB","");printf "%d", $1*1024} /MiB/{sub("MiB","");printf "%d", $1} /KiB/{print 0}')
    [ -n "$mb" ] && [ "$mb" -gt "$peak" ] && peak=$mb
    sleep 5
  done
  rc=$(docker inspect -f '{{.State.ExitCode}}' "$name"); oom=$(docker inspect -f '{{.State.OOMKilled}}' "$name")
  docker logs "$name" 2>&1 | grep -E "Finished in|OutOfMemory|Exception|ERROR|overall" | tail -8
  docker rm "$name" >/dev/null
  echo "planetiler -Xmx$1: exit $rc, oom-killed $oom, $(( $(date +%s) - t0 )) s, container peak ${peak} MB"
  return "$rc"
}
echo "== planetiler"
planetiler 2g || { echo "== planetiler again at 4g"; planetiler 4g; }
ls -l "$SCR/out/great-britain.pmtiles" 2>/dev/null | awk '{print "pmtiles", $5}'
echo "== the gazetteer load (batched, with points)"
( cd ../OspreyFlow_Core && PYTHONPATH=.:packages .venv/bin/python -u \
    ../OspreyFlow_Build/process/lanes/rules-b/v060-basemap/measure_load.py load \
    "$SCR/great-britain.osm.pbf" "$SCR" ); echo "loader exit $?"
echo "== the count of named points against settlements (a second pass, capped at 45 min)"
( cd ../OspreyFlow_Core && PYTHONPATH=.:packages timeout 2700 .venv/bin/python -u \
    ../OspreyFlow_Build/process/lanes/rules-b/v060-basemap/measure_load.py count \
    "$SCR/great-britain.osm.pbf" ); echo "count exit $? (124: stopped at the cap)"
echo "== disk"; du -sh "$SCR"/great-britain.osm.pbf "$SCR"/out/sources "$SCR"/out/great-britain.pmtiles "$SCR"/analytics.duckdb "$SCR" 2>/dev/null
echo "== END $(date -u +%FT%TZ)"; uptime; free -m | head -2
rm -rf "$SCR"; echo "scratch removed"
