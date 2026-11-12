#!/usr/bin/env bash
# P12 part 2, round 2, item 2: Laurium's image built, scanned and started once, on the test server, offline (no stack).
# Run from OspreyFlow_Build under `scripts/stack_lease.sh offline case-b -- bash process/lanes/case-b/p12p2_image.sh`.
# The scan is P12p2_CI.diff's trivy-image-laurium job's: trivy v0.76.1's vuln scanner, HIGH and CRITICAL, unfixed
# ignored, OspreyFlow_Core/.trivyignore. The start: no network at all (`--network none`), its one setting, and its own
# /healthz asked from inside the container, as its compose healthcheck asks it; the container removed after.
set -u
cd ../OspreyFlow_Core || exit 1
IMAGE=case-b-laurium:p12p2
NAME=case-b-laurium-p12p2
step() { echo; echo "=== $* ($(date -u +%H:%M:%SZ))"; }
trap 'docker rm -f "$NAME" >/dev/null 2>&1 || true' EXIT

step "build, from its own folder alone"
docker build --pull -f services/laurium/Dockerfile -t "$IMAGE" services/laurium
echo "build: exit $?"

step "trivy, as P12p2_CI.diff's job"
trivy --version | head -1
trivy image --scanners vuln --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 \
  --ignorefile .trivyignore "$IMAGE"
echo "trivy: exit $?"

step "start once: no network, its gateway's address alone"
docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --name "$NAME" --network none \
  -e OSPREY_LAURIUM_GATEWAY_URL=http://litellm:4000/v1 "$IMAGE"
ready=no
for i in $(seq 1 60); do
  if docker exec "$NAME" python -c \
    "import urllib.request as u; print(u.urlopen('http://127.0.0.1:8000/healthz', timeout=5).read().decode())" 2>/dev/null; then
    ready=yes; echo "healthz answered after about $((i * 2)) s"; break
  fi
  sleep 2
done
echo "healthz: $ready"
docker inspect -f 'configured user={{.Config.User}} state={{.State.Status}}' "$NAME"
echo "measured: uid=$(docker exec "$NAME" id -u) gid=$(docker exec "$NAME" id -g)"
docker logs "$NAME" 2>&1 | tail -15
echo "start: $ready"
