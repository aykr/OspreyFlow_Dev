# usage: migrate.sh <n> <script>   — dry run, run, re-run, each logged; stops at the first failure.
R=/root/osprey-runs/rules-upg; n=$1; s=$2
for pass in dry-run run rerun; do
  f=$R/logs/08-$n-$s.$pass.txt
  if [ $pass = dry-run ]; then flag=--dry-run; else flag=; fi
  echo "\$ docker exec osprey-upg-api-1 python -m scripts.$s $flag" > $f
  docker exec osprey-upg-api-1 python -m scripts.$s $flag >> $f 2>&1; rc=$?
  echo "exit $rc" >> $f
  echo "== $s $pass: exit $rc, $(wc -l < $f) lines"; tail -6 $f | cut -c1-260
  [ $rc = 0 ] || exit $rc
done
