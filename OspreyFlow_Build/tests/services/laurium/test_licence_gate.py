"""Laurium's image licence gate (`services/laurium/licence_gate.py`, ADR-135 Amendment 6 decisions 2
and 7): the repository's rule, inside the image `make licence-check` cannot see, with the recorded
evidence for Laurium's three packages, and a refusal of the `encoder` extra's packages whatever their
licence. Each plant is the row pip-licenses gives it at image build (`main`'s own call)."""

from __future__ import annotations

import importlib.util

import pytest
from tools import licence_check
from tools.layout import CORE

_spec = importlib.util.spec_from_file_location(
    "laurium_licence_gate", CORE / "services/laurium/licence_gate.py"
)
assert _spec and _spec.loader
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)


def _row(name: str, licence: str, version: str = "1") -> dict[str, str]:
    return {"Name": name, "Version": version, "License": licence}


def test_the_allowlist_and_exceptions_are_the_repositorys() -> None:
    assert gate.ALLOWED_MARKERS == licence_check.ALLOWED_MARKERS
    assert gate.RECORDED_LGPL_EXCEPTIONS == licence_check.RECORDED_LGPL_EXCEPTIONS
    assert gate.RECORDED_LICENCE_EVIDENCE == licence_check.RECORDED_LICENCE_EVIDENCE


@pytest.mark.parametrize(
    "row",
    [
        _row("laurium", "UNKNOWN", "0.6.0"),
        _row("arrow_pd_parser", "UNKNOWN", "2.2.0"),
        _row("tiktoken", "MIT License\n\nCopyright (c) 2022 OpenAI, and/or others", "0.14.0"),
        _row("laurium", "GPL-3.0", "0.6.0"),
        _row("laurium", "UNKNOWN", "0.7.0"),
        _row("udapi", "UNKNOWN"),
        _row("mixed", "MIT AND GPL-3.0-or-later"),
        _row("spacy", "MIT"),
        _row("en-core-web-sm", "MIT", "3.8.0"),
    ],
    ids=lambda r: f"{r['Name']}-{r['Version']}-{r['License'][:12]}",
)
def test_the_image_gate_judges_every_row_as_the_repositorys_gate(row: dict[str, str]) -> None:
    assert (gate.offenders([row]) == []) == (licence_check.find_offenders([row]) == [])


@pytest.mark.parametrize(
    "name",
    ["torch", "transformers", "setfit", "sentence-transformers", "nvidia-cublas-cu12", "nvidia_cudnn_cu12"],
)
def test_an_encoder_package_fails_whatever_its_licence(name: str) -> None:
    """The owner's ruling 4: the `encoder` extra is never installed. torch is BSD and transformers
    Apache, so the allowlist alone would pass them; their presence is the fault."""
    found = gate.offenders([_row(name, "BSD-3-Clause")])
    assert [p["Name"] for p in found] == [name]


def test_the_gates_own_tooling_is_not_judged() -> None:
    assert gate.offenders([_row("pip-licenses", "MIT"), _row("prettytable", "BSD")]) == []


def test_the_dockerfile_runs_this_gate() -> None:
    dockerfile = (CORE / "services/laurium/Dockerfile").read_text(encoding="utf-8")
    assert "COPY licence_gate.py" in dockerfile
    assert "python licence_gate.py" in dockerfile
