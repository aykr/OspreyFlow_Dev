"""ADR-053 point 4: the Enron corpus is `internal`, and the packaging gate refuses anything under
its folder even if someone flips the entry to `shipped`."""

from __future__ import annotations

import dataclasses

from scripts.demo_registry import REGISTRY, internal_manifests, shipped_manifests

from tools import packaging_gate

_FOLDER = "OspreyFlow_Data/Enron_Mails"
_A_MAILBOX_FILE = f"{_FOLDER}/allen-p/inbox/1."


def _enron():  # type: ignore[no-untyped-def]
    return next(m for m in REGISTRY if m.id == "enron")


def test_the_enron_manifest_is_internal_and_names_its_folder() -> None:
    manifest = _enron()
    assert manifest.distribution == "internal"
    assert manifest in internal_manifests()
    assert manifest not in shipped_manifests()
    assert manifest.seed_module == "scripts.seed_enron"
    assert _FOLDER in manifest.paths


def test_a_mail_file_in_an_artefact_is_refused() -> None:
    assert packaging_gate.find_internal_demo_data([_A_MAILBOX_FILE]) == [_A_MAILBOX_FILE]


def test_flipping_enron_to_shipped_is_still_refused_while_the_mail_is_in_the_bundle() -> None:
    flipped = dataclasses.replace(_enron(), distribution="shipped")
    violations = packaging_gate.find_internal_demo_data([_A_MAILBOX_FILE], registry=(flipped,))
    assert violations == [_A_MAILBOX_FILE]
