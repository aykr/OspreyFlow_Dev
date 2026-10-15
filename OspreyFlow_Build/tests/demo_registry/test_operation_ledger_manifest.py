"""ADR-114 Amendment 1: Operation Ledger is a shipped, seeded demo, so its code and synthetic
files travel in the artefact and the packaging gate must not refuse them."""

from __future__ import annotations

from scripts.demo_registry import REGISTRY, seeded_manifests
from tools import packaging_gate


def _ledger():  # type: ignore[no-untyped-def]
    return next(m for m in REGISTRY if m.id == "operation-ledger")


def test_operation_ledger_is_shipped_and_seeded() -> None:
    manifest = _ledger()

    assert manifest.is_shipped
    assert manifest.is_seeded
    assert manifest in seeded_manifests()
    assert manifest.seed_module == "scripts.seed_ledger_fixture"
    assert manifest.paths == (
        "packages/demo_fixtures/ledger.py",
        "packages/demo_fixtures/ledger_onboarding_applications.csv",
        "packages/demo_fixtures/screening_list_synthetic.yaml",
    )


def test_operation_ledger_paths_are_not_refused_by_the_gate() -> None:
    """A seeded demo's own files must pass, or the gate would block a legitimate bundle."""
    assert packaging_gate.find_internal_demo_data(list(_ledger().paths), registry=REGISTRY) == []
