# UPG's guards on the shared test server (P5b's `guarded`, in shell). Source it: `. upg_guard.sh`.
# Every compose call names project osprey-upg and the deployment's own compose file, which must be
# under the throwaway home and say `name: osprey-upg`; volume removal names osprey-upg_* alone; no
# prune and no image removal (images go through upg_images.py).
R=/root/osprey-runs/rules-upg
D=$R/home/.ospreyflow/deployments/osprey-upg
UPG=osprey-upg

dc() {
  case "$D/compose.yaml" in "$R"/home/*) ;; *) echo "REFUSED: compose file outside the throwaway home" >&2; return 2;; esac
  [ "$(sed -n 's/^name: *//p' "$D/compose.yaml" | head -1)" = "$UPG" ] || { echo "REFUSED: $D/compose.yaml is another project" >&2; return 2; }
  docker compose -p "$UPG" -f "$D/compose.yaml" --env-file "$D/deployment.env" "$@"
}

rm_volumes() {
  for v in "$@"; do
    case "$v" in osprey-upg_*|osprey-upg-*) ;; *) echo "REFUSED: volume $v is not this run's" >&2; return 2;; esac
  done
  [ $# -eq 0 ] || docker volume rm "$@"
}

api() { docker exec "$UPG-api-1" "$@"; }
