"""The pins the register records for what the product fetches at run time, and the code that reads
or checks each (PL11 item 2b; the owner's word of 21 November 2026).

Each of these was fetched with no pin: the Whisper weights followed the Hub's `main`, the
recogniser's `dslim/bert-base-NER` followed it too, the Stanza models were hash-checked but the hash
file was not in the register, and planetiler's own downloads were named nowhere. What the code can
read or check, it does; what happens inside a third-party tool, the register records and a test here
holds the record to the code's constant. **What remains unpinned, and why, is in the report and in
the register's `ships` column**: planetiler's fetches (inside its jar), the water polygons' hash
(the file is republished every few days), and `-latest` extracts of OpenStreetMap (data, with no
revision).

**The folders this test walks:** none. It reads named files under `OspreyFlow_Core` and the
register.
"""

from __future__ import annotations

import hashlib
import re
import sys
import types
import warnings
from pathlib import Path
from typing import Any

import pytest
from harness.render import _whisper_download_script
from tools import licence_register
from tools.layout import CORE

from schemas.deployment import TRANSCRIPTION_MODEL_REVISIONS, TRANSCRIPTION_MODELS

WHISPER = "Systran/faster-whisper-tiny.en"


def _pin(name: str, kind: str | None = None) -> str:
    rows = [
        r
        for r in licence_register.load_register()
        if r["name"] == name and (kind is None or r["kind"] == kind)
    ]
    assert len(rows) == 1, f"{name!r} should have exactly one row, has {len(rows)}"
    return str(rows[0]["pin"])


# --- Whisper -------------------------------------------------------------------------------------


def test_every_transcription_model_has_a_revision_and_the_register_names_it() -> None:
    assert set(TRANSCRIPTION_MODELS) == set(TRANSCRIPTION_MODEL_REVISIONS)
    for model, revision in TRANSCRIPTION_MODEL_REVISIONS.items():
        assert re.fullmatch(r"[0-9a-f]{40}", revision), (model, revision)
        assert _pin(model, "weight") == revision


def test_the_rendered_speech_job_requires_the_registered_revision() -> None:
    script = _whisper_download_script(WHISPER)
    revision = _pin(WHISPER, "weight")
    assert f'[ "$$(basename "$$snapshot")" = {revision} ] || return 1' in script
    assert f"version {revision}" in script, "the refusal must name the revision it wanted"


def test_the_adrs_commit_is_the_one_in_the_code() -> None:
    """The decision log names the same commit (Stage 2 addendum): a change to one is a change to
    both."""
    log = (CORE.parent / "OspreyFlow_Build" / "spec" / "06_DECISIONS.md").read_text(
        encoding="utf-8"
    )
    assert TRANSCRIPTION_MODEL_REVISIONS[WHISPER] in log


# --- Stanza --------------------------------------------------------------------------------------


def test_the_stanza_pin_is_the_hash_of_the_file_the_build_checks_every_download_against() -> None:
    models = (CORE / "services/ner/models.sha256").read_bytes()
    assert _pin("stanza:en", "weight") == "sha256:" + hashlib.sha256(models).hexdigest()
    dockerfile = (CORE / "services/ner/Dockerfile").read_text(encoding="utf-8")
    assert "sha256sum -c --strict /tmp/models.sha256" in dockerfile
    assert "COPY services/ner/models.sha256 /tmp/models.sha256" in dockerfile
    assert len(models.decode().splitlines()) == 7, (
        "the pin file lists seven files, and the build counts them"
    )


# --- the transformers recogniser ----------------------------------------------------------------


@pytest.fixture
def fake_transformers(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """A `transformers` that records how `pipeline` was called, standing in for the real one
    (which would fetch weights); the adapter imports it inside `_load`."""
    calls: list[dict[str, Any]] = []

    def pipeline(task: str, **kwargs: Any) -> object:
        calls.append({"task": task, **kwargs})
        return object()

    module = types.ModuleType("transformers")
    module.pipeline = pipeline  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "transformers", module)
    return calls


def test_the_default_model_is_loaded_at_the_registered_revision(
    fake_transformers: list[dict[str, Any]],
) -> None:
    from adapters.recognise_transformers.adapter import RecogniseTransformersAdapter

    RecogniseTransformersAdapter()._load()
    assert fake_transformers == [
        {
            "task": "token-classification",
            "model": "dslim/bert-base-NER",
            "revision": _pin("dslim/bert-base-NER", "weight"),
            "aggregation_strategy": "simple",
        }
    ]


def test_another_model_is_not_given_the_default_models_revision(
    fake_transformers: list[dict[str, Any]],
) -> None:
    from adapters.recognise_transformers.adapter import RecogniseTransformersAdapter

    RecogniseTransformersAdapter(model_name="someone/else-NER")._load()
    assert fake_transformers[0]["revision"] is None
    RecogniseTransformersAdapter(model_name="someone/else-NER", revision="abc123")._load()
    assert fake_transformers[1]["revision"] == "abc123"


# --- planetiler ----------------------------------------------------------------------------------


def test_the_planetiler_pin_in_the_code_is_the_registers() -> None:
    from scripts import build_local_basemap as basemap

    pin = basemap.PLANETILER_PIN
    assert _pin("planetiler", "map-data") == f"{pin['version']} sha256:{pin['sha256']}"
    for key, entry in basemap.PLANETILER_SOURCES.items():
        assert _pin(f"planetiler:{key}", "map-data") == f"sha256:{entry['sha256']}"
        assert re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])
        assert entry["url"].startswith("https://")


def test_a_jar_is_the_pinned_release_only_if_it_hashes_to_the_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts import build_local_basemap as basemap

    jar = tmp_path / "planetiler.jar"
    jar.write_bytes(b"a jar")
    assert basemap.jar_is_the_pinned_release(jar) is False
    monkeypatch.setattr(
        basemap, "PLANETILER_PIN", {"version": "vX", "sha256": hashlib.sha256(b"a jar").hexdigest()}
    )
    assert basemap.jar_is_the_pinned_release(jar) is True


def test_a_jar_that_is_not_the_pinned_release_is_warned_about_and_the_build_goes_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts import build_local_basemap as basemap

    jar = tmp_path / "planetiler.jar"
    jar.write_bytes(b"another release")
    ran: list[list[str]] = []

    def fake_run(command: list[str], **_: object) -> object:
        ran.append(command)
        return object()

    with pytest.warns(UserWarning, match="not planetiler v0.10.2"):
        basemap.run_planetiler(
            tmp_path / "x.osm.pbf",
            tmp_path / "out" / "x.pmtiles",
            jar_path=jar,
            subprocess_run=fake_run,
        )  # type: ignore[arg-type]
    assert any("--download" in command for command in ran), (
        "a different jar still runs: it is warned about, not refused"
    )

    monkeypatch.setattr(
        basemap,
        "PLANETILER_PIN",
        {"version": "vX", "sha256": hashlib.sha256(b"another release").hexdigest()},
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        basemap.run_planetiler(
            tmp_path / "x.osm.pbf",
            tmp_path / "out" / "x.pmtiles",
            jar_path=jar,
            subprocess_run=fake_run,
        )  # type: ignore[arg-type]
