# Counts and rule states of osprey-upg's Postgres (read-only SELECTs).
q() { docker exec osprey-upg-postgres-1 sh -c "psql -U \$POSTGRES_USER -d \${POSTGRES_DB:-\$POSTGRES_USER} -At -F' | ' -c \"$1\"" 2>&1; }
for t in investigations investigation_datasets datasets alerts typology_rules typology_rule_versions studio_recipes recipe_runs hotlists monitors saved_patterns; do echo "$t: $(q "select count(*) from $t")"; done
echo "-- cases"; q "select id, name, coalesce(branched_from,'-'), created_by from investigations order by created_at"
echo "-- rules"; q "select id, name, status, investigation_id, owner_id, coalesce(dataset_id,'-'), params->'sentence'->>'scope', params->>'typology' from typology_rules order by created_at"
echo "-- alerts by state"; q "select status, count(*) from alerts group by 1"
for t in cases case_views view_shares case_layers sources source_policies dataset_models home_cases; do r=$(q "select count(*) from $t" | head -1); case "$r" in *ERROR*|*does\ not*) ;; *) echo "$t: $r";; esac; done
