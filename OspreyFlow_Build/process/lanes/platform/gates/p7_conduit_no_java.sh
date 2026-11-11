#!/usr/bin/env bash
# ADR-148 decision 12 (the independent review of P7, item 9): the Conduit built once with
# `--build-arg CONDUIT_JAVA=omitted`, as `ospreyflow images push` builds it for the cloud-platform profile,
# and shown to carry no Java (no `java` on its path, no JAVA_HOME, an empty-or-absent /opt/java, no Java
# licence or version label) and to start: its application imports, and its own entrypoint runs uvicorn up to
# the application's start-up. On the test server, from OspreyFlow_Core:
#   bash ../OspreyFlow_Build/process/lanes/platform/gates/p7_conduit_no_java.sh run
# The image is tagged osprey-p7-api-nojava:check and its containers are named osprey-p7-nojava-*, removed at
# the end, pass or fail; the image is kept for the record (`docker image rm osprey-p7-api-nojava:check`).
set -uo pipefail
IMAGE=osprey-p7-api-nojava:check
P=osprey-p7-nojava
fails=0
say() { printf '\n== %s\n' "$*"; }
ok() { printf 'PASS  %s\n' "$*"; }
bad() { printf 'FAIL  %s\n' "$*"; fails=$((fails + 1)); }
cleanup() { docker rm -f "$P-start" >/dev/null 2>&1; }
trap cleanup EXIT
cd "$(git rev-parse --show-toplevel)/OspreyFlow_Core" || exit 2

say "build: services/api/Dockerfile, --build-arg CONDUIT_JAVA=omitted, at $(git rev-parse --short HEAD)"
if docker build -q -f services/api/Dockerfile --build-arg CONDUIT_JAVA=omitted -t "$IMAGE" . ; then
  ok "built $IMAGE ($(docker image inspect --format '{{.Id}}' "$IMAGE"))"
else
  bad "the build"; exit 1
fi

say "no Java in it"
labels=$(docker image inspect --format '{{json .Config.Labels}}' "$IMAGE")
echo "labels: $labels"
case "$labels" in
  *'"org.ospreyflow.runtime.java.included":"omitted"'*) ok "labelled included=omitted" ;;
  *) bad "no included=omitted label" ;;
esac
case "$labels" in
  *runtime.java.licence*|*runtime.java.version*) bad "labelled with Java's licence or version" ;;
  *) ok "no Java licence or version label" ;;
esac
env_list=$(docker image inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$IMAGE")
echo "$env_list" | sed 's/^/env: /'
if echo "$env_list" | grep -q '^JAVA_HOME='; then bad "JAVA_HOME is set"; else ok "no JAVA_HOME"; fi
if echo "$env_list" | grep '^PATH=' | grep -q '/opt/java'; then bad "/opt/java on PATH"; else ok "/opt/java not on PATH"; fi
found=$(docker run --rm --entrypoint sh "$IMAGE" -c 'id; command -v java || echo "java: not found"; ls -A /opt/java 2>&1 || true; find / -xdev -name java -type f 2>/dev/null | head -5')
echo "$found" | sed 's/^/in the image: /'
if echo "$found" | grep -q '^java: not found$' && ! echo "$found" | grep -q '/bin/java$'; then
  ok "no java executable anywhere in the image"
else bad "a java executable is in the image"; fi

say "it starts"
if docker run --rm --entrypoint python "$IMAGE" -c \
    'import shutil, services.api.app; print("imported services.api.app; shutil.which(java) =", shutil.which("java"))'; then
  ok "the application imports without Java"
else bad "the application does not import"; fi
# Its own entrypoint (uvicorn), with no stores and no IdP: it must get past the image (Python, the app's
# imports) to the application's own start-up, which then stops on the deployment's missing settings.
docker run -d --name "$P-start" "$IMAGE" >/dev/null
for _ in $(seq 1 30); do
  docker logs "$P-start" 2>&1 | grep -q 'Waiting for application startup\|Application startup' && break; sleep 2
done
docker logs "$P-start" 2>&1 | tail -8 | sed 's/^/log: /'
if docker logs "$P-start" 2>&1 | grep -q 'Waiting for application startup'; then
  ok "uvicorn started the application (its start-up then needs a deployment's settings, not Java)"
else bad "uvicorn never reached the application's start-up"; fi
if docker logs "$P-start" 2>&1 | grep -qi 'java'; then bad "the log names Java"; else ok "the log names no Java"; fi

say "result: $fails failure(s)"
exit $((fails > 0))
