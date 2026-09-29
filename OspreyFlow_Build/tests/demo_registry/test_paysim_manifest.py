"""ADR-055 §3: PaySim is `internal`, and the packaging gate refuses its data even if someone flips
the entry to `shipped`."""

from __future__ import annotations

import dataclasses

from scripts.demo_registry import REGISTRY, internal_manifests, shipped_manifests

from tools import packaging_gate

_DATA = "OspreyFlow_Data/PaySIM_Dataset/PS_20174392719_1491204439457_log.csv"


def _paysim():  # type: ignore[no-untyped-def]
    return next(m for m in REGISTRY if m.id == "paysim")


def test_the_paysim_manifest_is_internal_and_names_its_data() -> None:
    manifest = _paysim()

    assert manifest.distribution == "internal"
    assert manifest in internal_manifests()
    assert manifest not in shipped_manifests()
    assert manifest.seed_module == "scripts.seed_paysim"
    assert _DATA in manifest.paths


def test_flipping_paysim_to_shipped_is_refused_while_its_data_is_in_the_bundle() -> None:
    flipped = dataclasses.replace(_paysim(), distribution="shipped")

    violations = packaging_gate.find_internal_demo_data([_DATA], registry=(flipped,))

    assert violations == [_DATA]
