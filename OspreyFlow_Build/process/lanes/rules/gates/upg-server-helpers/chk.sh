# usage: chk.sh <account-suffix> <ROUTES...>  (reads the password from deployment.env, never prints it)
R=/root/osprey-runs/rules-upg; D=$R/home/.ospreyflow/deployments/osprey-upg
who=$1; shift; var=OSPREY_DEMO_$(echo $who | tr a-z- A-Z_)_PASSWORD
export $var="$(sed -n "s/^$var=//p" $D/deployment.env)"
cd $R/tools && $R/repo/.venv/bin/python upg_check.py http://osprey-upg.localhost:8090 http://id.osprey-upg.localhost:8090 osprey-demo-$who $var "$@"
