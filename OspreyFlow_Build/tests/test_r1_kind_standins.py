"""R1's managed-store stand-ins (`process/lanes/platform/gates/r1_kind_standins.yaml`) are what the
client's platform is, not a figure of their own: the RDS stand-in's `max_connections` is the one the
Terraform renders into the parameter group (`harness.cloud_platform.connections`, ADR-114 Amendment
46), read at apply, so the poc manifest's `managed.rds` holds on kind as it would on AWS (case-b's
v052-r1 verifier, 13 November 2026)."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml
from harness.cloud_platform.connections import POSTGRES_MAX_CONNECTIONS

GATES = Path(__file__).parents[1] / "process/lanes/platform/gates"


def test_the_rds_stand_in_allows_what_the_parameter_group_sets() -> None:
    sys.path.insert(0, str(GATES))
    try:
        import r1_kind
    finally:
        sys.path.remove(str(GATES))
    docs = [d for d in yaml.safe_load_all(r1_kind.standins_text("pw")) if d]
    postgres = next(d for d in docs if d["kind"] == "StatefulSet" and d["metadata"]["name"] == "postgres")
    args = postgres["spec"]["template"]["spec"]["containers"][0]["args"]
    assert f"max_connections={POSTGRES_MAX_CONNECTIONS}" in args
    raw = (GATES / "r1_kind_standins.yaml").read_text(encoding="utf-8")
    assert "max_connections=${MAX_CONNECTIONS}" in raw  # never a number kept beside the render's
