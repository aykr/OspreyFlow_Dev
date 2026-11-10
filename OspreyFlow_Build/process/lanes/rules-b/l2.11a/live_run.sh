#!/bin/sh
# Run on the server's copy (stack_lease.sh remote): the live set, then a plant on the copy alone, restored after.
cd ../OspreyFlow_Core || exit 2
T=../OspreyFlow_Build/tests
P=".venv/bin/pytest -c ../OspreyFlow_Build/pytest.ini -q -rfE -p no:cacheprovider"
echo "## the live set"
$P $T/ingest/test_rule_standards_routes_live.py $T/services/api/test_route_rights.py $T/ingest/test_typology_rule_routes.py $T/services/api/test_rule_maker_checker_routes.py $T/services/api/test_rule_schedule.py $T/services/api/test_audit_section_store.py $T/services/api/test_rule_standards_routes.py $T/services/api/test_investigation_levels.py $T/services/api/test_rule_sentence_routes.py
SET=$?
echo "EXIT $SET"
echo "## plant: the import's source-or-composite check removed (server copy only), against the real dataset store"
F=services/api/rule_standards_routes.py
cp $F /tmp/rules-b-rule_standards_routes.py.orig
python3 - <<'PY'
p = "services/api/rule_standards_routes.py"; s = open(p).read()
o = " if d.kind in (SOURCE, COMPOSITE)"
assert s.count(o) == 1, "plant site moved"
open(p, "w").write(s.replace(o, ""))
PY
$P $T/ingest/test_rule_standards_routes_live.py
echo "PLANT EXIT $? (red expected)"
cp /tmp/rules-b-rule_standards_routes.py.orig $F
cmp -s /tmp/rules-b-rule_standards_routes.py.orig $F && echo "restored"
exit $SET
