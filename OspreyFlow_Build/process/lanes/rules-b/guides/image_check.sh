#!/usr/bin/env bash
# The guides step's image check (ADR-145 Amendment 10, the orchestrator's review item 2): the Conduit's
# image, built from this checkout, carries each guide's PDF byte for byte as `docs/pdf/manifest.json`
# records it, readable by anyone (0444), and not the architecture guide. Run on the test server under the
# rules-b lease (`stack_lease.sh remote rules-b -- bash OspreyFlow_Build/process/lanes/rules-b/guides/image_check.sh`).
#
#   image_check.sh           build, read /app/docs/pdf inside the image, compare: exit 0 when all match
#   image_check.sh --plant   the same, after a stale user guide (one byte appended) is put in the build
#                            context; the comparison must fail (exit 1). The file is restored on exit.
#
# The image is tagged for this run only and removed afterwards, pass or fail. It touches no stack.
set -euo pipefail
cd "$(dirname "$0")/../../../../../OspreyFlow_Core"
TAG="osprey-rules-b-guides-check:$$"
PDF=docs/pdf/user-guide.pdf
cleanup() {
  [ -f "$PDF.unplanted" ] && mv -f "$PDF.unplanted" "$PDF"
  docker rmi -f "$TAG" >/dev/null 2>&1 || true
}
trap cleanup EXIT
if [ "${1:-}" = "--plant" ]; then
  cp -p "$PDF" "$PDF.unplanted"
  printf 'x' >> "$PDF"
  echo "PLANT: one byte appended to $PDF in the build context"
fi
echo "building $TAG from $(pwd) (services/api/Dockerfile)"
DOCKER_BUILDKIT=1 docker build -q -f services/api/Dockerfile -t "$TAG" . >/dev/null
echo "inside the image, /app/docs/pdf:"
echo "the folders, as root, and what the Conduit's own user (the image's USER) can list:"
docker run --rm --user 0 --entrypoint stat "$TAG" -c "%a %U %n" /app/docs /app/docs/pdf
docker run --rm --entrypoint ls "$TAG" /app/docs/pdf
inside=$(docker run --rm --entrypoint sh "$TAG" -c 'cd /app/docs/pdf && for f in *; do printf "%s %s %s\n" "$(sha256sum "$f" | cut -d" " -f1)" "$(stat -c %a "$f")" "$f"; done')
echo "$inside"
[ -f "$PDF.unplanted" ] && mv -f "$PDF.unplanted" "$PDF"
python3 - "$inside" <<'EOF'
import json, sys
inside = {name: (sha, mode) for sha, mode, name in (l.split() for l in sys.argv[1].splitlines())}
manifest = json.load(open("docs/pdf/manifest.json"))
wanted = {"user-guide.pdf", "developer-guide.pdf", "administration-guide.pdf", "manifest.json"}
bad = []
if set(inside) != wanted:
    bad.append(f"carried {sorted(inside)}, wanted {sorted(wanted)}")
for name in sorted(wanted - {"manifest.json"}):
    sha = inside.get(name, ("missing", ""))[0]
    if sha != manifest[name.replace(".pdf", ".md")]["pdf"]:
        bad.append(f"{name}: {sha} in the image, {manifest[name.replace('.pdf', '.md')]['pdf']} in manifest.json")
for name, (_, mode) in inside.items():
    if mode != "444":
        bad.append(f"{name}: mode {mode}, not 444")
print("RESULT:", "every guide carried byte for byte as manifest.json records it, 0444" if not bad else "MISMATCH")
for line in bad:
    print("  " + line)
sys.exit(1 if bad else 0)
EOF
