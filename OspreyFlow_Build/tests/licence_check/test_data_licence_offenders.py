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
    """The real registry: generated demos declare nothing, and PaySim's CC-BY-SA-4.0 is admitted
    as a download only (ADR-114 Amendment 1)."""
    from scripts.demo_registry import REGISTRY

    assert find_data_licence_offenders(REGISTRY) == []


def _manifest(licence: str, delivery: str) -> DemoManifest:
    return DemoManifest(
        id="x", distribution="shipped", seed_module="x", delivery=delivery, data_licence=licence
    )


def test_cc_by_sa_is_admitted_only_for_a_download_pack() -> None:
    """ADR-114 Amendment 1 decision 5: share-alike data is acceptable only where it is fetched,
    never where it would travel in the artefact. Built from the shape the real call site passes:
    `DemoManifest` entries carrying a `delivery`."""
    assert find_data_licence_offenders((_manifest("CC-BY-SA-4.0", "download"),)) == []
    assert find_data_licence_offenders((_manifest("CC-BY-SA-4.0", "seed"),)) == [
        ("x", "CC-BY-SA-4.0")
    ]
    assert find_data_licence_offenders((_manifest("CC-BY-SA-4.0", ""),)) == [
        ("x", "CC-BY-SA-4.0")
    ]
    assert find_data_licence_offenders((_manifest("CDLA-Sharing-1.0", "download"),)) == [
        ("x", "CDLA-Sharing-1.0")
    ]


def test_the_real_registry_has_no_data_licence_offender() -> None:
    from scripts.demo_registry import REGISTRY

    assert find_data_licence_offenders(REGISTRY) == []


ENRON_LICENCE = 'None stated (CMU: "a resource for researchers"); real personal data'


def _enron(**changes: str) -> DemoManifest:
    fields = {
        "id": "enron",
        "distribution": "shipped",
        "delivery": "download",
        "seed_module": "scripts.seed_enron",
        "data_licence": ENRON_LICENCE,
    }
    return DemoManifest(**{**fields, **changes})  # type: ignore[arg-type]


def test_the_enron_download_as_recorded_is_not_flagged() -> None:
    """ADR-114 Amendment 23 point 7: each user downloads it; OspreyFlow never carries it."""
    assert find_data_licence_offenders((_enron(),)) == []


def test_enron_carried_rather_than_downloaded_is_flagged() -> None:
    assert find_data_licence_offenders((_enron(delivery="seed"),)) == [("enron", ENRON_LICENCE)]


def test_enron_with_its_licence_reworded_is_flagged() -> None:
    """A change to what is declared asks for a decision again, rather than passing on the name."""
    changed = "None stated"
    assert find_data_licence_offenders((_enron(data_licence=changed),)) == [("enron", changed)]


def test_another_download_with_no_stated_licence_is_flagged() -> None:
    """The exception is the one entry, not a rule for unlicensed data."""
    other = _enron(id="other-mail")
    assert find_data_licence_offenders((other,)) == [("other-mail", ENRON_LICENCE)]
