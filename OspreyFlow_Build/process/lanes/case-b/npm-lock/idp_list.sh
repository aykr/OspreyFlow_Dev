#!/usr/bin/env bash
# List only: every osprey-test-idp-* container and network on this host, with when it was made, its state, and
# its bind mounts' sources (a test's tmp_path names the pytest session that made it). Removes nothing.
echo "listed at $(date -u +%Y-%m-%dT%H:%M:%SZ) on $(hostname)"
echo "== containers"
for c in $(docker ps -a --filter name=osprey-test-idp- --format '{{.Names}}'); do
  docker inspect -f '{{.Name}} created={{.Created}} state={{.State.Status}} mounts={{range .Mounts}}{{.Source}} {{end}}' "$c"
done
echo "== networks"
for n in $(docker network ls --filter name=osprey-test-idp- --format '{{.Name}}'); do
  docker network inspect -f '{{.Name}} created={{.Created}} containers={{len .Containers}}' "$n"
done
echo "== pytest sessions of root made since 04:25Z"
find /tmp/pytest-of-root -maxdepth 1 -name 'pytest-*' -newermt '2026-11-14 04:25:00Z' -printf '%f %TY-%Tm-%TdT%TH:%TM\n' 2>/dev/null | sort
