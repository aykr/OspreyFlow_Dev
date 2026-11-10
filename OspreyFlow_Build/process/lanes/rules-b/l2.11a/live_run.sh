#!/bin/sh
# Run on the server's copy: the live set, then the reach plant on the copy alone (restored after).
cd ../OspreyFlow_Core || exit 2
T=../OspreyFlow_Build/tests
P=".venv/bin/pytest -c ../OspreyFlow_Build/pytest.ini -q -rfE -p no:cacheprovider"
echo "## the rights table, again (author_rules guarded now)"
$P $T/services/api/test_route_rights.py
SET=$?
echo "EXIT $SET"
echo "## plant: get_listed's reach clause and its argument dropped (server copy only)"
cp services/api/typology_rules.py /tmp/rules-b-typology_rules.py.orig
python3 - <<'PY'
p = "services/api/typology_rules.py"; s = open(p).read()
head = s.index("    async def get_listed(")
body = s.index("reach, extra = reach_clause(principal, 3)", head)
assert body < s.index("    async def retire(", head), "plant site moved"
open(p, "w").write(s[:body] + 'reach, extra = "", []' + s[body + len("reach, extra = reach_clause(principal, 3)"):])
PY
$P $T/ingest/test_rule_standards_routes_live.py
echo "PLANT EXIT $? (red expected)"
cp /tmp/rules-b-typology_rules.py.orig services/api/typology_rules.py
cmp -s /tmp/rules-b-typology_rules.py.orig services/api/typology_rules.py && echo "restored"
exit $SET
