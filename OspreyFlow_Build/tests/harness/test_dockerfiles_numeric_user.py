"""Every image of ours runs as one numeric non-root user, 10001 (`spec/06_DECISIONS.md` ADR-148
decision 3): a platform that sets `runAsNonRoot` cannot check a user given by name, so the kubelet
refuses to start it, and a pod spec's `runAsUser` then has to agree with the image's own user.

Every `Dockerfile*` is read, as `make licence-check` reads them, with its parser
(`tools.licence_check._instructions`: continued lines joined, comments left out), through
`make cp-policy-check`'s own `final_user`, so the gate and this test are one reading; a variant (a
Conduit built without Java, say) is held to it too; `FROM` and `USER` are matched as Docker matches
them, in any case. Each refusal is planted in a real Dockerfile's own text (rule 15)."""

from __future__ import annotations

from pathlib import Path

import pytest
from tools.cp_policy_check import final_user

CORE = Path(__file__).resolve().parents[3] / "OspreyFlow_Core"
OURS = sorted(
    p
    for p in CORE.rglob("Dockerfile*")
    if p.is_file() and not {"node_modules", ".venv"} & set(p.parts)
)
API = (CORE / "services" / "api" / "Dockerfile").read_text(encoding="utf-8")


def test_every_dockerfile_is_found() -> None:
    names = {str(p.relative_to(CORE)) for p in OURS}
    assert {
        "services/api/Dockerfile", "services/ingest/Dockerfile", "services/worker/Dockerfile",
        "services/report_sync/Dockerfile", "services/ner/Dockerfile", "harness/Dockerfile",
        "apps/workspace/Dockerfile", "deploy/superset/Dockerfile",
    } <= names  # fmt: skip


@pytest.mark.parametrize("dockerfile", OURS, ids=lambda p: str(p.relative_to(CORE)))
def test_the_image_runs_as_10001_by_number(dockerfile: Path) -> None:
    assert final_user(dockerfile.read_text(encoding="utf-8")) == "10001:10001"


def test_the_real_dockerfile_passes() -> None:
    assert final_user(API) == "10001:10001"


@pytest.mark.parametrize(
    "plant",
    [
        lambda t: t.replace("USER 10001:10001", "USER osprey"),  # named
        lambda t: t + "user root\n",  # a lower-case USER after it is Docker's USER too
        lambda t: t + "USER 0:0\n",
        lambda t: t.replace("USER 10001:10001", "# USER 10001:10001"),  # none in the last stage
        lambda t: t + "from python:3.12-slim\nRUN true\n",  # a later stage, lower case, no USER
        lambda t: t.replace("USER 10001:10001", "USER \\\n    root"),  # continued onto a line
    ],
    ids=["named", "lower-case-root", "uid-zero", "commented-out", "later-stage", "continued"],
)
def test_a_fault_planted_in_the_real_dockerfile_is_refused(plant: object) -> None:
    planted = plant(API)  # type: ignore[operator]
    assert planted != API
    assert final_user(planted) != "10001:10001"
