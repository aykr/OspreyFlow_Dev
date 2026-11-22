#!/usr/bin/env bash
# Monday's clean-up of the early-warning runner (DEMO_SERVER_EARLY_WARNING_BRIEF.md, point 7). Run by the owner as root.
#
#   sudo bash cleanup.sh --dry-run    lists what it would remove; removes nothing
#   sudo bash cleanup.sh              removes it, and lists what it removed
#
# It removes only what install.sh and the runner made: the runner's containers, networks, volumes and images (those
# whose name starts osprey-early- AND that carry the label osprey.early=1; nothing else, whatever its name), the
# runner's jobs (its account's processes), the shield (its unit and its nftables table), the summary's units, table and
# account (010), the key's line in authorized_keys (by its marker comment), the systemd
# drop-in, linger, the account, and the folder (the source copy, the jobs, the tools, the caches). Run twice, the
# second run lists nothing.
set -euo pipefail

ROOT="${OSPREY_EARLY_ROOT:-/var/lib/osprey-early}"
USER_NAME="${OSPREY_EARLY_USER:-osprey-early}"
SUMMARY_USER="${OSPREY_EARLY_SUMMARY_USER:-osprey-summary}"
DROPIN_BASE="${OSPREY_EARLY_DROPIN_BASE:-/etc/systemd/system}"
UNIT_DIR="${OSPREY_EARLY_UNIT_DIR:-/etc/systemd/system}"
PREFIX=osprey-early-
LABEL=osprey.early=1
MARKER=osprey-early-warning-key
DRY=no
case "${1:-}" in --dry-run) DRY=yes ;; "") ;; *) echo "usage: cleanup.sh [--dry-run]" >&2; exit 2 ;; esac
[ "$#" -le 1 ] || { echo "usage: cleanup.sh [--dry-run]" >&2; exit 2; }
case "$ROOT" in */osprey-early) ;; *) echo "Refused: $ROOT is not an osprey-early folder." >&2; exit 2 ;; esac
[ -n "${OSPREY_EARLY_ROOT:-}" ] || [ "$(id -u)" -eq 0 ] || { echo "cleanup.sh runs as root." >&2; exit 1; }

found=0
quiet() { "$@" >/dev/null; }
gone() {  # what, then the command that removes it
  local what="$1"; shift
  found=$((found + 1))
  if [ "$DRY" = yes ]; then printf 'would remove: %s\n' "$what"; else "$@" && printf 'removed: %s\n' "$what"; fi
}

# The runner's Docker objects: name prefix and label, both (the runner starts none under the owner's ruling 1).
if command -v docker >/dev/null 2>&1; then
  while read -r id name; do
    [ -n "$id" ] && case "$name" in "$PREFIX"*) gone "container $name" quiet docker rm -f -v "$id" ;; esac
  done < <(docker ps -a --filter "label=$LABEL" --format '{{.ID}} {{.Names}}' 2>/dev/null || true)
  while read -r id name; do
    [ -n "$id" ] && case "$name" in "$PREFIX"*) gone "network $name" quiet docker network rm "$id" ;; esac
  done < <(docker network ls --filter "label=$LABEL" --format '{{.ID}} {{.Name}}' 2>/dev/null || true)
  while read -r name; do
    [ -n "$name" ] && case "$name" in "$PREFIX"*) gone "volume $name" quiet docker volume rm "$name" ;; esac
  done < <(docker volume ls --filter "label=$LABEL" --format '{{.Name}}' 2>/dev/null || true)
  while read -r id ref; do
    [ -n "$id" ] && case "$ref" in "$PREFIX"*) gone "image $ref" quiet docker rmi "$id" ;; esac
  done < <(docker images --filter "label=$LABEL" --format '{{.ID}} {{.Repository}}:{{.Tag}}' 2>/dev/null || true)
fi

if id -u "$USER_NAME" >/dev/null 2>&1; then
  uid="$(id -u "$USER_NAME")"
  if command -v loginctl >/dev/null 2>&1 && loginctl show-user "$USER_NAME" >/dev/null 2>&1; then
    gone "the runner's jobs and session ($USER_NAME's processes)" loginctl terminate-user "$USER_NAME"
    gone "linger for $USER_NAME" loginctl disable-linger "$USER_NAME"
  fi
  dropin="$DROPIN_BASE/user@$uid.service.d/osprey-early-delegate.conf"
  if [ -f "$dropin" ]; then
    gone "$dropin" sh -c 'rm -f "$1"; rmdir "$(dirname "$1")" 2>/dev/null || true; systemctl daemon-reload 2>/dev/null || true' _ "$dropin"
  fi
fi

shield_unit="$UNIT_DIR/osprey-early-shield.service"
if [ -f "$shield_unit" ]; then
  gone "the shield's unit ($shield_unit)" sh -c 'systemctl disable --now osprey-early-shield.service >/dev/null 2>&1 || true; rm -f "$1"; systemctl daemon-reload 2>/dev/null || true' _ "$shield_unit"
fi
if command -v nft >/dev/null 2>&1 && nft list table inet osprey_early >/dev/null 2>&1; then
  gone "the shield (nftables table inet osprey_early)" nft delete table inet osprey_early
fi

for unit in osprey-summary.path osprey-summary.timer osprey-summary.service; do
  if [ -f "$UNIT_DIR/$unit" ]; then
    gone "the summary's unit ($UNIT_DIR/$unit)" sh -c 'systemctl disable --now "$2" >/dev/null 2>&1 || true; rm -f "$1"; systemctl daemon-reload 2>/dev/null || true' _ "$UNIT_DIR/$unit" "$unit"
  fi
done
if command -v nft >/dev/null 2>&1 && nft list table inet osprey_summary >/dev/null 2>&1; then
  gone "the summary's shield (nftables table inet osprey_summary)" nft delete table inet osprey_summary
fi
if id -u "$SUMMARY_USER" >/dev/null 2>&1; then
  gone "the account $SUMMARY_USER" userdel "$SUMMARY_USER"
fi

keys="$ROOT/home/.ssh/authorized_keys"
if [ -f "$keys" ] && grep -q "$MARKER" "$keys"; then
  gone "the key's line in $keys (marker $MARKER)" sh -c 'grep -v "$2" "$1" > "$1.new" || true; mv "$1.new" "$1"' _ "$keys" "$MARKER"
fi

if id -u "$USER_NAME" >/dev/null 2>&1; then
  gone "the account $USER_NAME" userdel "$USER_NAME"
fi

if [ -e "$ROOT" ]; then
  gone "$ROOT (the runner's code, source copy, jobs, tools and caches)" rm -rf -- "$ROOT"
fi

[ "$found" -gt 0 ] || echo "nothing to remove"
