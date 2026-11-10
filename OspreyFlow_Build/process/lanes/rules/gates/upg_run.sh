# UPG's run driver on ospreyflow-test: one phase per call, each logged under $R/logs by its caller.
# Run 3 (platform-b's fix, option A: refresh refuses a deployment rendered before ADR-135 Am. 2):
#   install                      fresh v0.4.12 clone and install (fixture-corp, operation-ledger)
#   provider                     a hosted provider enabled with a synthetic key, by v0.4.12's apply
#   fixtures                     a branch, a pending whole-deployment rule, the list at version 1
#   v0412-update <export> <sha>  v0.4.12's update by hand, as far as its files step: backup (v0.4.12's
#                                code), its own _keep_rollback_point, the checkout moved, then the plain
#                                `scripts.refresh --files-only` with no OSPREYFLOW_DEPLOYMENT_DIR, as
#                                v0.4.12's update.py runs it; every file of the folder hashed around it
#   backup | apply | update      today's CLI, `--name osprey-upg`
#   stop | apply-build           the stand-in for update's pull of a release's images (none exists)
#   files-twice                  today's files step twice, OSPREYFLOW_DEPLOYMENT_DIR set; hashes equal
#   keys | gateway | health      the end-state asserts
#   teardown                     down -v; refuses to remove a folder while anything of the run is left
# Every compose call goes through upg_guard.sh's dc; nothing here prunes or removes an image.
set -u
R=/root/osprey-runs/rules-upg
. $R/tools/upg_guard.sh
PY=$R/repo/.venv/bin/python
CLI="env PATH=/root/.local/bin:$PATH HOME=$R/home DOCKER_CONFIG=/root/.docker OSPREYFLOW_HOME=$R/repo PYTHONPATH=.:packages:cli"
say() { echo "upg-run: $*"; }
hash() { $PY $R/tools/upg_folderhash.py snap $D "$1"; }

case "$1" in
install)
  [ ! -e $R/repo ] && [ ! -e $R/home/.ospreyflow ] || { say "REFUSED: an earlier run's repo or home is still there"; exit 2; }
  mkdir -p $R/home $R/logs
  docker ps -a --format "{{.Names}}" | sort > $R/logs/containers.before
  docker volume ls -q | sort > $R/logs/volumes.before
  git clone -q https://github.com/aykr/OspreyFlow.git $R/repo && cd $R/repo && git checkout -q v0.4.12 || exit 1
  PATH=/root/.local/bin:$PATH uv sync --frozen -q --all-extras || exit 1
  # v0.4.12's preflight reads the proxy's ${OSPREY_ARCADEDB_PORT:-2480} before deployment.env exists.
  OSPREY_ARCADEDB_PORT=2500 $CLI .venv/bin/python -m ospreyflow install --mode lite --name osprey-upg \
    --config $R/answers.yaml --yes < /dev/null
  say "install exit $?" ;;
provider)
  cd $R/repo
  $PY - "$D/osprey.yaml" <<'EOF'
import sys, yaml
path = sys.argv[1]
doc = yaml.safe_load(open(path))
doc["models"]["local_only"] = False
doc["models"]["providers"] = [{"name": "gemini", "roles": {"extraction": "gemini/gemini-2.5-flash"}}]
open(path, "w").write(yaml.safe_dump(doc, sort_keys=False))
print("upg-run: osprey.yaml: models.local_only false, provider gemini (extraction); defaults left local")
EOF
  # A synthetic key (rule 9): not a credential anywhere, so the assert is not vacuous and nothing leaks.
  # v0.4.12's apply has the same 2480 preflight defect as its install.
  OSPREY_ARCADEDB_PORT=2500 OSPREY_MODEL_KEY_GEMINI=upg-synthetic-not-a-real-key-0000 $CLI .venv/bin/python -m ospreyflow apply --name osprey-upg < /dev/null
  say "apply exit $?"
  say "provider key lines in deployment.env: $(grep -c '^OSPREY_MODEL_KEY_' $D/deployment.env)" ;;
fixtures)
  C=$R/tools/chk.sh
  FC=$(sed -n "s/.*Case .Fixture Corp.* is \([0-9A-Z]*\)\..*/\1/p" $R/logs/01-install-v0.4.12.log)
  LG=$(sed -n "s/.*Case .Operation Ledger.* is \([0-9A-Z]*\)\..*/\1/p" $R/logs/01-install-v0.4.12.log)
  echo "FC=$FC LG=$LG" > $R/logs/ids.txt
  sh $C analyst "POST:/v1/investigations/$FC/branch"
  sh $C admin "POST:/v1/investigations/$FC/rules/sentence|{\"name\": \"UPG whole-deployment: Okafor\", \"sentence\": {\"subject\": \"Person\", \"conditions\": [{\"op\": \"equals\", \"property\": \"family_name\", \"value\": \"Okafor\"}], \"scope\": \"deployment\"}}" \
    "POST:/v1/admin/screening-lists/UK%20Sanctions%20List%20(synthetic)/refresh"
  sh $R/tools/snap.sh ;;
v0412-update)
  cd $R/repo
  [ "$(git describe --tags --exact-match 2>/dev/null)" = v0.4.12 ] || { say "REFUSED: the checkout is not at v0.4.12"; exit 2; }
  commit=$(git rev-parse HEAD)
  $CLI .venv/bin/python -m ospreyflow backup --name osprey-upg < /dev/null | tail -2; say "backup exit $?"
  point=$($CLI .venv/bin/python -c "
from pathlib import Path; from harness.update import _keep_rollback_point
print(_keep_rollback_point(Path('$D'), 'v0.4.12', '$commit'))")
  say "v0.4.12's own rollback point: ${point#$D/}"
  $PY $R/tools/upg_envdiff.py snap $D/deployment.env $R/logs/env.0-v0.4.12.json
  hash $R/logs/folder.0-before-files.json
  # As `git checkout <tag>` would: tracked files replaced, ignored ones (.install, .venv) kept.
  rsync -a --delete --exclude .git --exclude .venv --exclude .install --exclude node_modules "$2/" $R/repo/ &&
    chown -R root:root $R/repo && git checkout -q -b upg-$3 && git add -A &&
    git -c user.name="UPG rehearsal" -c user.email=upg@ospreyflow.invalid commit -q -m "OspreyFlow — from $3" &&
    git log --oneline -1 || exit 1
  # v0.4.12's update.py runs the files step from the moved checkout before syncing anything, with the
  # interpreter it was started with, and with no OSPREYFLOW_DEPLOYMENT_DIR (its cli passes none).
  say "\$ python -m scripts.refresh --files-only   (as v0.4.12's update runs it: no OSPREYFLOW_DEPLOYMENT_DIR)"
  env -u OSPREYFLOW_DEPLOYMENT_DIR HOME=$R/home OSPREYFLOW_HOME=$R/repo PYTHONPATH=.:packages:cli \
    .venv/bin/python -m scripts.refresh --files-only; say "files step exit $?"
  hash $R/logs/folder.1-after-files.json
  say "--- the folder around the refused files step (must be unchanged)"
  $PY $R/tools/upg_folderhash.py diff $R/logs/folder.0-before-files.json $R/logs/folder.1-after-files.json
  say "folder diff exit $?"
  PATH=/root/.local/bin:$PATH uv sync --frozen -q --all-extras ;;
backup|apply|update)
  cd $R/repo
  $CLI .venv/bin/python -m ospreyflow $1 --name osprey-upg ${2:-} < /dev/null; say "$1 exit $?" ;;
stop)
  cd $R/repo
  $CLI .venv/bin/python -m ospreyflow stop --name osprey-upg < /dev/null; say "stop exit $?" ;;
apply-build)
  cd $R/repo
  (cd $R/tools && $PY upg_images.py hold $R/logs/images-state.json)
  $CLI .venv/bin/python -m harness.apply --build --config $D/osprey.yaml --out-root $R/home/.ospreyflow/deployments < /dev/null
  rc=$?; (cd $R/tools && $PY upg_images.py claim $R/logs/images-state.json $D/compose.yaml)
  say "apply --build exit $rc" ;;
files-twice)
  cd $R/repo
  for n in 1 2; do
    hash $R/logs/folder.f$n-before.json
    say "\$ OSPREYFLOW_DEPLOYMENT_DIR=<osprey-upg> python -m scripts.refresh --files-only   (pass $n)"
    env HOME=$R/home OSPREYFLOW_DEPLOYMENT_DIR=$D OSPREYFLOW_HOME=$R/repo PYTHONPATH=.:packages:cli \
      .venv/bin/python -m scripts.refresh --files-only 2>&1 | tail -2; say "files step exit $?"
    hash $R/logs/folder.f$n-after.json
    $PY $R/tools/upg_folderhash.py diff $R/logs/folder.f$n-before.json $R/logs/folder.f$n-after.json
    say "pass $n folder diff exit $?"
  done ;;
keys)
  say "OSPREY_MODEL_KEY_* lines left: $(grep -c '^OSPREY_MODEL_KEY_' $D/deployment.env)"
  say "OSPREY_MODEL_KEYS_IN_GATEWAY: $(sed -n 's/^OSPREY_MODEL_KEYS_IN_GATEWAY=//p' $D/deployment.env)"
  say "--- every secret held at v0.4.12, after"
  $PY $R/tools/upg_envdiff.py snap $D/deployment.env $R/logs/env.9-end.json
  $PY $R/tools/upg_envdiff.py diff $R/logs/env.0-v0.4.12.json $R/logs/env.9-end.json ;;
gateway)
  # The two keys compared by hash inside their own containers; the Conduit's key asked of the gateway.
  g=$(docker exec osprey-upg-litellm-1 sh -c 'printf %s "$LITELLM_MASTER_KEY" | sha256sum' | cut -c1-12)
  a=$(docker exec osprey-upg-api-1 sh -c 'printf %s "$LITELLM_API_KEY" | sha256sum' | cut -c1-12)
  [ "$g" = "$a" ] && say "the gateway's master key equals the Conduit's LITELLM_API_KEY ($g)" ||
    say "MISMATCH: the gateway's master key $g, the Conduit's $a"
  docker exec osprey-upg-api-1 python -c '
import os, urllib.request, urllib.error
req = urllib.request.Request("http://litellm:4000/v1/models", headers={"Authorization": "Bearer " + os.environ["LITELLM_API_KEY"]})
try:
    print("upg-run: the gateway answered the Conduit key:", urllib.request.urlopen(req, timeout=20).status)
except urllib.error.HTTPError as e:
    print("upg-run: the gateway REFUSED the Conduit key:", e.code); raise SystemExit(1)
' ;;
health)
  dc ps --format "{{.Service}} {{.State}} {{.Health}}" | sort
  say "running: $(dc ps --format '{{.State}}' | grep -c running); healthy: $(dc ps --format '{{.Health}}' | grep -c '^healthy')"
  say "owned images: $(dc config --images 2>/dev/null | grep -E 'osprey/|ghcr.io/aykr' | tr '\n' ' ')" ;;
teardown)
  dc down -v --remove-orphans; rc=$?
  left=$(docker ps -a -q --filter label=com.docker.compose.project=$UPG | wc -l)
  [ $rc = 0 ] && [ "$left" = 0 ] || { say "REFUSED to go on: down -v exit $rc, $left containers left (take them down by project label first)"; exit 2; }
  rm_volumes $(docker volume ls -q --filter label=com.docker.compose.project=$UPG) || exit 2
  if [ -f $R/logs/images-state.json ]; then
    (cd $R/tools && $PY upg_images.py restore $R/logs/images-state.json && $PY upg_images.py check $R/logs/images-state.json) || exit 2
  else
    say "no image was held or built in this run: no tag to put back"
  fi
  say "nothing of $UPG is left: containers $left, volumes $(docker volume ls -q --filter name=^$UPG | wc -l)" ;;
capture)
  # Which containers a step recreated, and the stores' mounts (platform-b's ask): `capture <label>`.
  say "--- containers ($2)"; dc ps -a --format '{{.Name}} {{.ID}} {{.CreatedAt}}' | sort
  say "--- stores' mounts ($2)"
  for s in postgres arcadedb clickhouse opensearch valkey; do
    c=$UPG-$s-1; docker inspect -f "$c {{range .Mounts}}{{.Name}}:{{.Destination}} {{end}}" $c 2>/dev/null
  done
  say "--- data ($2)"; sh $R/tools/snap.sh | head -11
  for v in $(docker volume ls -q --filter label=com.docker.compose.project=$UPG | sort); do
    echo "$v $(docker run --rm -v $v:/v:ro busybox:1.36 du -s /v 2>/dev/null | cut -f1)KiB"
  done ;;
*) say "no phase $1"; exit 2 ;;
esac
