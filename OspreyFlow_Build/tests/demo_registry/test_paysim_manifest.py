"""ADR-114 Amendment 1 (superseding ADR-055 §3's `internal`): PaySim is `shipped` as a download,
under CC-BY-SA-4.0, and the packaging gate still refuses its data inside any artefact."""

from __future__ import annotations

from scripts.demo_registry import (
    REGISTRY,
    downloaded_manifests,
    internal_manifests,
    shipped_manifests,
)
from tools import packaging_gate

_DATA = "OspreyFlow_Data/PaySIM_Dataset/PS_20174392719_1491204439457_log.csv"


def _paysim():  # type: ignore[no-untyped-def]
    return next(m for m in REGISTRY if m.id == "paysim")


def test_the_paysim_manifest_is_a_shipped_download_and_names_its_data() -> None:
    manifest = _paysim()

    assert manifest.distribution == "shipped"
    assert manifest.delivery == "download"
    assert manifest.data_licence == "CC-BY-SA-4.0"
    assert manifest in shipped_manifests()
    assert manifest in downloaded_manifests()
    assert manifest not in internal_manifests()
    assert manifest.seed_module == "scripts.seed_paysim"
    assert _DATA in manifest.paths


def test_paysim_data_is_refused_inside_an_artefact_although_shipped() -> None:
    """Shipped as a download means the gate must still keep the file out of every bundle."""
    violations = packaging_gate.find_internal_demo_data([_DATA], registry=REGISTRY)

    assert violations == [_DATA]
