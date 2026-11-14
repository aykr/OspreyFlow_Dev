# platform-b's v0.5.0 -> v0.5.1 candidate (7d76022, release/v0.5.1) upgrade rehearsal on ospreyflow-test, one phase per
# call, each logged by its caller. Adapted from the rules lane's driver
# (process/lanes/rules/gates/upg_run.sh, v0.4.12 -> v0.5.0); its guards (tools/upg_guard.sh, the root
# changed), its image guard (upg_images.py + P5b's p5b_live_update.py) and its teardown refusals kept.
#
#   install                    the user repository's v0.5.0 cloned; `sh install.sh` as a user runs it
#                              (uv sync, `uv tool install --editable ./cli`) in a throwaway HOME; then
#                              `ospreyflow install --mode lite --name osprey-upg` (fixture-corp, ledger)
#   snap <label>               every public table's row count, the graph's vertices, max_connections
#   backup                     CHANGELOG "Back up first": `ospreyflow backup --name osprey-upg` (v0.5.0)
#   update-emulated <export> <sha>
#                              v0.5.0's own `apply_update`, run as far as a release-less candidate can go:
#                              its backup (real_host().backup), its rollback point, the checkout moved to
#                              the export (as `git checkout <tag>`), then its files step exactly as it runs
#                              it (the old .venv's python, `-m scripts.refresh --files-only`,
#                              OSPREYFLOW_DEPLOYMENT_DIR set). Not exercised: find_release, signatures,
#                              pin_images, pull, verify_running, rollback (no signed release for 9197ea6).
#   cli                        CHANGELOG "The command is installed with `uv tool install ./cli`": the old
#                              command tried first ("keeps working"), then uv sync and the install as written
#   stop | apply-build         the stand-in for update's pull and start (no images exist for 9197ea6)
#   keys | gateway | health | pg   the end-state asserts
#   teardown                   down -v, the run's volumes, image tags put back. Exit 2 (REFUSED) as rules'.
set -u
R=/root/osprey-runs/platform-b-upg
. $R/tools/upg_guard.sh
PY=$R/repo/.venv/bin/python
U="env PATH=$R/home/.local/bin:/root/.local/bin:/usr/local/bin:/usr/bin:/bin HOME=$R/home DOCKER_CONFIG=/root/.docker UV_CACHE_DIR=/root/.cache/uv"
OF="$U ospreyflow"
# v0.5.0's install.sh installs a command that cannot start ("No module named 'httpx'", the defect
# v0.5.1's CHANGELOG names): v0.5.0's own steps run its command from the checkout's environment.
OF0="$U OSPREYFLOW_HOME=$R/repo PYTHONPATH=.:packages:cli $PY -m ospreyflow"
say() { echo "upg-run: $*"; }
hash() { $PY $R/tools/upg_folderhash.py snap $D "$1"; }
q() { docker exec $UPG-postgres-1 sh -c "psql -U \$POSTGRES_USER -d \${POSTGRES_DB:-\$POSTGRES_USER} -At -F' ' -c \"$1\"" 2>&1; }

case "$1" in
install)
  [ ! -e $R/repo ] && [ ! -e $R/home ] || { say "REFUSED: an earlier run's repo or home is still there"; exit 2; }
  [ -z "$(docker ps -a -q --filter label=com.docker.compose.project=$UPG)" ] || { say "REFUSED: project $UPG already has containers"; exit 2; }
  mkdir -p $R/home $R/logs $R/ingest $R/tiles
  docker ps -a --format "{{.Names}}" | sort > $R/logs/containers.before
  docker volume ls -q | sort > $R/logs/volumes.before
  git clone -q https://github.com/aykr/OspreyFlow.git $R/repo && cd $R/repo && git checkout -q v0.5.0 || exit 1
  git log --oneline -1
  $U sh install.sh < /dev/null; say "install.sh exit $?"
  $U uv tool list
  $OF --help < /dev/null > $R/logs/help-v050.out 2>&1; rc=$?; tail -2 $R/logs/help-v050.out
  say "v0.5.0's installed command --help, expected to fail before the repair: status $rc" ;;
deploy)
  cd $R/repo
  [ ! -e $D ] || { say "REFUSED: osprey-upg's folder already exists"; exit 2; }
  $OF0 install --mode lite --name osprey-upg --config $R/answers.yaml --yes < /dev/null
  say "install (v0.5.0, python -m ospreyflow) exit $?" ;;
snap)
  say "--- data ($2)"
  q "select table_schema || '.' || table_name, (xpath('/row/c/text()', query_to_xml(format('select count(*) as c from %I.%I', table_schema, table_name), false, true, '')))[1]::text from information_schema.tables where table_schema in ('public', 'osprey_reports') and table_type='BASE TABLE' order by 1"
  docker exec $UPG-api-1 python -c '
import base64, json, os, urllib.request
auth = "Basic " + base64.b64encode(("root:" + os.environ["ARCADEDB_ROOT_PASSWORD"]).encode()).decode()
def call(path, body=None):
    req = urllib.request.Request("http://" + os.environ.get("ARCADEDB_HOST", "arcadedb") + ":2480" + path, data=body and json.dumps(body).encode(), headers={"Authorization": auth, "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=30))["result"]
for db in sorted(call("/api/v1/databases")):
    types = call("/api/v1/query/" + db, {"language": "sql", "command": "select name, type from schema:types"})
    for t in sorted(types, key=lambda t: t["name"]):
        if t.get("type") in ("vertex", "edge"):
            n = call("/api/v1/query/" + db, {"language": "sql", "command": "select count(*) as n from `" + t["name"] + "`"})[0]["n"]
            print("graph", db, t["type"], t["name"], n)
' 2>&1 | tail -60 ;;
pg)
  say "max_connections (server): $(q 'show max_connections')"
  say "postgres command (compose.yaml): $($PY -c "import yaml,sys; print(' '.join(yaml.safe_load(open('$D/compose.yaml'))['services']['postgres'].get('command') or ['(none)']))")"
  say "postgres container started: $(docker inspect -f '{{.State.StartedAt}}' $UPG-postgres-1)" ;;
repair-c)
  # v0.5.1's CHANGELOG (7d76022), "Before you update", first bullet, in the checkout's folder.
  cd $R/repo
  say "\$ ospreyflow --help   (v0.5.0's command, before the repair)"
  $OF --help < /dev/null > $R/logs/help-before.out 2>&1; rc=$?; tail -1 $R/logs/help-before.out; say "before the repair, expected to fail: status $rc"
  say "\$ uv tool install --force --editable --with httpx ./cli"
  $U uv tool install --force --editable --with httpx ./cli < /dev/null; say "uv tool install exit $?"
  $U uv tool list --show-with
  say "\$ ospreyflow --help"
  $OF --help < /dev/null > $R/logs/help-c.out 2>&1; rc=$?; tail -2 $R/logs/help-c.out
  say "ospreyflow --help exit $rc" ;;
repair-a)
  # Candidate (a): the checkout's own environment, the bare form, no PYTHONPATH.
  cd $R/repo/cli
  say "\$ cd <checkout>/cli && ../.venv/bin/python -m ospreyflow --help   (no PYTHONPATH: $(env | grep -c '^PYTHONPATH='))"
  $U ../.venv/bin/python -m ospreyflow --help < /dev/null > $R/logs/help-a.out 2>&1; rc=$?; tail -3 $R/logs/help-a.out
  say "python -m ospreyflow --help exit $rc" ;;
backup-tool)
  cd $R/repo
  say "\$ ospreyflow backup --name osprey-upg   (the repaired command: \"Back up first\")"
  $OF backup --name osprey-upg < /dev/null; say "backup exit $?" ;;
backup)
  cd $R/repo
  $OF0 backup --name osprey-upg < /dev/null; say "backup exit $?" ;;
update-emulated)
  cd $R/repo
  [ "$(git describe --tags --exact-match 2>/dev/null)" = v0.5.0 ] || { say "REFUSED: the checkout is not at v0.5.0"; exit 2; }
  [ -d "${2:-}" ] && [ -n "${3:-}" ] || { say "REFUSED: the move needs an export folder and its sha"; exit 2; }
  commit=$(git rev-parse HEAD)
  say "--- v0.5.0's update: its own backup and rollback point (harness.update.real_host, _keep_rollback_point)"
  $U OSPREYFLOW_HOME=$R/repo PYTHONPATH=.:packages:cli $PY -c "
from pathlib import Path
from harness.update import real_host, _keep_rollback_point
d = Path('$D')
print('upg-run: the update\'s backup:', real_host(d, Path('$R/repo')).backup())
print('upg-run: rollback point:', _keep_rollback_point(d, 'v0.5.0', '$commit'))
" < /dev/null; say "backup step exit $?"
  $PY $R/tools/upg_envdiff.py snap $D/deployment.env $R/logs/env.0-v0.5.0.json
  hash $R/logs/folder.0-before-files.json
  # As `git checkout <tag>` would: tracked files replaced, ignored ones (.install, .venv) kept.
  rsync -a --delete --exclude .git --exclude .venv --exclude .install --exclude node_modules "$2/" $R/repo/ &&
    chown -R root:root $R/repo && git checkout -q -b upg-$3 && git add -A &&
    git -c user.name="UPG rehearsal" -c user.email=upg@ospreyflow.invalid commit -q -m "OspreyFlow — from $3" &&
    git log --oneline -2 || exit 1
  say "\$ <old .venv>/python -m scripts.refresh --files-only   (PYTHONPATH=<checkout>:<checkout>/packages as v0.5.0's command sets it, main.py:153; OSPREYFLOW_DEPLOYMENT_DIR=<osprey-upg>, as its update sets it)"
  $U PYTHONPATH=$R/repo:$R/repo/packages OSPREYFLOW_DEPLOYMENT_DIR=$D OSPREYFLOW_HOME=$R/repo $PY -m scripts.refresh --files-only < /dev/null
  say "files step exit $?"
  hash $R/logs/folder.1-after-files.json
  say "--- the folder around the files step"
  $PY $R/tools/upg_folderhash.py diff $R/logs/folder.0-before-files.json $R/logs/folder.1-after-files.json
  say "folder diff exit $?" ;;
envsnap)
  # The secrets before a real update, per-key hashes only (update-emulated takes its own).
  $PY $R/tools/upg_envdiff.py snap $D/deployment.env $R/logs/env.0-v0.5.0.json; say "env snapshot exit $?" ;;
update-real)
  # Run 3: the real `ospreyflow update` to the signed release, by the CHANGELOG's words, through the
  # command repaired by repair-c: find_release, signatures, its backup, pin_images, pull, start,
  # verify_running. `$2` is the tag (v0.5.1).
  cd $R/repo
  [ -n "${2:-}" ] || { say "REFUSED: update-real needs the release's tag"; exit 2; }
  say "\$ ospreyflow update --name osprey-upg --to $2 --yes"
  $OF update --name osprey-upg --to $2 --yes < /dev/null; say "update exit $?"
  say "checkout: $(git describe --tags --exact-match 2>/dev/null || git rev-parse --short HEAD)" ;;
sync)
  # The stand-in's own step, not the CHANGELOG's: the build below runs in the checkout's environment.
  cd $R/repo
  say "\$ uv sync --inexact   (stand-in: install.sh's step, so the build has the candidate's packages)"
  $U uv sync --inexact -q < /dev/null; say "uv sync exit $?" ;;
cli-after)
  # v0.5.1's CHANGELOG (7d76022), "Before you update", last bullet, in the checkout's folder.
  cd $R/repo
  say "\$ uv tool install --force --editable ./cli"
  $U uv tool install --force --editable ./cli < /dev/null; say "uv tool install exit $?"
  say "\$ uv tool list --show-with"
  $U uv tool list --show-with > $R/logs/tools.out 2>&1; cat $R/logs/tools.out
  grep -q httpx $R/logs/tools.out && say "FAILED: the httpx extra is still there" || say "no httpx extra"
  say "\$ ospreyflow --help"
  $OF --help < /dev/null > $R/logs/help-after.out 2>&1; rc=$?; tail -2 $R/logs/help-after.out
  say "ospreyflow --help exit $rc"
  say "\$ ospreyflow status --name osprey-upg"
  $OF status --name osprey-upg < /dev/null 2>&1 | tail -4; say "status exit $?" ;;
stop)
  cd $R/repo
  $OF stop --name osprey-upg < /dev/null; say "stop exit $?" ;;
apply-build)
  cd $R/repo
  (cd $R/tools && $PY upg_images.py hold $R/logs/images-state.json)
  $U OSPREYFLOW_HOME=$R/repo PYTHONPATH=.:packages:cli $PY -m harness.apply --build --config $D/osprey.yaml --out-root $R/home/.ospreyflow/deployments < /dev/null
  rc=$?; (cd $R/tools && $PY upg_images.py claim $R/logs/images-state.json $D/compose.yaml)
  say "apply --build exit $rc" ;;
keys)
  say "--- every secret held at v0.5.0, after (per-key hashes only)"
  $PY $R/tools/upg_envdiff.py snap $D/deployment.env $R/logs/env.9-end.json
  $PY $R/tools/upg_envdiff.py diff $R/logs/env.0-v0.5.0.json $R/logs/env.9-end.json; say "env diff exit $?" ;;
gateway)
  g=$(docker exec $UPG-litellm-1 sh -c 'printf %s "$LITELLM_MASTER_KEY" | sha256sum' | cut -c1-12)
  a=$(docker exec $UPG-api-1 sh -c 'printf %s "$LITELLM_API_KEY" | sha256sum' | cut -c1-12)
  [ "$g" = "$a" ] && say "the gateway's master key equals the Conduit's LITELLM_API_KEY ($g)" ||
    say "MISMATCH: the gateway's master key $g, the Conduit's $a"
  docker exec $UPG-api-1 python -c '
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
  say "version: $(sed -n 's/^OSPREY_RELEASE_VERSION=//p' $D/deployment.env)"
  cd $R/repo && $OF0 status --name osprey-upg < /dev/null 2>&1 | tail -15 ;;
teardown)
  dc down -v --remove-orphans; rc=$?
  left=$(docker ps -a -q --filter label=com.docker.compose.project=$UPG | wc -l | tr -d " ")
  [ $rc = 0 ] && [ "$left" = 0 ] || { say "REFUSED to go on: down -v exit $rc, $left containers left (take them down by project label first)"; exit 2; }
  rm_volumes $(docker volume ls -q --filter label=com.docker.compose.project=$UPG) || exit 2
  orphans=""
  for v in $(docker volume ls -q | sort | comm -13 $R/logs/volumes.before -); do
    if echo "$v" | grep -qE '^[0-9a-f]{64}$' && [ -z "$(docker ps -a -q --filter volume=$v)" ]; then
      orphans="$orphans $v"
    else
      say "a volume new since the run began, not an orphan (listed, not failed): $v"
    fi
  done
  if [ -n "$orphans" ]; then say "REFUSED: anonymous volumes no container mounts, new since the run began:$orphans"; exit 2; fi
  if [ -f $R/logs/images-state.json ]; then
    (cd $R/tools && $PY upg_images.py restore $R/logs/images-state.json && $PY upg_images.py check $R/logs/images-state.json) || exit 2
  else
    say "no image was held or built in this run: no tag to put back"
  fi
  say "nothing of $UPG is left: containers $left, volumes $(docker volume ls -q --filter name=^$UPG | wc -l)" ;;
*) say "no phase $1"; exit 2 ;;
esac
