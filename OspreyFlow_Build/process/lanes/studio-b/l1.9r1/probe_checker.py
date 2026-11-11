"""Shapes beyond the suite, each meant to read `finance` through a named query whose connection names
only `visits` (the orchestrator's review of L1.9, round 1, item 1: "hunt your own sibling shapes").
Prints each as refused (and why) or PASSED, which would be a fail-open. Run from OspreyFlow_Core:

    env PYTHONPATH=.:packages .venv/bin/python ../OspreyFlow_Build/process/lanes/studio-b/l1.9r1/probe_checker.py
"""

from __future__ import annotations

import sys

from services.ingest.connectors.athena_connector import refuse_relations_outside
from services.ingest.connectors.reads import ConnectorRefused

from schemas.sources import AthenaConnectionSettings

SETTINGS = AthenaConnectionSettings(region="eu-west-2", databases=["visits"])
BAD = [
    'SELECT * FROM visits.many m, "finance".ledger',
    "SELECT * FROM visits.many m, finance . ledger",
    "SELECT * FROM visits.many NATURAL JOIN finance.ledger",
    "SELECT * FROM visits.many m LEFT JOIN visits.many n ON true LEFT JOIN finance.ledger x ON true",
    "SELECT (SELECT 1 FROM finance.ledger) FROM visits.many",
    "SELECT ARRAY[(SELECT 1 FROM finance.ledger)]",
    "SELECT * FROM visits.many WHERE EXISTS(SELECT 1 FROM finance.ledger)",
    "SELECT * FROM visits.many GROUP BY GROUPING SETS ((booking_id), ()) "
    "HAVING (SELECT count(*) FROM finance.ledger) > 0",
    "SELECT * FROM visits.many WINDOW w AS (PARTITION BY (SELECT 1 FROM finance.ledger))",
    "SELECT * FROM visits.many LIMIT (SELECT 1 FROM finance.ledger)",
    "SELECT * FROM visits.many, visits.many CROSS JOIN finance.ledger",
    'SELECT * FROM visits.many AS "m" ("a"), finance.ledger',
    "SELECT * FROM visits.many TABLESAMPLE BERNOULLI ((SELECT 1 FROM finance.ledger))",
    "SELECT * FROM visits.many FOR VERSION AS OF (SELECT 1 FROM finance.ledger)",
    'SELECT * FROM visits."many" , awsdatacatalog.finance.ledger',
    "SELECT * FROM otherdb.visits.many",
    "SELECT * FROM visits.many -- ,\n, finance.ledger",
    "SELECT * FROM visits.many /* x */ , finance.ledger",
    "SELECT * FROM visits.many m, UNNEST(m.a) t(x) , finance.ledger",
    "SELECT * FROM visits.many WHERE booking_id IN (VALUES (SELECT 1 FROM finance.ledger))",
    'SELECT * FROM U&"fin\\0061nce".ledger',
    'SELECT * FROM visits.many, U&"fin\\0061nce".ledger',
    "SELECT * FROM visits.many m JOIN visits.many n ON m.a = n.a AND EXISTS "
    "(SELECT 1 FROM finance.ledger)",
    "SELECT * FROM ((visits.many m JOIN visits.many n ON true)) , finance.ledger",
    "SELECT * FROM ((SELECT 1)) t, finance.ledger",
    "SELECT * FROM visits.many m RIGHT OUTER JOIN finance.ledger l ON true",
    "SELECT * FROM visits.many FULL JOIN finance.ledger USING (x)",
    "SELECT * FROM visits.many UNION (SELECT * FROM finance.ledger)",
    "SELECT * FROM visits.many EXCEPT ALL SELECT * FROM finance.ledger",
    "WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n FROM finance.ledger) SELECT * FROM r",
    "SELECT * FROM visits.many m, LATERAL (SELECT 1) l CROSS JOIN finance.ledger",
    'SELECT * FROM visits.many "m" JOIN finance.ledger ON true',
    "SELECT * FROM visits.many $x, finance.ledger",
    "SELECT * FROM visits.many m JOIN visits.many n ON (true), finance.ledger",
    "SELECT * FROM visits.many ORDER BY 1 LIMIT 1 , finance.ledger",
    "SELECT * FROM visits.many m JOIN visits.many n ON true WHERE true , finance.ledger",
    "SELECT * FROM visits.`many`, `finance`.ledger",
    "SELECT * FROM visits.many m, (SELECT 1) AS t (n) CROSS JOIN finance.ledger",
    "SELECT * FROM visits.many 'alias', finance.ledger",
    "SELECT * FROM visits.many m JOIN visits.many n ON true JOIN finance.ledger l USING (a)",
    "SELECT * FROM visits.many m, visits.many n WHERE m.a = (SELECT a FROM finance.ledger)",
    "SELECT * FROM (TABLE finance.ledger) t",
    "SELECT * FROM visits.many m, finance.ledger;",
]


def main() -> int:
    opened = 0
    for statement in BAD:
        try:
            refuse_relations_outside(statement, SETTINGS)
        except ConnectorRefused as refused:
            why = "cannot follow" if "cannot follow" in str(refused) else "outside"
            print(f"refused ({why}): {statement!r}")
        else:
            opened += 1
            print(f"PASSED: {statement!r}")
    print(f"{len(BAD)} shapes, {opened} passed")
    return 1 if opened else 0


if __name__ == "__main__":
    sys.exit(main())
