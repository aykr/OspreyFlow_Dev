#!/usr/bin/env bash
# The demo server's early-warning runner: installed by the owner, by hand, as root (DEMO_SERVER_EARLY_WARNING_BRIEF.md).
# ADVICE ONLY: the Mac's merge run stays the only gate to main.
#
#   sudo bash install.sh           prints what it would do, and the authorized_keys line; changes nothing
#   sudo bash install.sh --yes     does it
#
# Run it from this folder (demo_server/ of a checkout of lane/line-fixes-demo-server). It opens no port, starts no
# listener, changes no firewall, DNS or model address, touches no container, network, volume or image, and adds
# nobody to the docker group. What it creates is listed at the end, and cleanup.sh removes all of it.
set -euo pipefail

ROOT=/var/lib/osprey-early          # bin/ (root's: the runner's code), data/ (the runner's), home/ (root's: .ssh)
USER_NAME=osprey-early              # the runner's account: no password, no sudo, no docker group
UV_VERSION=0.5.14                   # the Mac's uv (uv --version, 21 November 2026); CI's setup-uv takes it from
                                    # astral-sh/uv's GitHub releases, as here
NODE_VERSION=22.23.5                # the Mac's line Node (~/.ospreyflow/slice-line/node/v22); CI's setup-node takes
                                    # Node 22 from nodejs.org's distributions, as here
DROPIN_NAME=osprey-early-delegate.conf
SHIELD_UNIT=/etc/systemd/system/osprey-early-shield.service
SUMMARY_USER=osprey-summary         # 010: the summary's account: no password, no shell, no sudo, no docker group
UNITS=/etc/systemd/system
FILES="runner.py protocol.py lists.py lists.tsv mac_only.tsv cleanup.sh shield.nft summarize.py summary.nft"
HERE="$(cd "$(dirname "$0")" && pwd)"
DO=no
[ "${1:-}" = "--yes" ] && DO=yes
[ "$#" -le 1 ] && { [ "$#" -eq 0 ] || [ "$DO" = yes ]; } || { echo "usage: install.sh [--yes]" >&2; exit 2; }

say() { printf '%s\n' "$*"; }
act() { if [ "$DO" = yes ]; then "$@"; else say "  would run: $*"; fi; }

[ "$(id -u)" -eq 0 ] || { echo "install.sh runs as root (the owner, by hand)." >&2; exit 1; }
missing=""
for cmd in git make python3 curl tar xz sha256sum systemd-run systemctl loginctl useradd runuser nft; do
  command -v "$cmd" >/dev/null 2>&1 || missing="$missing $cmd"
done
[ -z "$missing" ] || { echo "Missing on this machine:$missing. install.sh installs none of these: add them first." >&2; exit 1; }
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' || { echo "python3 is older than 3.8." >&2; exit 1; }
for f in $FILES; do
  [ -f "$HERE/$f" ] || { echo "$HERE/$f is missing: run install.sh from its own folder." >&2; exit 1; }
done
if id -u "$USER_NAME" >/dev/null 2>&1 && id -nG "$USER_NAME" | tr ' ' '\n' | grep -qx docker; then
  echo "$USER_NAME is in the docker group: the runner must reach no Docker. Remove it from the group first." >&2; exit 1
fi

say "The early-warning runner, $( [ "$DO" = yes ] && echo installing || echo 'what install.sh --yes would do' ):"

# 1. The account: a system user with no password and no docker group. Its shell is /bin/sh only because sshd runs the
#    forced command through the account's shell; the key's forced command is all it can run over SSH.
if ! id -u "$USER_NAME" >/dev/null 2>&1; then
  act useradd --system --user-group --no-create-home --home-dir "$ROOT/home" --shell /bin/sh "$USER_NAME"
fi

# 2. The folders. bin/ and home/ are root's (the runner cannot change its own code or its authorized_keys); data/ is
#    the runner's own, mode 700: its source copy, its jobs, its tools and caches. Nothing outside $ROOT.
act install -d -o root -g root -m 0755 "$ROOT" "$ROOT/bin" "$ROOT/home" "$ROOT/home/.ssh"
act install -d -o "$USER_NAME" -g "$USER_NAME" -m 0700 "$ROOT/data" "$ROOT/data/tools" "$ROOT/data/cache" "$ROOT/data/jobs"
for f in $FILES; do
  act install -o root -g root -m 0644 "$HERE/$f" "$ROOT/bin/$f"
done
act chmod 0755 "$ROOT/bin/runner.py" "$ROOT/bin/cleanup.sh"

# 3. The toolchain the checks need, into data/tools, each checked against its publisher's checksum. Python 3.12 (CI's
#    UV_PYTHON) is fetched by uv itself into data/tools/python at the first run, as uv does on CI.
fetch() {  # url, sha256 line source url, dest
  act runuser -u "$USER_NAME" -- curl -fsSL --proto '=https' -o "$3" "$1"
}
UV_TGZ="uv-x86_64-unknown-linux-gnu.tar.gz"
UV_URL="https://github.com/astral-sh/uv/releases/download/$UV_VERSION/$UV_TGZ"
NODE_TXZ="node-v$NODE_VERSION-linux-x64.tar.xz"
NODE_URL="https://nodejs.org/dist/v$NODE_VERSION"
T="$ROOT/data/cache/download"
act runuser -u "$USER_NAME" -- mkdir -p "$T" "$ROOT/data/tools/uv" "$ROOT/data/tools/node/v22"
fetch "$UV_URL" - "$T/$UV_TGZ"
fetch "$UV_URL.sha256" - "$T/$UV_TGZ.sha256"
fetch "$NODE_URL/$NODE_TXZ" - "$T/$NODE_TXZ"
fetch "$NODE_URL/SHASUMS256.txt" - "$T/SHASUMS256.txt"
if [ "$DO" = yes ]; then
  (cd "$T" && sha256sum -c "$UV_TGZ.sha256" && grep " $NODE_TXZ\$" SHASUMS256.txt | sha256sum -c -) \
    || { echo "A download does not match its published checksum: nothing installed from it." >&2; exit 1; }
else
  say "  would check: $UV_TGZ against its .sha256, $NODE_TXZ against SHASUMS256.txt (stops on any mismatch)"
fi
act runuser -u "$USER_NAME" -- tar -xzf "$T/$UV_TGZ" -C "$ROOT/data/tools/uv" --strip-components=1
act runuser -u "$USER_NAME" -- tar -xJf "$T/$NODE_TXZ" -C "$ROOT/data/tools/node/v22" --strip-components=1
act rm -rf "$T"

# 4. The caps. The job runs as a transient service of the account's own systemd manager (systemd-run --user), which
#    needs that manager running without a login (linger) and the cpu, io and memory controllers delegated to it.
#    CPUQuota, MemoryMax, RuntimeMaxSec, nice and the I/O class are set per job by runner.py (protocol.py's numbers).
UID_NUM="$(id -u "$USER_NAME" 2>/dev/null || echo '<its uid>')"
DROPIN_DIR="/etc/systemd/system/user@$UID_NUM.service.d"
if [ "$DO" = yes ]; then
  install -d -m 0755 "$DROPIN_DIR"
  printf '[Service]\nDelegate=cpu cpuset io memory pids\n' > "$DROPIN_DIR/$DROPIN_NAME"
  systemctl daemon-reload
  loginctl enable-linger "$USER_NAME"
else
  say "  would write: $DROPIN_DIR/$DROPIN_NAME ([Service] Delegate=cpu cpuset io memory pids), daemon-reload"
  say "  would run: loginctl enable-linger $USER_NAME"
fi

# 5. The shield: an outbound restriction on this account alone (shield.nft says what and why). Its rules name the
#    account, the system's ephemeral port range (where every test server of its own binds, on port 0) and the
#    resolvers in /etc/resolv.conf (DNS, for the package downloads); one oneshot unit loads them at boot.
EPHEMERAL="$(tr -s '[:space:]' '-' < /proc/sys/net/ipv4/ip_local_port_range | sed 's/-$//')"
R4="$(awk '$1 == "nameserver" && $2 ~ /^[0-9.]+$/ {print $2}' /etc/resolv.conf | paste -sd, -)"
R6="$(awk '$1 == "nameserver" && $2 ~ /:/ {print $2}' /etc/resolv.conf | paste -sd, -)"
DNS=""
[ -n "$R4" ] && DNS="ip daddr { $R4 } meta l4proto { tcp, udp } th dport 53 accept"
[ -n "$R6" ] && DNS="$DNS
		ip6 daddr { $R6 } meta l4proto { tcp, udp } th dport 53 accept"
[ -n "$DNS" ] || { echo "/etc/resolv.conf names no resolver: the shield would refuse the package downloads' DNS." >&2; exit 1; }
SHIELD_TEXT="$(USER_NAME="$USER_NAME" EPHEMERAL="$EPHEMERAL" DNS="$DNS" python3 -c '
import os, sys
t = open(sys.argv[1]).read()
for k in ("USER", "EPHEMERAL", "DNS"):
    t = t.replace("@%s@" % k, os.environ["USER_NAME" if k == "USER" else k])
sys.stdout.write(t)' "$HERE/shield.nft")"
UNIT_TEXT="[Unit]
Description=The early-warning runner's shield (outbound restriction on $USER_NAME only)
After=nftables.service
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/sbin/nft -f $ROOT/bin/shield.nft
ExecStop=/usr/sbin/nft delete table inet osprey_early
[Install]
WantedBy=multi-user.target"
if [ "$DO" = yes ]; then
  printf '%s\n' "$SHIELD_TEXT" > "$ROOT/bin/shield.nft"
  chmod 0644 "$ROOT/bin/shield.nft"
  nft -c -f "$ROOT/bin/shield.nft" || { echo "nft refuses the shield's rules: nothing loaded." >&2; exit 1; }
  printf '%s\n' "$UNIT_TEXT" > "$SHIELD_UNIT"
  systemctl daemon-reload
  systemctl enable --now osprey-early-shield.service
else
  say "  would write $ROOT/bin/shield.nft, checked with nft -c, and load it as:"
  printf '%s\n' "$SHIELD_TEXT" | sed 's/^/    /'
  say "  would write $SHIELD_UNIT and run: systemctl enable --now osprey-early-shield.service"
  printf '%s\n' "$UNIT_TEXT" | sed 's/^/    /'
fi

# 6. The summary of a red run (010), after the job and outside it: its own account, which reads only what the runner
#    hands over (handoff/, group-readable to it) and writes only its summaries (summaries/, group-readable to the
#    runner, which returns them as `summary <id>`). It reaches one address and port: 127.0.0.1:11434, the host's
#    Ollama (summary.nft, by its account; and the unit's own IPAddressAllow). It never reads data/ (mode 700, the
#    runner's) and runs nothing from a log. A path unit starts it when a run is handed over; a timer catches up.
if ! id -u "$SUMMARY_USER" >/dev/null 2>&1; then
  act useradd --system --user-group --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin "$SUMMARY_USER"
fi
act install -d -o "$USER_NAME" -g "$SUMMARY_USER" -m 2750 "$ROOT/handoff"
act install -d -o "$SUMMARY_USER" -g "$USER_NAME" -m 2750 "$ROOT/summaries"
act chmod 0755 "$ROOT/bin/summarize.py"
SUMMARY_NFT="$(sed "s/@SUMMARY_USER@/$SUMMARY_USER/g" "$HERE/summary.nft")"
SUMMARY_SERVICE="[Unit]
Description=Summaries of the early-warning runner's red runs (advice only)
[Service]
Type=oneshot
User=$SUMMARY_USER
Group=$SUMMARY_USER
ExecStartPre=+/usr/sbin/nft -f $ROOT/bin/summary.nft
ExecStart=/usr/bin/python3 -I $ROOT/bin/summarize.py
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
ReadWritePaths=$ROOT/summaries
InaccessiblePaths=$ROOT/data $ROOT/home
IPAddressDeny=any
IPAddressAllow=127.0.0.1/32
RestrictAddressFamilies=AF_INET AF_UNIX
CPUQuota=100%
MemoryMax=1G
Nice=15
IOSchedulingClass=idle
TimeoutStartSec=45min"
SUMMARY_PATH="[Unit]
Description=Start a summary when the early-warning runner hands a red run over
[Path]
PathChanged=$ROOT/handoff
Unit=osprey-summary.service
[Install]
WantedBy=multi-user.target"
SUMMARY_TIMER="[Unit]
Description=Catch up on any red run handed over while no summary ran
[Timer]
OnBootSec=5min
OnUnitInactiveSec=10min
Unit=osprey-summary.service
[Install]
WantedBy=timers.target"
if [ "$DO" = yes ]; then
  printf '%s\n' "$SUMMARY_NFT" > "$ROOT/bin/summary.nft"
  chmod 0644 "$ROOT/bin/summary.nft"
  nft -c -f "$ROOT/bin/summary.nft" || { echo "nft refuses the summary's rules: nothing loaded." >&2; exit 1; }
  printf '%s\n' "$SUMMARY_SERVICE" > "$UNITS/osprey-summary.service"
  printf '%s\n' "$SUMMARY_PATH" > "$UNITS/osprey-summary.path"
  printf '%s\n' "$SUMMARY_TIMER" > "$UNITS/osprey-summary.timer"
  systemctl daemon-reload
  systemctl enable --now osprey-summary.path osprey-summary.timer
else
  say "  would write $ROOT/bin/summary.nft, checked with nft -c, loaded before each summary:"
  printf '%s\n' "$SUMMARY_NFT" | sed 's/^/    /'
  say "  would write $UNITS/osprey-summary.service, .path and .timer, and run: systemctl enable --now osprey-summary.path osprey-summary.timer"
  printf '%s\n' "$SUMMARY_SERVICE" | sed 's/^/    /'
fi

say ""
say "The one line to add, by hand, to $ROOT/home/.ssh/authorized_keys (owned by root, mode 644), with the public key"
say "in place of the placeholder. restrict turns off the pty and port, agent and X11 forwarding; with the forced"
say "command, scp and sftp have nothing to run (an sftp or scp request reaches runner.py, which refuses it):"
say ""
say "command=\"/usr/bin/python3 -I $ROOT/bin/runner.py\",restrict <PUBLIC KEY: ssh-ed25519 ...> osprey-early-warning-key"
say ""
say "Opened: nothing. No port, no listener, no inbound rule, no DNS change, no model address changed. The one rule"
say "  added is outbound, for $USER_NAME alone (table inet osprey_early): it refuses that account's connections to"
say "  this machine's listeners and to every private network, Docker's among them."
say "Containers, networks, volumes, images: none started, none changed. $USER_NAME is in no docker group."
say "Created: the account $USER_NAME; $ROOT (bin/, data/, home/.ssh/); $DROPIN_DIR/$DROPIN_NAME;"
say "  $SHIELD_UNIT and the nftables table inet osprey_early it loads;"
say "  the account $SUMMARY_USER, $ROOT/handoff and $ROOT/summaries, osprey-summary.service, .path and .timer, and the"
say "  nftables table inet osprey_summary (its one allowed connection: 127.0.0.1 port 11434);"
say "  linger for $USER_NAME. Removed by: sudo bash $ROOT/bin/cleanup.sh (try --dry-run first)."
