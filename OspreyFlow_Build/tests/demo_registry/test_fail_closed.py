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
    """Checked directly, not assumed. Two shipped, synthetic, generated demos (`hmp`,
    `fixture-corp`), and the internal ones the owner has ruled on: PaySim (ADR-055). Neither the
    Enron corpus nor the VAST-shaped fixture is registered yet. Adding a dataset must change this
    test, so a registry entry can never appear unnoticed."""
    assert {m.id for m in shipped_manifests(REGISTRY)} == {"hmp", "fixture-corp"}
    assert {m.id for m in internal_manifests(REGISTRY)} == {"paysim"}
