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
#: Superset and the report sync, rendered from v0.5.2, as many copies as the render gives each
#: shape (the owner, 13 November 2026: one of each on poc and development, `DEVELOPMENT_REPLICAS`;
#: production's two, `harness.cluster.REPLICAS`): Superset each two gunicorn workers
#: (`deploy/superset/osprey_entrypoint.py`) at SQLAlchemy's pool of 5 with 10 overflow, and up to 8
#: queries to the mart; the report sync, its mart pool of 4. Sized now so the client's database
#: does not change between v0.5.1 and v0.5.2.
SUPERSET_WORKERS = 2
SQLALCHEMY_POOL = 5 + 10
SUPERSET_MART_QUERIES = 8
REPORT_SYNC_POOL = 4
#: An upgrade runs each Deployment's old and new copies side by side.
UPGRADE_OVERLAP = 2
#: What the RDS parameter group sets in every shape (the owner's figure, 13 November 2026): above
#: each shape's least, with room for what it does not count (a third Conduit while a pod is
#: rescheduled, a slow drain).
POSTGRES_MAX_CONNECTIONS = 1000


def least_connections(superset_copies: int, report_sync_copies: int) -> int:
    """The least the managed PostgreSQL must allow: two Conduits (an update's old and new) and the
    worker opening the same stores, the gateway, an operator's reserve, and Superset's and the
    report sync's copies doubled by an upgrade in progress."""
    return (
        3 * (CONDUIT_POOL_CEILING + RUNNING_LOADS_ALLOWED)
        + GATEWAY_POOL_MAX
        + OPERATOR_RESERVE
        + UPGRADE_OVERLAP
        * (
            superset_copies * (SUPERSET_WORKERS * SQLALCHEMY_POOL + SUPERSET_MART_QUERIES)
            + report_sync_copies * REPORT_SYNC_POOL
        )
    )


def least_for(production: bool) -> int:
    """A shape's least, from the copies its render gives Superset and the report sync: 834 on poc
    and development (one of each), 918 in production (two)."""
    from harness.cloud_platform import DEVELOPMENT_REPLICAS
    from harness.cluster import REPLICAS

    copies = REPLICAS if production else DEVELOPMENT_REPLICAS
    return least_connections(copies["superset"], copies["report-sync"])
