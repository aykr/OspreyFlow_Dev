"""GitHub's `conformance` job runs two real Conduits beside the suite's own stores
(`tests/services/api/test_statelessness.py`, `test_statelessness_clickhouse.py`). One Conduit holds 50
Postgres connections once it is up (its stores' pools at their minimum, measured: process/lanes/
platform-b/stateless/), so Postgres's default `max_connections` of 100 refused the second
(`TooManyConnectionsError`, GitHub run 43310891764). The lane stacks allow 400 for the same reason
(`scripts/stack_lease.sh`, `PG_CONNECTIONS`, 10 November 2026). This holds the CI job to the same
number, so the two cannot drift apart again."""

from __future__ import annotations

import re

from tools.layout import BUILD
from tools.layout import REPO as REPO_ROOT

CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"
LEASE = BUILD / "scripts" / "stack_lease.sh"


def _job(text: str, name: str) -> str:
    found = re.search(rf"^  {re.escape(name)}:\n(.*?)(?=^  [a-z0-9-]+:\n|\Z)", text, re.M | re.S)
    assert found, f"no job {name} in ci.yml"
    return found.group(1)


def test_the_conformance_jobs_postgres_allows_what_the_lane_stacks_do() -> None:
    wanted = int(re.search(r"^PG_CONNECTIONS=(\d+)$", LEASE.read_text(encoding="utf-8"), re.M).group(1))
    job = _job(CI.read_text(encoding="utf-8"), "conformance")
    raised = re.findall(r"ALTER SYSTEM SET max_connections = (\d+)", job)
    assert raised, "the conformance job leaves Postgres at its default max_connections (100)"
    assert int(raised[0]) >= wanted, f"max_connections {raised[0]} < the lane stacks' {wanted}"
    assert "SHOW max_connections" in job, "the job reads the setting back after the restart"
