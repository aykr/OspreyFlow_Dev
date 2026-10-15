"""`recogniser_for_deployment` (ADR-108 phase D): a deployment built without the `extraction`
extra has no spaCy or transformers, and an extract stage asking for one must be refused in words,
not crash. The adapters import their libraries lazily, so it is the library that is looked for
(found when CI first ran the ingest tests without spaCy, 15 October 2026)."""

from __future__ import annotations

import importlib.util

import pytest
from services.api.pipeline_run import recogniser_for_deployment

STANZA = object()


def _without(monkeypatch: pytest.MonkeyPatch, *missing: str) -> None:
    real = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name, *a, **k: None if name in missing else real(name, *a, **k),
    )


@pytest.mark.parametrize("library", ["spacy", "transformers"])
def test_a_library_the_deployment_lacks_is_no_recogniser(
    monkeypatch: pytest.MonkeyPatch, library: str
) -> None:
    _without(monkeypatch, library)
    assert recogniser_for_deployment(STANZA)(library) is None  # type: ignore[arg-type]


def test_stanza_is_the_sidecar_and_an_unknown_name_is_none() -> None:
    get = recogniser_for_deployment(STANZA)  # type: ignore[arg-type]
    assert get("stanza") is STANZA
    assert get("nonesuch") is None
