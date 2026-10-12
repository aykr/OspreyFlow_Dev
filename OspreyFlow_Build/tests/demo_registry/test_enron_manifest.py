"""ADR-053 point 4: the Enron corpus is `internal`, and the packaging gate refuses anything under
its folder even if someone flips the entry to `shipped`. Its entry is registered beside its code in
the developer repository, not in the product's registry (ADR-114 Amendment 2)."""

from __future__ import annotations

import dataclasses

from internal_demos.registry import ALL as REGISTRY
from scripts.demo_registry import REGISTRY as PRODUCT_REGISTRY
from scripts.demo_registry import internal_manifests, shipped_manifests

from tools import packaging_gate

_FOLDER = "OspreyFlow_Data/Enron_Mails"
_A_MAILBOX_FILE = f"{_FOLDER}/allen-p/inbox/1."


def _enron():  # type: ignore[no-untyped-def]
    return next(m for m in REGISTRY if m.id == "enron")


def test_the_enron_manifest_is_internal_and_names_its_folder() -> None:
    manifest = _enron()
    assert manifest.distribution == "internal"
    assert manifest in internal_manifests(REGISTRY)
    assert manifest not in shipped_manifests(REGISTRY)
    assert manifest.seed_module == "internal_demos.seed_enron"
    assert _FOLDER in manifest.paths
    assert "enron" not in {m.id for m in PRODUCT_REGISTRY}, "never in the product's own registry"


def test_the_enron_code_is_refused_in_an_artefact_wherever_it_sits() -> None:
    """Its reader and seed, at their place here and at the places they used to have in the product
    folder, so a copy put back there is refused too."""
    code = ["internal_demos/seed_enron.py", "internal_demos/enron.py", "scripts/seed_enron.py",
            "packages/demo_fixtures/enron.py"]  # fmt: skip
    assert packaging_gate.find_internal_demo_data(code) == code


def test_a_mail_file_in_an_artefact_is_refused() -> None:
    assert packaging_gate.find_internal_demo_data([_A_MAILBOX_FILE]) == [_A_MAILBOX_FILE]


def test_flipping_enron_to_shipped_is_still_refused_while_the_mail_is_in_the_bundle() -> None:
    flipped = dataclasses.replace(_enron(), distribution="shipped")
    violations = packaging_gate.find_internal_demo_data([_A_MAILBOX_FILE], registry=(flipped,))
    assert violations == [_A_MAILBOX_FILE]
