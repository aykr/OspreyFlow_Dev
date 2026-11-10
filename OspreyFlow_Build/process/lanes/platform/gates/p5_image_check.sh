#!/bin/sh
# P5 (ADR-147 Amendment 2): the Conduit's image with its jlinked Java, built on the owner's test
# server (amd64) under the platform lane's lease, run as
#   stack_lease.sh remote platform -- sh process/lanes/platform/gates/p5_image_check.sh
# from OspreyFlow_Build. Images are tagged osprey-p5-* and removed at the end; no other container is touched.
# 1. Build the image as CI's `trivy-image-api` job and Core's `make trivy-image-api` do; its size; the
#    runtime's version (/opt/java/release, java -version); its java.desktop notices.
# 1b. CI's own step over it (`P5_ci.diff`): java_runtime_check --image, through `uv run` as CI runs it
#    (this machine's venv when uv is absent, said so), and --current: the pin against its tag now.
# 2. planetiler's own --help run by the image's java (brief item 1's purpose), from a release jar.
# 3. trivy over it, as both run it, and listing what it sees of the Java runtime.
# 4. The same image from an old Temurin 21 (21.0.1, October 2023, with known CVEs), scanned the same
#    way (whether trivy sees a jlinked runtime at all), then CI's step over it (red), and --current
#    over the Dockerfile pinned at 21-jdk's digest before 21.0.13+9 (red).
set -u
cd ../OspreyFlow_Core || exit 2
TRIVY=aquasec/trivy:0.76.1
OLD=eclipse-temurin:21.0.1_12-jdk
JAR_URL=https://github.com/onthegomap/planetiler/releases/download/v0.10.2/planetiler.jar
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"; docker image rm -f osprey-p5-api:current osprey-p5-api:old-temurin >/dev/null 2>&1' EXIT

say() { printf '\n===== %s\n' "$*"; }
check() {  # CI's step: `PYTHONPATH=../OspreyFlow_Build uv run python -m tools.java_runtime_check …`
  if command -v uv >/dev/null 2>&1; then PYTHONPATH=../OspreyFlow_Build uv run python -m tools.java_runtime_check "$@"
  else echo "(uv absent here: the same command through .venv/bin/python)"; PYTHONPATH=../OspreyFlow_Build .venv/bin/python -m tools.java_runtime_check "$@"; fi
}
BEFORE=sha256:f9bf7e9fe2f9bc4657537c1a7e20c768f0c3bafca41598263be4714783dd62eb
trivy() { docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v "$WORK/trivy-cache:/root/.cache" "$TRIVY" "$@"; }

# Built as CI's job builds it, without --pull: Docker Hub's pull limit refused --pull's manifest
# request on the test server (429), and the base images are already there from this evening's builds.
say "1. build (amd64), as CI's trivy-image-api job: docker build -f services/api/Dockerfile"
docker build -q -f services/api/Dockerfile -t osprey-p5-api:current . || exit 1
docker image inspect osprey-p5-api:current --format 'image size: {{.Size}} bytes ({{.Architecture}})'
docker run --rm --entrypoint sh osprey-p5-api:current -c 'du -sh /opt/java; cat /opt/java/release; java -version 2>&1; echo "legal/java.desktop:"; ls /opt/java/legal/java.desktop; for f in /opt/java/legal/java.desktop/*.md; do echo "----- $f"; cat "$f"; done'
grep -n '^FROM eclipse-temurin' services/api/Dockerfile

say "1b. CI's step over it (P5_ci.diff), then the pin against its tag now (--current)"
check --image osprey-p5-api:current
echo "CI step (current image) exit: $?"
check --current
echo "java-runtime-check --current (the committed pin) exit: $?"

say "2. planetiler --help, run by the image's java"
curl -fsSL -o "$WORK/planetiler.jar" "$JAR_URL" || echo "planetiler jar download failed"
sha256sum "$WORK/planetiler.jar"
# The image runs as uid 10001, and mktemp -d makes its directory 0700 (round 3's first run: "Unable
# to access jarfile"), so the jar is opened to it read-only.
chmod 755 "$WORK"; chmod 644 "$WORK/planetiler.jar"
docker run --rm -v "$WORK:/j:ro" --entrypoint java osprey-p5-api:current -jar /j/planetiler.jar --help > "$WORK/p.out" 2>&1
echo "planetiler --help exit: $?"; head -60 "$WORK/p.out"

say "3. trivy over the image, as CI and make trivy-image-api (HIGH,CRITICAL, --ignore-unfixed)"
trivy image --exit-code 1 --severity HIGH,CRITICAL --ignore-unfixed osprey-p5-api:current > "$WORK/t.out" 2>&1
echo "trivy (current) exit: $?"; grep -v "^20..-..-..T" "$WORK/t.out" | tail -40
say "3b. what trivy sees of the Java runtime (every package, any severity)"
trivy image --list-all-pkgs --format json osprey-p5-api:current 2>/dev/null \
  | python3 -c 'import json,sys; r=json.load(sys.stdin).get("Results",[])
for t in r: print(t.get("Type"), t.get("Target"), len(t.get("Packages") or []))
java=[p for t in r for p in (t.get("Packages") or []) if "java" in (p.get("Name","")+p.get("ID","")).lower() or "jdk" in (p.get("Name","")).lower() or "openjdk" in (p.get("Name","")).lower()]
print("packages naming java/jdk:", [(p.get("Name"), p.get("Version")) for p in java])'

say "4. the same image from an old Temurin ($OLD), scanned the same way"
sed "s#^FROM eclipse-temurin:21-jdk@sha256:[0-9a-f]* AS java#FROM $OLD AS java#" services/api/Dockerfile > "$WORK/Dockerfile.old"
grep -n '^FROM eclipse-temurin' "$WORK/Dockerfile.old"
docker build -q -f "$WORK/Dockerfile.old" -t osprey-p5-api:old-temurin . || exit 1
docker run --rm --entrypoint sh osprey-p5-api:old-temurin -c 'cat /opt/java/release | head -3'
trivy image --exit-code 1 --severity HIGH,CRITICAL --ignore-unfixed osprey-p5-api:old-temurin > "$WORK/o.out" 2>&1
echo "trivy (old Temurin) exit: $?"; grep -v "^20..-..-..T" "$WORK/o.out" | tail -25
say "4b. CI's step over the old Temurin (its label as committed): red; then --current at 21-jdk's digest before 21.0.13+9: red"
check --image osprey-p5-api:old-temurin
echo "CI step (old Temurin image) exit: $?"
sed "s#^FROM eclipse-temurin:21-jdk@sha256:[0-9a-f]* AS java#FROM eclipse-temurin:21-jdk@$BEFORE AS java#" services/api/Dockerfile > "$WORK/Dockerfile.before"
grep -n '^FROM eclipse-temurin' "$WORK/Dockerfile.before"
check --current --dockerfile "$WORK/Dockerfile.before"
echo "java-runtime-check --current (the pin before) exit: $?"
trivy image --severity HIGH,CRITICAL --format json osprey-p5-api:old-temurin 2>/dev/null \
  | python3 -c 'import json,sys; r=json.load(sys.stdin).get("Results",[])
v=[(x.get("PkgName"),x.get("VulnerabilityID")) for t in r for x in (t.get("Vulnerabilities") or [])]
print("vulnerabilities in a Java package:", [i for i in v if "java" in (i[0] or "").lower() or "jdk" in (i[0] or "").lower()])'
say "done"
