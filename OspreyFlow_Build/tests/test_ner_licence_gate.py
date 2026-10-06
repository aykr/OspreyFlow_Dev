"""The recogniser image's licence gate (`services/ner/licence_gate.py`, ADR-098 decision 2): the
same rule as `make licence-check`, applied inside the image `make licence-check` cannot see. Each
case plants the shape the gate really receives from pip-licenses."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from tools import licence_check
from tools.layout import CORE

_spec = importlib.util.spec_from_file_location(
    "ner_licence_gate", CORE / "services/ner/licence_gate.py"
)
assert _spec and _spec.loader
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)


def _pkg(name: str, licence: str) -> dict[str, str]:
    return {"Name": name, "Version": "1", "License": licence}


def test_the_gates_allowlist_is_the_repositorys() -> None:
    assert gate.ALLOWED_MARKERS == licence_check.ALLOWED_MARKERS


def test_a_gpl_package_is_named_as_pip_licenses_5_5_reports_it() -> None:
    found = gate.offenders(
        [_pkg("udtools", "GPL-2.0-or-later"), _pkg("stanza", "Apache Software License")]
    )
    assert [p["Name"] for p in found] == ["udtools"]


def test_an_unreadable_licence_fails_rather_than_passing() -> None:
    """pip-licenses 5.0.0 reported udapi and udtools as UNKNOWN: default-deny must catch it."""
    assert [p["Name"] for p in gate.offenders([_pkg("udapi", "UNKNOWN")])] == ["udapi"]


def test_an_allowed_licence_joined_to_a_gpl_one_still_fails() -> None:
    assert gate.offenders([_pkg("mixed", "MIT AND GPL-3.0-or-later")])


def test_the_gates_own_tooling_is_not_judged() -> None:
    assert gate.offenders([_pkg("pip-licenses", "MIT"), _pkg("prettytable", "BSD")]) == []


def test_the_path_is_the_one_the_dockerfile_copies() -> None:
    dockerfile = (CORE / "services/ner/Dockerfile").read_text(encoding="utf-8")
    assert "COPY services/ner/licence_gate.py" in dockerfile
    assert "python licence_gate.py" in dockerfile
    assert Path(CORE / "services/ner/licence_gate.py").is_file()
