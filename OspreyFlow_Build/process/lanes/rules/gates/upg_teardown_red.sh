# Rule 15 for upg_run.sh's teardown: each refusal shown red, at the real call site (the teardown phase
# itself, sourcing upg_guard.sh), with a stand-in `docker` on PATH answering the calls it makes in the
# shapes the server gave (a failed `down -v`; a container left; an anonymous 64-hex volume no container
# mounts, as run 1, 2 and 4 left); another lane's new volumes are listed, not failed.
#   sh upg_teardown_red.sh > upg-teardown-red.txt
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
mkdir -p "$T/tools" "$T/logs" "$T/bin" "$T/home/.ospreyflow/deployments/osprey-upg"
cp "$HERE/upg_run.sh" "$HERE/upg_guard.sh" "$T/tools/"
printf 'name: osprey-upg\nservices: {}\n' > "$T/home/.ospreyflow/deployments/osprey-upg/compose.yaml"
: > "$T/home/.ospreyflow/deployments/osprey-upg/deployment.env"
BEFORE_ANON=$(printf 'a%.0s' $(seq 64))
printf '%s\nosprey-small_postgres-data\n' "$BEFORE_ANON" | sort > "$T/logs/volumes.before"
cat > "$T/bin/docker" <<'EOF'
#!/bin/sh
# The stand-in: SHIM_DOWN_RC, SHIM_LEFT (container ids), SHIM_VOLUMES and SHIM_MOUNTED (volume names).
case "$*" in
  compose*down*) echo "stand-in: compose down"; exit "${SHIM_DOWN_RC:-0}" ;;
  "ps -a -q --filter label="*) for c in ${SHIM_LEFT:-}; do echo "$c"; done ;;
  "ps -a -q --filter volume="*) all="$*"; v=${all##*volume=}; for m in ${SHIM_MOUNTED:-}; do [ "$m" = "$v" ] && echo c0ffee; done; exit 0 ;;
  "volume ls -q --filter "*) : ;;
  "volume ls -q") for v in ${SHIM_VOLUMES:-}; do echo "$v"; done ;;
  "volume rm"*) echo "stand-in: $*" ;;
  *) echo "stand-in: unexpected call: $*" >&2; exit 9 ;;
esac
EOF
chmod +x "$T/bin/docker"
NEW_ANON=$(printf 'b%.0s' $(seq 64))
case_() {
  label=$1; want=$2; shift 2
  echo "--- $label (want exit $want)"
  env "$@" UPG_ROOT="$T" PATH="$T/bin:$PATH" sh "$T/tools/upg_run.sh" teardown 2>&1 | sed 's/^/    /'
  got=$(env "$@" UPG_ROOT="$T" PATH="$T/bin:$PATH" sh "$T/tools/upg_run.sh" teardown >/dev/null 2>&1; echo $?)
  [ "$got" = "$want" ] && echo "    exit $got: as wanted" || { echo "    exit $got: WRONG"; FAILED=1; }
}
FAILED=0
ALL="$BEFORE_ANON osprey-small_postgres-data"
case_ "red: down -v failed (the run-2 shape)" 2 SHIM_DOWN_RC=1 SHIM_VOLUMES="$ALL"
case_ "red: a container of the project left" 2 SHIM_LEFT=deadbeef SHIM_VOLUMES="$ALL"
case_ "red: an anonymous volume no container mounts, new since the run began" 2 SHIM_VOLUMES="$ALL $NEW_ANON"
case_ "green: another lane's new named volume, listed" 0 SHIM_VOLUMES="$ALL osprey-test-c_pg"
case_ "green: a new anonymous volume a live container mounts, listed" 0 SHIM_VOLUMES="$ALL $NEW_ANON" SHIM_MOUNTED="$NEW_ANON"
case_ "green: nothing new" 0 SHIM_VOLUMES="$ALL"
echo "--- $( [ $FAILED = 0 ] && echo 'every case as wanted' || echo 'A CASE WAS WRONG')"
exit $FAILED
