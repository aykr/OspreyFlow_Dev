"""§6a.1's *Moving to a new release (poc shape)*, and §6a.8's line on the report sync, held to the
`cloud-platform` profile's rendered runbooks (platform-b's v0.5.2 run sheet, Q1: the client upgrades by
running `INSTALL.md` again from the new release's copy, the backup first). Each statement names the
runbook that does it, so a runbook changing under it turns the guide red (rule 12):

- there is no separate upgrade runbook, and the install's `helm upgrade --install` is the upgrade;
- the backup first is the runbook's *Before an upgrade*, which stops the pods the guide names;
- the install's own checks are section 6's (the Conduit reads Entra's settings) and section 7's (`/healthz`);
- the install test that is to check it has not run: the paragraph says so until its log is recorded;
- the report sync is rendered only with reporting on, so the runbook's scaling of it may say "not found".
"""

from __future__ import annotations

import re
from functools import cache
from typing import Any

import yaml

from tests.test_guides_cloud_platform import ADMIN, CORE
from tests.test_guides_cloud_platform import section as _section

BUILD = CORE.parent / "OspreyFlow_Build"
RUNBOOK = (CORE / "deploy" / "RUNBOOK.md").read_text(encoding="utf-8")
#: The pods a runbook names, and the guide's words for them.
WORDS = {"api": "the Conduit", "worker": "the workers", "report-sync": "the report sync"}


def section(heading: str) -> str:
    return re.sub(r"\s+", " ", _section(ADMIN, heading))


def upgrade_paragraph() -> str:
    m = re.search(r"\*\*Moving to a new release \(poc shape\)\.\*\*(.*?)\*\*A platform is a settings file\*\*",
                  section("### 6a.1"))  # fmt: skip
    assert m, "§6a.1's paragraph on moving to a new release"
    return m.group(1)


@cache
def artefacts(reporting: bool) -> dict[str, str]:
    from harness.render import render
    from tools.cp_policy_check import FIXTURES, _resolver

    from schemas.deployment import OspreyConfig

    raw: dict[str, Any] = yaml.safe_load((FIXTURES / "poc.yaml").read_text(encoding="utf-8"))
    if reporting:
        raw["reporting"] = {"superset": True, "sync": True}
        raw["cloud_platform"].setdefault("claims", {})["superset_client_id"] = "60000000-0000-4000-8000-000000000006"
    return dict(render(OspreyConfig.model_validate(raw), resolver=_resolver).artefacts)


def test_the_upgrade_is_the_install_run_again_and_no_runbook_of_its_own() -> None:
    runbooks = {name for name in artefacts(False) if name.endswith(".md")}
    install = artefacts(False)["INSTALL.md"]
    text = upgrade_paragraph()
    assert ("There is no separate upgrade runbook." in text) is (not any("UPGRADE" in r.upper() for r in runbooks))
    assert ("its `helm upgrade --install` moves the deployment" in text) is ("helm upgrade --install" in install)


def test_the_backup_first_stops_the_pods_the_runbook_s_before_an_upgrade_stops() -> None:
    m = re.search(r"\*\*Before an upgrade, with the Conduit stopped\*\*.*?scale ((?:deployment/[a-z-]+ )+)--replicas=0",
                  RUNBOOK, re.DOTALL)  # fmt: skip
    assert m, "the runbook's Before an upgrade"
    stopped = [d.removeprefix("deployment/") for d in m.group(1).split()]
    step = re.search(r"1\. \*\*Back up first\.\*\*(.*?) 2\. \*\*", upgrade_paragraph())
    assert step and "*Before an upgrade*" in step.group(1)
    assert [p for p in stopped if WORDS.get(p, f"`{p}`") not in step.group(1)] == []


def test_the_install_s_own_checks_are_the_ones_the_guide_names() -> None:
    install = artefacts(False)["INSTALL.md"]
    six = re.search(r"^## 6\. Sign-in.*?(?=^## 7\.)", install, re.MULTILINE | re.DOTALL)
    seven = re.search(r"^## 7\. Check.*?(?=^## 8\.|\Z)", install, re.MULTILINE | re.DOTALL)
    assert six and seven, "INSTALL.md's sections 6 and 7"
    text = upgrade_paragraph()
    assert ("section 6's check that the Conduit reads Entra's settings" in text) is (
        "printenv OSPREY_IDENTITY_PROVIDER OIDC_ISSUER" in six.group(0))
    assert ("section 7's `/healthz` through the Glass" in text) is ("/healthz" in seven.group(0))


def test_the_install_test_is_said_not_to_have_run_until_its_log_is_recorded() -> None:
    """platform-b's run sheet names the upgrade's log `UPGRADE.log`, kept with the step's records."""
    ran = any(BUILD.joinpath("process").rglob("UPGRADE.log"))
    text = upgrade_paragraph()
    assert ("It has not run yet." in text) is (not ran)
    assert ("is to install v0.5.1, then the candidate" in text) is (not ran)
    assert "has not been rehearsed" in text


def test_section_6a8_says_when_the_report_sync_is_rendered() -> None:
    def has_sync(reporting: bool) -> bool:
        values = yaml.safe_load(artefacts(reporting)["values.yaml"])
        return "report-sync" in [w["name"] for w in values["workloads"]]

    text = section("### 6a.8")
    assert "is not rendered on this profile" not in text
    assert ("`deployment/report-sync`, which is rendered only with reporting on" in text) is (
        has_sync(True) and not has_sync(False))
