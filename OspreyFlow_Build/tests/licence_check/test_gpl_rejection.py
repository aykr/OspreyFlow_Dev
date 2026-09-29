"""Deterministic proof of Phase 0's exit criterion: a GPL dependency fails the
build. Phase 0's own plan, §3.4 item 3 / §2 amendment 3:
no scratch branch, no manual step — this runs on every PR.

`tests/fixtures/licence_check/gpl_dependency/site-packages/` holds a fabricated
dist-info for a package declaring GPL-3.0, entirely offline and reproducible.
"""

from __future__ import annotations

import sys

from tools.layout import REPO as REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "tools"))

from licence_check import find_offenders, run_pip_licenses  # noqa: E402

FIXTURE_SITE_PACKAGES = (
    REPO_ROOT / "tests" / "fixtures" / "licence_check" / "gpl_dependency" / "site-packages"
)


def test_gpl_fixture_package_is_rejected_by_name() -> None:
    packages = run_pip_licenses(str(FIXTURE_SITE_PACKAGES))
    offenders = find_offenders(packages)
    offender_names = {p["Name"] for p in offenders}
    assert "evil-gpl-pkg" in offender_names, (
        "the GPL fixture package must be named as an offender — got "
        f"{sorted(offender_names)}"
    )


def test_real_environment_has_no_offenders() -> None:
    packages = run_pip_licenses(None)
    offenders = find_offenders(packages)
    assert offenders == [], f"unexpected licence-check offenders: {offenders}"
