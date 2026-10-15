"""ADR-114 Amendment 23 (amending ADR-053 point 4): the Enron corpus is a `shipped` *download* — real
data, fetched by each user from CMU and accepted on their machine — so its code ships with the product,
and its mail is refused in every artefact as any download pack's data is, even if its entry is ever
changed to say otherwise."""

from __future__ import annotations

import dataclasses

from scripts.demo_registry import DELIVERY_DOWNLOAD, REGISTRY, shipped_manifests
from tools import packaging_gate

_FOLDER = "OspreyFlow_Data/Enron_Mails"
_A_MAILBOX_FILE = f"{_FOLDER}/allen-p/inbox/1."


def _enron():  # type: ignore[no-untyped-def]
    return next(m for m in REGISTRY if m.id == "enron")


def test_the_enron_manifest_is_a_shipped_download_that_names_its_folder() -> None:
    manifest = _enron()
    assert manifest in shipped_manifests(REGISTRY)
    assert manifest.delivery == DELIVERY_DOWNLOAD
    assert manifest.seed_module == "scripts.seed_enron"
    assert _FOLDER in manifest.paths
    assert "real personal data" in (manifest.data_licence or "")


def test_the_enron_code_ships_with_the_product() -> None:
    code = ["scripts/seed_enron.py", "scripts/enron_mail.py", "scripts/real_data_acknowledgement.py"]
    assert packaging_gate.find_internal_demo_data(code) == []


def test_a_mail_file_in_an_artefact_is_refused() -> None:
    assert packaging_gate.find_internal_demo_data([_A_MAILBOX_FILE]) == [_A_MAILBOX_FILE]


def test_marking_enron_as_seeded_by_mistake_still_refuses_its_mail() -> None:
    flipped = dataclasses.replace(_enron(), delivery="seed")
    violations = packaging_gate.find_internal_demo_data([_A_MAILBOX_FILE], registry=(flipped,))
    assert violations == [_A_MAILBOX_FILE]
