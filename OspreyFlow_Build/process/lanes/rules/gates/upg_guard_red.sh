# Rule 15 for upg_guard.sh, at its real call sites with the shapes they receive: rm_volumes is given
# `docker volume ls -q` names; dc reads the deployment's own compose.yaml. A stand-in docker records
# any call that gets through. Each case prints its command, then its output (stdout and stderr together).
#   sh upg_guard_red.sh > upg-guard-red.txt
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
mkdir -p "$T/bin" "$T/home/.ospreyflow/deployments/osprey-upg"
printf '#!/bin/sh\necho "stand-in docker reached: $*"\n' > "$T/bin/docker"; chmod +x "$T/bin/docker"
C="$T/home/.ospreyflow/deployments/osprey-upg/compose.yaml"
run() { echo "--- $1"; echo "\$ $2"; ( UPG_ROOT="$T"; PATH="$T/bin:$PATH"; . "$HERE/upg_guard.sh"; eval "$2" ) 2>&1 | sed 's/^/    /'; }
printf 'name: osprey-upg\nservices: {}\n' > "$C"
run "red: another project's volume, as docker volume ls names it" "rm_volumes osprey-small_postgres-data osprey-upg_postgres-data"
run "green: the run's own volumes" "rm_volumes osprey-upg_postgres-data osprey-upg_valkey-data"
run "green: the run's own compose file" "dc down -v"
printf 'name: osprey-small\nservices: {}\n' > "$C"
run "red: the deployment's compose file names another project" "dc down -v"
echo "--- note: dc's path check (compose file outside the throwaway home) cannot fail as called, since D is"
echo "    built from R; the real protection is the hard-coded -p osprey-upg on every compose call."
