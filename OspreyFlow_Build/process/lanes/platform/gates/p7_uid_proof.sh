#!/usr/bin/env bash
# The shared commit's proofs (spec/06_DECISIONS.md ADR-148 decision 3: every image of ours runs as
# USER 10001:10001), run on the test server through
#   OspreyFlow_Build/scripts/stack_lease.sh offline platform -- env P7_COMMIT=<sha> bash ../OspreyFlow_Build/process/lanes/platform/gates/p7_uid_proof.sh
# from OspreyFlow_Core. Everything it makes is named osprey-p7-uid-* and removed at the end, pass or fail.
#
# 1. Our images: each built image's user is 10001:10001, and the image before the change (this
#    Dockerfile with exactly the shared commit's change reverted, so nothing else differs) had which.
#    Superset's base's own ids read, its leftovers checked by them, its re-owning step shown red with
#    its chown removed, and it started to healthy; the harness's docker group measured with the user
#    by name and by number; the workspace started.
# 2. An installed deployment's named volumes: written by the old image, then written and read by the
#    new one (osprey-data, map-settings and model-settings by the Conduit; osprey-staging by ingest).
# ONLY=superset: Superset's proofs alone.
# (ArcadeDB, ClickHouse and Keeper as 10001 are P7's exit, not this commit's: `p7_stores_uid_proof.sh`.)
set -uo pipefail
cd "$(dirname "$0")/../../../../../OspreyFlow_Core" || exit 2
P=osprey-p7-uid
SUPERSET_BASE=apache/superset@sha256:16b50bbef6648912a79e3293d418fefa743ce555d36c5af6b85d859119ed7f88
fails=0
say() { printf '\n== %s\n' "$*"; }
ok() { printf 'PASS  %s\n' "$*"; }
bad() { printf 'FAIL  %s\n' "$*"; fails=$((fails + 1)); }
tmp="$(mktemp -d)"
cleanup() {
  docker rm -f $(docker ps -aq --filter "name=^$P") >/dev/null 2>&1
  docker volume rm $(docker volume ls -q --filter "name=^$P") >/dev/null 2>&1
  docker network rm "$P-net" >/dev/null 2>&1
  docker rmi -f $(docker images --format '{{.Repository}}:{{.Tag}}' | grep "^$P/") >/dev/null 2>&1
  rm -f "$tmp"/*; rmdir "$tmp"
}
trap cleanup EXIT
echo "commit: ${P7_COMMIT:-not given} (the copy's own: $(git -C .. log -1 --format=%h 2>/dev/null))"
grep -n '^USER\|^RUN old_uid' deploy/superset/Dockerfile harness/Dockerfile apps/workspace/Dockerfile

# The old Dockerfile: the shared commit's change reverted, line for line.
old_of() {
  case "$1" in
    apps/workspace/Dockerfile)
      sed -e 's#chown -R 10001:10001 /var/run/nginx.pid#chown -R nginx:nginx /var/run/nginx.pid#' \
          -e 's#^USER 10001:10001$#USER nginx#' "$1" ;;
    deploy/superset/Dockerfile)
      sed -e '/^RUN old_uid="$(id -u superset)"/,/-gid "$old_gid" -print -quit)"$/d' \
          -e 's#^USER 10001:10001$#USER superset#' "$1" ;;
    harness/Dockerfile)  # the docker group the shared commit drops, back
      sed -e 's#^USER 10001:10001$#RUN groupadd docker \&\& usermod -aG docker osprey\nUSER osprey#' "$1" ;;
    services/ner/Dockerfile) sed 's#^USER 10001:10001$#USER ner#' "$1" ;;
    *) sed 's#^USER 10001:10001$#USER osprey#' "$1" ;;
  esac
}
build() {  # build <dockerfile> <context> <tag-name>
  old_of "$1" > "$tmp/$3.old.Dockerfile"
  docker build -q -f "$1" -t "$P/$3:new" "$2" >/dev/null || { bad "$3: the new image did not build"; return 1; }
  docker build -q -f "$tmp/$3.old.Dockerfile" -t "$P/$3:old" "$2" >/dev/null || { bad "$3: the old image did not build"; return 1; }
}
ident() { docker run --rm --entrypoint id "$1" 2>&1 | tr -d '\r'; }

say "1. our images' users, before and after"
specs=("services/api/Dockerfile . api" "services/ingest/Dockerfile . ingest"
       "services/worker/Dockerfile . worker" "services/report_sync/Dockerfile . report-sync"
       "services/ner/Dockerfile . ner" "harness/Dockerfile . harness"
       "apps/workspace/Dockerfile . workspace" "deploy/superset/Dockerfile deploy/superset superset")
[ "${ONLY:-}" = superset ] && specs=("deploy/superset/Dockerfile deploy/superset superset")
for spec in "${specs[@]}"; do
  set -- $spec
  build "$1" "$2" "$3" || continue
  o="$(ident "$P/$3:old")"; n="$(ident "$P/$3:new")"
  echo "$3 old: $o"; echo "$3 new: $n"
  # The workspace's nginx image has no name for 10001 (`uid=10001 gid=10001`); nginx needs none.
  case "$n" in "uid=10001("*" gid=10001("*|"uid=10001 gid=10001"*) ok "$3 runs as 10001:10001" ;; *) bad "$3 new: $n" ;; esac
done

say "1a. Superset: its base's own ids, what is left of them, its home, its step red, its start"
echo "superset base: $(docker run --rm --entrypoint id "$SUPERSET_BASE")"
base_uid="$(docker run --rm --entrypoint id "$SUPERSET_BASE" -u)"; base_gid="$(docker run --rm --entrypoint id "$SUPERSET_BASE" -g)"
docker run --rm --entrypoint sh "$P/superset:new" -c "find / -xdev \( -uid $base_uid -o -gid $base_gid \) 2>/dev/null | head -5" > "$tmp/left"
if [ -s "$tmp/left" ]; then bad "superset: files keep the base's $base_uid/$base_gid: $(tr '\n' ' ' < "$tmp/left")"
else ok "superset: nothing keeps the base's uid $base_uid or gid $base_gid"; fi
docker run --rm --entrypoint sh "$P/superset:new" -c 'id; echo "SUPERSET_HOME=$SUPERSET_HOME"; touch "$SUPERSET_HOME/.p7" && ls -ln "$SUPERSET_HOME/.p7"' \
  && ok "superset: writes into \$SUPERSET_HOME as its running user" || bad "superset: \$SUPERSET_HOME not writable"
# Red: the step with its chown removed leaves files with the old uid, which its own check refuses.
sed '/-exec chown -h 10001 {} +/d' deploy/superset/Dockerfile > "$tmp/superset.red.Dockerfile"
echo "chown lines left in the planted Dockerfile: $(grep -c 'exec chown' "$tmp/superset.red.Dockerfile")"
if docker build -q -f "$tmp/superset.red.Dockerfile" -t "$P/superset:red" deploy/superset > "$tmp/red.log" 2>&1; then
  bad "superset: the step passed with its chown removed"
else ok "superset: the step refuses itself with its chown removed ($(grep -m1 -o 'exit code: [0-9]*' "$tmp/red.log"))"; fi
# Superset started to healthy, beside a throwaway Postgres and Valkey, as the render starts it.
docker network create "$P-net" >/dev/null
docker run -d --name "$P-valkey" --network "$P-net" --network-alias valkey valkey/valkey:8.0 >/dev/null
docker run -d --name "$P-pg" --network "$P-net" -e POSTGRES_USER=osprey -e POSTGRES_PASSWORD=throwaway-p7 \
  -e POSTGRES_DB=ospreyflow postgres:16.4 >/dev/null
for i in $(seq 1 60); do docker exec "$P-pg" pg_isready -U osprey >/dev/null 2>&1 && break; sleep 1; done
sleep 2
docker exec "$P-pg" psql -U osprey -d ospreyflow -c "CREATE ROLE osprey_reports_reader LOGIN PASSWORD 'throwaway-p7'" >/dev/null
docker run -d --name "$P-superset" --network "$P-net" -e POSTGRES_HOST="$P-pg" -e POSTGRES_USER=osprey \
  -e POSTGRES_PASSWORD=throwaway-p7 -e POSTGRES_DB=ospreyflow -e REPORT_MART_READER_PASSWORD=throwaway-p7 \
  -e SUPERSET_SECRET_KEY=throwaway-p7-throwaway-p7-throwaway -e SUPERSET_OIDC_CLIENT_SECRET=throwaway \
  -e SUPERSET_GUEST_TOKEN_SECRET=throwaway-p7-guest -e SUPERSET_EMBEDDER_PASSWORD=throwaway-p7 \
  -e OSPREY_IDENTITY_ORIGIN=https://id.p7.invalid -e OSPREY_DASHBOARDS_ORIGIN=https://bi.p7.invalid \
  -e OSPREY_GLASS_ORIGIN=https://p7.invalid "$P/superset:new" >/dev/null
up=0
for i in $(seq 1 120); do
  docker exec "$P-superset" python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8088/health', timeout=5)" >/dev/null 2>&1 && { up=1; break; }
  sleep 3
done
if [ "$up" = 1 ]; then ok "superset: started and answers /health as $(docker exec "$P-superset" id)"
else bad "superset did not start"; docker logs "$P-superset" 2>&1 | tail -20; fi

if [ -z "${ONLY:-}" ]; then
  say "1b. the harness's docker group, and the workspace"
  echo "harness by name, the group line kept (the old image): $(ident "$P/harness:old")"
  # The claim measured as stated: the same group line, the user given by number.
  sed 's#^USER 10001:10001$#RUN groupadd docker \&\& usermod -aG docker osprey\nUSER 10001:10001#' harness/Dockerfile > "$tmp/harness.group.Dockerfile"
  docker build -q -f "$tmp/harness.group.Dockerfile" -t "$P/harness:group-by-number" . >/dev/null
  g="$(ident "$P/harness:group-by-number")"; echo "harness by number, the group line kept: $g"
  case "$(ident "$P/harness:old")" in *"(docker)"*) ok "harness: by name, the docker group is there" ;; *) bad "harness: the old image had no docker group either" ;; esac
  case "$g" in *"(docker)"*) bad "harness: a numeric user kept the docker group: $g" ;; *) ok "harness: a user given by number takes no group from /etc/group" ;; esac
  case "$(ident "$P/harness:new")" in *"(docker)"*) bad "harness: a docker group is still baked in" ;; *) ok "harness: none baked in" ;; esac
  sock_gid="$(stat -c %g /var/run/docker.sock)"
  if docker run --rm --group-add "$sock_gid" -v /var/run/docker.sock:/var/run/docker.sock --entrypoint docker \
       "$P/harness:new" version --format 'the daemon answers: {{.Server.Version}}'; then
    ok "harness: as 10001 with --group-add $sock_gid it reaches the docker socket"
  else bad "harness: --group-add did not reach the socket"; fi
  docker run -d --name "$P-workspace" "$P/workspace:new" >/dev/null
  for i in $(seq 1 30); do docker exec "$P-workspace" wget -q -O /dev/null http://127.0.0.1:8080/ 2>/dev/null && break; sleep 1; done
  docker exec "$P-workspace" wget -q -O /dev/null http://127.0.0.1:8080/ && ok "workspace: nginx serves on 8080 as 10001" \
    || { bad "workspace: nginx did not serve"; docker logs "$P-workspace" 2>&1 | tail -5; }

  say "2. an installed deployment's named volumes, written by the old image, then by the new"
  for pair in "api /var/lib/osprey/data osprey-data" "api /run/osprey/map-settings map-settings" \
              "api /run/osprey/model-settings model-settings" "ingest /var/lib/osprey/staging osprey-staging"; do
    set -- $pair
    v="$P-$3"; docker volume create "$v" >/dev/null
    if ! docker run --rm --entrypoint sh -v "$v:$2" "$P/$1:old" -c "echo old > $2/written-by-old && mkdir -p $2/sub && echo x > $2/sub/f"; then
      # Not this change's: a folder the image does not make is the volume's root's (root) for both.
      if docker run --rm --entrypoint sh -v "$v:$2" "$P/$1:new" -c "touch $2/p7" 2>/dev/null; then
        bad "$3: the old $1 image could not write a fresh volume and the new one can: a change"
      else ok "$3: unchanged: neither the old nor the new $1 image writes a fresh volume there (the image makes no $2)"; fi
      continue
    fi
    if docker run --rm --entrypoint sh -v "$v:$2" "$P/$1:new" -c \
         "cat $2/written-by-old >/dev/null && echo new >> $2/written-by-old && echo y > $2/sub/g && echo z > $2/written-by-new && ls -ln $2 $2/sub"; then
      ok "$3: the new $1 image reads and writes what the old one wrote"
    else bad "$3: the new $1 image cannot write the old volume"; fi
  done
fi

say "result: $fails failure(s)"
exit $((fails > 0))
