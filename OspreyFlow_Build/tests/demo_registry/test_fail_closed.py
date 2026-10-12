"""`06_DECISIONS.md` ADR-035 §C1: "The registry fails closed... The test that proves this."
Named prospectively in that record; built here against the real `scripts/demo_registry.py`.
"""

from __future__ import annotations

from scripts.demo_registry import (
    REGISTRY,
    DemoManifest,
    internal_manifests,
    shipped_manifests,
)

from tools import packaging_gate


def test_a_manifest_with_no_distribution_field_is_excluded_from_a_shipped_build() -> None:
    """A manifest literally lacking the field — `from_dict` on a raw dict with no `distribution`
    key at all, not one explicitly set to `"internal"` — must not appear in a shipped-build
    listing."""
    manifest = DemoManifest.from_dict({"id": "no-distribution-field", "seed_module": "x"})

    assert manifest.distribution == ""
    assert manifest.is_shipped is False
    assert manifest not in shipped_manifests((manifest,))
    assert manifest in internal_manifests((manifest,))


def test_an_unrecognised_distribution_value_is_treated_as_internal() -> None:
    """A different code path from the missing-field case above (a present-but-wrong value, not an
    absent key) — each needs its own proof, per this ADR's own text."""
    for bad_value in ("Shipped", "SHIPPED", "shiped", "public", ""):
        manifest = DemoManifest(id="x", distribution=bad_value, seed_module="x")
        assert manifest.is_shipped is False, f"{bad_value!r} was wrongly treated as shipped"


def test_a_correctly_spelled_shipped_manifest_is_included() -> None:
    """The positive case beside the two refusals above — a registry that failed everything closed
    including the correct spelling would pass the tests above vacuously."""
    manifest = DemoManifest(id="x", distribution="shipped", seed_module="x")
    assert manifest.is_shipped is True
    assert manifest in shipped_manifests((manifest,))


def test_the_real_registry_holds_exactly_the_datasets_it_is_known_to_hold() -> None:
    """Checked directly, not assumed. Four shipped demos (`hmp`, `fixture-corp`,
    `operation-ledger`, and `paysim` as a download, ADR-114 Amendment 1) and no internal one: the
    Enron corpus (ADR-053) is registered beside its code in the developer repository (ADR-114
    Amendment 2), and the gates judge against both. Adding a dataset must change this test, so a
    registry entry can never appear unnoticed."""
    assert {m.id for m in shipped_manifests(REGISTRY)} == {
        "hmp",
        "fixture-corp",
        "operation-ledger",
        "paysim",
    }
    assert {m.id for m in internal_manifests(REGISTRY)} == set()
    from internal_demos.registry import ALL

    assert {m.id for m in internal_manifests(ALL)} == {"enron"}


def test_a_misspelled_or_missing_delivery_is_not_seeded_and_its_data_is_refused() -> None:
    """ADR-114 Amendment 1 decision 1: `delivery` fails closed as `distribution` does. A shipped
    manifest whose delivery is misspelt, empty or absent is not seeded, so the gate refuses its
    data rather than letting it into a bundle."""
    path = "packages/demo_fixtures/x.csv"
    from_dict = DemoManifest.from_dict(
        {"id": "x", "distribution": "shipped", "seed_module": "x", "paths": [path]}
    )
    assert from_dict.delivery == ""
    candidates = [
        from_dict,
        DemoManifest(
            id="x", distribution="shipped", seed_module="x", delivery="Seed", paths=(path,)
        ),
        DemoManifest(id="x", distribution="shipped", seed_module="x", delivery="", paths=(path,)),
    ]
    for manifest in candidates:
        assert manifest.is_seeded is False
        assert packaging_gate.find_internal_demo_data([path], registry=(manifest,)) == [path]
    seeded = DemoManifest(
        id="x", distribution="shipped", seed_module="x", delivery="seed", paths=(path,)
    )
    assert seeded.is_seeded is True
    assert packaging_gate.find_internal_demo_data([path], registry=(seeded,)) == []
