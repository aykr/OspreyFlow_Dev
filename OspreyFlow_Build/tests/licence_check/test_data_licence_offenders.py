"""`06_DECISIONS.md` ADR-035 §C7 — `make licence-check` extended to a demo's own data licence,
which neither `pip-licenses` nor `license-checker` can see. Same "prove the gate with a fixture
that intentionally violates it" pattern as `test_gpl_rejection.py`, over `scripts.demo_registry`
manifests rather than an installed package.
"""

from __future__ import annotations

from scripts.demo_registry import DemoManifest

from tools.licence_check import find_data_licence_offenders


def test_a_share_alike_data_licence_is_flagged() -> None:
    """The real, named case ADR-035 §C6 raises: CDLA-Sharing-1.0 carries a share-alike obligation
    on published modifications and is not on the spec/00_ARCHITECTURE.md §7 allowlist."""
    fixture_registry = (
        DemoManifest(
            id="ibm-aml-data",
            distribution="internal",
            seed_module="scripts.seed_ibm_aml_data",
            data_licence="CDLA-Sharing-1.0",
        ),
    )

    offenders = find_data_licence_offenders(fixture_registry)

    assert offenders == [("ibm-aml-data", "CDLA-Sharing-1.0")]


def test_an_apache_licensed_data_file_is_not_flagged() -> None:
    fixture_registry = (
        DemoManifest(
            id="openly-licensed-demo",
            distribution="shipped",
            seed_module="scripts.seed_x",
            data_licence="Apache-2.0",
        ),
    )

    assert find_data_licence_offenders(fixture_registry) == []


def test_no_declared_data_licence_is_not_flagged() -> None:
    """`None` (both real entries today) means generated/owned outright, nothing to check —
    absence is not itself a violation, the same "undeclared is not unlicensed" reasoning a data
    file with no accompanying licence file at all would need a human to actually resolve, not a
    mechanical check to assume the worst about."""
    fixture_registry = (
        DemoManifest(id="hmp", distribution="shipped", seed_module="scripts.seed_hmp_fixture"),
    )

    assert find_data_licence_offenders(fixture_registry) == []


def test_the_real_registry_has_no_data_licence_offenders_today() -> None:
    """Both real entries are generated and owned outright (ADR-035 §C3/§C5) — nothing declared,
    nothing to flag."""
    from scripts.demo_registry import REGISTRY

    assert find_data_licence_offenders(REGISTRY) == []
