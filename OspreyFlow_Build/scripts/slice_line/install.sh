#!/usr/bin/env bash
# Install the slice line's hooks in the fixed place outside every worktree (process/lanes/v062/slice-line/README.md,
# "Where the guard runs from"). Run by the owner (the guard refuses it from any agent):
#
#   OspreyFlow_Build/scripts/slice_line/install.sh
#
# Copies guard.py, stop_check.py, usage_hook.py and the Stop hook's scan map (scan_select.py, scan_map.tsv) from this checkout to ~/.ospreyflow/slice-line/bin, read-only,
# with their SHA-256 in manifest.json; writes the fixed settings every seat is started with (--settings); records
# origin's URL for push_main.sh; and records the owner's email addresses as SHA-256 hashes only (from git's
# user.email and each signed-in account), so the guard can refuse them without the address ever being written.
#
#   OspreyFlow_Build/scripts/slice_line/install.sh --register-everywhere
#
# also registers the guard (PreToolUse, every tool; Stop) in every account's own settings on this Mac (~/.claude and
# each ~/.claude-<account>), so a session started outside the checkout loads it too (F1). That binds the owner's own
# sessions in every repository: COMMANDS.md of the line fixes says which rules then hold for them. Never without the
# flag (the owner's word, 18 November 2026). Each settings file is copied aside first; the owner's own keys are kept.
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
BIN="$HOME/.ospreyflow/slice-line"
REPO="$(dirname "$(git -C "$SRC" rev-parse --path-format=absolute --git-common-dir)")"
mkdir -p "$BIN/bin" "$BIN/records" "$BIN/sessions" "$BIN/accounts"
chmod u+w "$BIN/bin" "$BIN/bin/"* 2>/dev/null || true
for f in guard.py stop_check.py usage_hook.py scan_select.py scan_map.tsv; do
  cp "$SRC/$f" "$BIN/bin/$f"
  chmod 0555 "$BIN/bin/$f"
done
# The seat shim (F1): every seat's `claude`, `claude-sol` and `claude-ayan`, first on its PATH (run_seat.py).
mkdir -p "$BIN/bin/shim"
chmod u+w "$BIN/bin/shim" "$BIN/bin/shim/"* 2>/dev/null || true
for n in claude claude-sol claude-ayan; do
  cp "$SRC/seat_shim.sh" "$BIN/bin/shim/$n"
  chmod 0555 "$BIN/bin/shim/$n"
done
chmod 0555 "$BIN/bin/shim"
mkdir -p "$BIN/launch"
/usr/bin/python3 - "$BIN" <<'PY'
import hashlib, json, sys
from pathlib import Path
b = Path(sys.argv[1])
m = {f: hashlib.sha256((b / "bin" / f).read_bytes()).hexdigest()
     for f in ("guard.py", "stop_check.py", "usage_hook.py", "scan_select.py", "scan_map.tsv", "shim/claude")}
(b / "manifest.json").write_text(json.dumps(m, indent=1))
py = "/usr/bin/python3 $HOME/.ospreyflow/slice-line/bin/"
hook = lambda cmd, **kw: {"hooks": [{"type": "command", "command": py + cmd, **kw}]}
settings = {"hooks": {
    "SessionStart": [hook("guard.py session-start")],
    "PreToolUse": [{"matcher": "*", **hook("guard.py pre")}],
    "Stop": [{"hooks": [{"type": "command", "command": py + "stop_check.py", "timeout": 1800},
                        {"type": "command", "command": py + "guard.py stop"}]}],
    "SubagentStop": [hook("guard.py stop")],
    "StopFailure": [hook("usage_hook.py stop-failure")],
    "SessionEnd": [hook("usage_hook.py session-end")],
}}
(b / "settings.json").write_text(json.dumps(settings, indent=1))
PY
chmod 0555 "$BIN/bin"
git -C "$REPO" remote get-url --push origin > "$BIN/origin.url"

# The owner's addresses, hashed: never printed, never written in the clear.
{
  git -C "$REPO" config user.email 2>/dev/null || true
  "$HOME/.local/bin/claude" auth status 2>/dev/null | /usr/bin/python3 -c 'import json,sys; print(json.load(sys.stdin).get("email",""))' || true
  for d in "$HOME"/.claude-*; do
    [ -d "$d" ] || continue
    CLAUDE_CONFIG_DIR="$d" "$HOME/.local/bin/claude" auth status 2>/dev/null | /usr/bin/python3 -c 'import json,sys; print(json.load(sys.stdin).get("email",""))' 2>/dev/null || true
  done
} | /usr/bin/python3 -c '
import hashlib, sys
seen = sorted({l.strip().lower() for l in sys.stdin if "@" in l})
print("\n".join(hashlib.sha256(e.encode()).hexdigest() for e in seen))' > "$BIN/emails.sha256"

echo "Installed in $BIN: $(wc -l < "$BIN/emails.sha256" | tr -d ' ') address hash(es); origin recorded; hooks:"
cat "$BIN/manifest.json"

if [ "${1:-}" = "--register-everywhere" ]; then
  for d in "$HOME/.claude" "$HOME"/.claude-*; do
    [ -d "$d" ] || continue
    /usr/bin/python3 - "$d/settings.json" <<'PY'
import json, shutil, sys, time
from pathlib import Path
f = Path(sys.argv[1])
s = json.loads(f.read_text()) if f.exists() and f.read_text().strip() else {}
if f.exists():
    shutil.copyfile(f, f.with_name(f"settings.json.before-slice-line-{time.strftime('%Y%m%dT%H%M%S')}"))
py = "/usr/bin/python3 $HOME/.ospreyflow/slice-line/bin/"
hooks = s.setdefault("hooks", {})
for event, cmd, extra in (("PreToolUse", py + "guard.py pre", {"matcher": "*"}), ("Stop", py + "guard.py stop", {})):
    have = [h.get("command") for e in hooks.get(event, []) for h in e.get("hooks", [])]
    if cmd not in have:
        hooks.setdefault(event, []).append({**extra, "hooks": [{"type": "command", "command": cmd}]})
tmp = f.with_name(f.name + ".tmp")
tmp.write_text(json.dumps(s, indent=2) + "\n")
tmp.replace(f)
print(f"The guard is registered in {f}.")
PY
  done
fi
