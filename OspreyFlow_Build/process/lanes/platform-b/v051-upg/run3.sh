# Run 3: the real signed update, v0.5.0 -> the tag in $TAG (v0.5.1), by its CHANGELOG's words, each phase its own log.
FROM=${1:-}   # resume: run the phases from this name on
M=/root/osprey-runs/platform-b-upg.meta; R=/root/osprey-runs/platform-b-upg; TAG=${TAG:-v0.5.1}
[ -n "$FROM" ] || [ ! -e $R ] || { echo "REFUSED: $R is still there" >> $M/logs/progress.txt; exit 2; }
[ -n "$FROM" ] || mkdir -p $R && cp -r $M/tools $M/answers.yaml $M/upg_run.sh $R/
cd $M/logs
# Stops at the first phase that reports a failure: a command's non-zero exit, a refusal, a mismatch.
p() {
  [ -z "$FROM" ] || [ "$1" = "$FROM" ] && FROM="" || return 0
  n=$1; shift; echo "=== $n $(date -u +%H:%M:%S)" >> progress.txt
  sh $R/upg_run.sh "$@" > $n.txt 2>&1; echo "    exit $? $(date -u +%H:%M:%S)" >> progress.txt
  if grep -v "folder diff exit" $n.txt | grep -qE "^upg-run: .*exit [1-9]|REFUSED|FAILED|MISMATCH|Traceback|exit [1-9]$"; then
    echo "=== STOPPED at $n: $(grep -v "folder diff exit" $n.txt | grep -E "^upg-run: .*exit [1-9]|REFUSED|FAILED|MISMATCH|Traceback|exit [1-9]$" | head -1)" >> progress.txt
    echo "=== done" >> progress.txt; exit 1
  fi
}
p 01-install-v0.5.0 install
p 02-deploy-v0.5.0 deploy
p 03a-snap-before snap "v0.5.0 before the update"
p 03b-pg-before pg
p 03c-health-before health
p 03d-envsnap envsnap
p 04-repair-c repair-c
p 05-backup-first backup-tool
p 06-update-real update-real $TAG
p 07a-health-after health
p 07b-pg-after pg
p 07c-snap-after snap "after the update"
p 07d-keys keys
p 07e-gateway gateway
p 08-cli-after cli-after
echo "=== done $(date -u +%H:%M:%S)" >> progress.txt
