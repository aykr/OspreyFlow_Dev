D=/root/osprey-runs/rules-upg/home/.ospreyflow/deployments/osprey-upg
for who in ADMIN ANALYST ENGINEER; do V=OSPREY_DEMO_${who}_PASSWORD; export $V="$(sed -n "s/^$V=//p" $D/deployment.env)"; done
cd /root/osprey-runs/rules-upg/tools && ../repo/.venv/bin/python "$@"
