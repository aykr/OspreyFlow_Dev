"""The managed PostgreSQL's connections on the cloud-platform profile: the least it must allow and
what its RDS parameter group sets (R1 on kind, finding 15; the owner's decisions of 13 November
2026). Read by the Terraform (`terraform.py`) and the install runbook (`runbooks.py`);
`tests/harness/test_cloud_platform_poc.py` counts the least a second time, so a term dropped here is
red."""

from __future__ import annotations

#: The Conduit's figures are ADR-114 Amendment 43's (`harness.profiles`, where a running Conduit's
#: own pools hold them; `test_cloud_platform_poc.py` holds these equal to them): one Conduit's pools
#: at their `max_size`, and the one connection each running load holds outside them.
CONDUIT_POOL_CEILING = 220
RUNNING_LOADS_ALLOWED = 20
GATEWAY_POOL_MAX = 10
OPERATOR_RESERVE = 20
#: Superset and the report sync, rendered from v0.5.2 at the client page's counts: two copies of
#: Superset, each two gunicorn workers (`deploy/superset/osprey_entrypoint.py`) at SQLAlchemy's
#: pool of 5 with 10 overflow, and up to 8 queries to the mart; two of the report sync, its mart
#: pool 4 each. Sized now so the client's database does not change between v0.5.1 and v0.5.2.
SUPERSET_COPIES = 2
SUPERSET_WORKERS = 2
SQLALCHEMY_POOL = 5 + 10
SUPERSET_MART_QUERIES = 8
REPORT_SYNC_COPIES = 2
REPORT_SYNC_POOL = 4
#: An upgrade runs each Deployment's old and new copies side by side.
UPGRADE_OVERLAP = 2
#: The least it must allow: two Conduits (an update's old and new) and the worker opening the same
#: stores, the gateway, an operator's reserve, and Superset's and the report sync's copies doubled
#: by an upgrade in progress. 918.
POSTGRES_LEAST_CONNECTIONS = (
    3 * (CONDUIT_POOL_CEILING + RUNNING_LOADS_ALLOWED)
    + GATEWAY_POOL_MAX
    + OPERATOR_RESERVE
    + UPGRADE_OVERLAP
    * (
        SUPERSET_COPIES * (SUPERSET_WORKERS * SQLALCHEMY_POOL + SUPERSET_MART_QUERIES)
        + REPORT_SYNC_COPIES * REPORT_SYNC_POOL
    )
)
#: What the RDS parameter group sets (the owner's figure, 13 November 2026): the least above, with
#: room for what it does not count (a third Conduit while a pod is rescheduled, a slow drain).
POSTGRES_MAX_CONNECTIONS = 1000
