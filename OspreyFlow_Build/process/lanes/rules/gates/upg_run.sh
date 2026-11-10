# UPG's run driver on ospreyflow-test: one phase per call, each logged under $R/logs.
#   sh upg_run.sh install                 fresh v0.4.12 clone and install (fixture-corp, operation-ledger)
#   sh upg_run.sh fixtures                a branch, a pending whole-deployment rule, the list at version 1
#   sh upg_run.sh move <export dir> <sha> backup with v0.4.12's code, then the checkout moved to <export>
#   sh upg_run.sh refresh                 update's files step twice, the env compared, compose config
#   sh upg_run.sh release-images          each owned image built under the reference refresh pinned, as a
#                                         release's pull would put it there (claimed by OwnImages)
#   sh upg_run.sh up                      update's own start: compose up -d --wait --pull never
#   sh upg_run.sh gateway                 the Conduit's own key asked of the gateway, from inside api
# Guards: upg_guard.sh (sourced). Nothing here removes anything; teardown is upg_guard's and upg_images'.
set -u
R=/root/osprey-runs/rules-upg
. $R/tools/upg_guard.sh
PY=$R/repo/.venv/bin/python
E="env PATH=/root/.local/bin:$PATH HOME=$R/home DOCKER_CONFIG=/root/.docker OSPREYFLOW_HOME=$R/repo PYTHONPATH=.:packages:cli"
say() { echo "upg-run: $*"; }

case "$1" in
install)
  [ ! -e $R/repo ] && [ ! -e $R/home/.ospreyflow ] || { say "REFUSED: an earlier run's repo or home is still there"; exit 2; }
  mkdir -p $R/home $R/logs
  docker ps -a --format "{{.Names}}" | sort > $R/logs/containers.before
  docker volume ls -q | sort > $R/logs/volumes.before
  git clone -q https://github.com/aykr/OspreyFlow.git $R/repo && cd $R/repo && git checkout -q v0.4.12 || exit 1
  PATH=/root/.local/bin:$PATH uv sync --frozen -q --all-extras || exit 1
  # OSPREY_ARCADEDB_PORT: v0.4.12's preflight reads the proxy's 2480 default before deployment.env exists.
  OSPREY_ARCADEDB_PORT=2500 $E .venv/bin/python -m ospreyflow install --mode lite --name osprey-upg \
    --config $R/answers.yaml --yes > $R/logs/01-install-v0.4.12.log 2>&1 < /dev/null
  say "install exit $?"; tail -2 $R/logs/01-install-v0.4.12.log ;;
fixtures)
  C=$R/tools/chk.sh
  FC=$(sed -n "s/.*Case .Fixture Corp.* is \([0-9A-Z]*\)\..*/\1/p" $R/logs/01-install-v0.4.12.log)
  LG=$(sed -n "s/.*Case .Operation Ledger.* is \([0-9A-Z]*\)\..*/\1/p" $R/logs/01-install-v0.4.12.log)
  echo "FC=$FC LG=$LG" > $R/logs/ids.txt
  { sh $C analyst "POST:/v1/investigations/$FC/branch"
    sh $C admin "POST:/v1/investigations/$FC/rules/sentence|{\"name\": \"UPG whole-deployment: Okafor\", \"sentence\": {\"subject\": \"Person\", \"conditions\": [{\"op\": \"equals\", \"property\": \"family_name\", \"value\": \"Okafor\"}], \"scope\": \"deployment\"}}" \
      "POST:/v1/admin/screening-lists/UK%20Sanctions%20List%20(synthetic)/refresh"
  } 2>&1 | tee $R/logs/02-fixtures-v0.4.12.txt
  sh $R/tools/snap.sh > $R/logs/02-snapshot-v0.4.12.txt 2>&1 ;;
move)
  cd $R/repo
  $E .venv/bin/python -m ospreyflow backup --name osprey-upg > $R/logs/03-backup-v0.4.12.log 2>&1
  say "backup exit $?"
  $PY $R/tools/upg_envdiff.py snap $D/deployment.env $R/logs/env.0-v0.4.12.json
  # As `git checkout <tag>` would: tracked files replaced, ignored ones (.install, .venv) kept.
  rsync -a --delete --exclude .git --exclude .venv --exclude .install --exclude node_modules "$2/" $R/repo/ &&
    chown -R root:root $R/repo && git checkout -q -b upg-$3 && git add -A &&
    git -c user.name="UPG rehearsal" -c user.email=upg@ospreyflow.invalid commit -q -m "OspreyFlow — from $3" &&
    git log --oneline -1 && PATH=/root/.local/bin:$PATH uv sync --frozen -q --all-extras ;;
refresh)
  cd $R/repo
  for n in 1 2; do
    say "\$ python -m scripts.refresh --files-only   (pass $n: update.py's files())"
    env HOME=$R/home OSPREYFLOW_DEPLOYMENT_DIR=$D OSPREYFLOW_HOME=$R/repo PYTHONPATH=.:packages:cli \
      .venv/bin/python -m scripts.refresh --files-only 2>&1 | tail -3
    $PY $R/tools/upg_envdiff.py snap $D/deployment.env $R/logs/env.$n-refresh.json
  done
  say "--- v0.4.12 -> refresh 1"; $PY $R/tools/upg_envdiff.py diff $R/logs/env.0-v0.4.12.json $R/logs/env.1-refresh.json
  say "--- refresh 1 -> refresh 2 (must be unchanged)"; $PY $R/tools/upg_envdiff.py diff $R/logs/env.1-refresh.json $R/logs/env.2-refresh.json
  say "refresh 1 -> 2 exit $?"
  dc config -q; say "compose config exit $?" ;;
release-images)
  cd $R/repo
  $PY - "$D/compose.yaml" > $R/logs/owned-images.txt <<'EOF'
import sys, yaml
for name, s in yaml.safe_load(open(sys.argv[1]))["services"].items():
    if str(s.get("image", "")).startswith("ghcr.io/aykr/"):
        print(name, s["image"])
EOF
  cat $R/logs/owned-images.txt
  (cd $R/tools && $PY upg_images.py hold $R/logs/images-state.json)
  while read svc ref; do
    base=${ref#ghcr.io/aykr/}; base=${base%%:*}
    for f in apps/$base/Dockerfile services/$base/Dockerfile; do [ -f $f ] && break; done
    say "\$ docker build -f $f -t $ref .   ($svc)"
    docker build -q -f $f -t "$ref" . > /dev/null || { say "build of $ref FAILED"; exit 1; }
  done < $R/logs/owned-images.txt
  (cd $R/tools && $PY upg_images.py claim $R/logs/images-state.json $D/compose.yaml) ;;
up)
  say "\$ docker compose ... up -d --wait --pull never   (update.py's 'start the release')"
  dc up -d --wait --pull never 2>&1 | tail -6; say "up exit $?" ;;
gateway)
  # The Conduit's own LITELLM_API_KEY, asked of the gateway inside the network; never printed.
  docker exec osprey-upg-api-1 python -c '
import os, urllib.request, urllib.error
req = urllib.request.Request("http://litellm:4000/v1/models", headers={"Authorization": "Bearer " + os.environ["LITELLM_API_KEY"]})
try:
    print("upg-run: the gateway answered the Conduit's key:", urllib.request.urlopen(req, timeout=20).status)
except urllib.error.HTTPError as e:
    print("upg-run: the gateway REFUSED the Conduit's key:", e.code); raise SystemExit(1)
' ;;
*) say "no phase $1"; exit 2 ;;
esac
