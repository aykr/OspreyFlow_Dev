"""PL11's acceptance: the licence register for what the code gate does not see — model weights, map
data, fonts and base images — and the gate leg that holds the code to it.

`spec/LICENCE_REGISTER.yaml` has a row for each weight, map dataset, font family and image the code
names; `tools/licence_register.py` re-derives that list from the code and fails when the two part.
Rule 15: every refusal below is planted at the shape the code really reads — the real file's text
with one line added or changed — never a hand-written stand-in, and each is asserted by name, so a
fallthrough that refuses for another reason does not pass it.

**The folders this test walks** (the conductor's scan-map row): under `OspreyFlow_Core`, `harness/`
(its `*.py`), `services/` and `apps/` and `deploy/` (one `rglob` for `Dockerfile*`, `node_modules`
and `.venv` left out), `providers/` (`*.yaml`); and these named files: `osprey.yaml`,
`packages/schemas/deployment.py`, `packages/design/fonts.json`, `apps/workspace/package.json`,
`scripts/build_local_basemap.py`, `scripts/fetch_basemap_glyphs.py`, `services/ner/models.sha256`,
`services/laurium/requirements.txt`, `packages/adapters/recognise_spacy/adapter.py`,
`packages/adapters/recognise_transformers/adapter.py`. Under `OspreyFlow_Build`: `spec/` by name
(`LICENCE_REGISTER.yaml`) only.
"""

from __future__ import annotations

import copy
import importlib
import json
from typing import Any

import pytest
import yaml
from tools.layout import BUILD

REGISTER = BUILD / "spec" / "LICENCE_REGISTER.yaml"


@pytest.fixture(scope="module")
def reg() -> Any:
    return importlib.import_module("tools.licence_register")


@pytest.fixture(scope="module")
def rows(reg: Any) -> list[dict[str, Any]]:
    return reg.load_register()


@pytest.fixture
def sources(reg: Any) -> dict[str, str]:
    return dict(reg.read_sources())


def _violations(reg: Any, rows: list[dict[str, Any]], sources: dict[str, str]) -> list[str]:
    return reg.find_register_violations(rows, reg.named_by_code(sources))


def _row(rows: list[dict[str, Any]], name: str, pin: str | None = None) -> dict[str, Any]:
    return next(r for r in rows if r["name"] == name and (pin is None or r["pin"] == pin))


# --- the register exists, and the code agrees with it ---------------------------------------------


def test_the_register_is_one_file_in_the_specification() -> None:
    assert REGISTER.is_file(), "spec/LICENCE_REGISTER.yaml does not exist"


def test_every_kind_has_rows_and_every_row_has_every_column(
    reg: Any, rows: list[dict[str, Any]]
) -> None:
    assert {r["kind"] for r in rows} == {"weight", "map-data", "font", "image"}
    for row in rows:
        missing = [c for c in reg.COLUMNS if c not in row]
        assert not missing, f"{row.get('id')} lacks {missing}"
    assert len({r["id"] for r in rows}) == len(rows), "a row id is used twice"


def test_the_register_and_the_code_agree_today(reg: Any, rows: list[dict[str, Any]]) -> None:
    assert _violations(reg, rows, reg.read_sources()) == []


def test_the_code_names_what_the_scout_found_and_the_register_has_each(
    reg: Any, rows: list[dict[str, Any]]
) -> None:
    named = {(n.kind, n.name) for n in reg.named_by_code(reg.read_sources())}
    for expected in [
        ("weight", "qwen2.5:7b-instruct"),
        ("weight", "qwen2.5:0.5b-instruct"),
        ("weight", "all-minilm:22m-l6-v2-fp16"),
        ("weight", "moondream:1.8b-v2-q4_K_M"),
        ("weight", "Systran/faster-whisper-tiny.en"),
        ("weight", "stanza:en"),
        ("weight", "dslim/bert-base-NER"),
        ("weight", "en_core_web_sm"),
        ("font", "Atkinson Hyperlegible Next"),
        ("font", "GDS Transport"),
        ("map-data", "osm-local"),
        ("image", "arcadedata/arcadedb"),
        ("image", "eclipse-temurin"),
        ("image", "node"),
    ]:
        assert expected in named, f"the derivation does not see {expected}"
    held = reg.HELD_FOR_OWNER
    for kind, name in sorted(named):
        assert name in held or any(r["kind"] == kind and r["name"] == name for r in rows), name


def test_gds_transport_is_conditional_on_the_owners_ruling(rows: list[dict[str, Any]]) -> None:
    row = _row(rows, "GDS Transport")
    assert row["test"] == "restricted" and row["status"] == "conditional"
    assert row["ships"].startswith("only when appearance.govuk_identity is on")
    assert row["owner_ruling"] == "21 November 2026, not a sovereignty gap"
    assert row["note"], "the register must say today's build still holds the files"


def test_a_confirmed_row_passes_its_own_test_and_says_where_it_was_read(
    reg: Any, rows: list[dict[str, Any]]
) -> None:
    for row in rows:
        if row["status"] == "confirmed":
            assert reg.licence_passes(row["licence"], row["test"]), row["id"]
            assert row["where_read"].strip(), row["id"]


# --- the definition the register applies (the owner, 21 November 2026) ----------------------------


@pytest.mark.parametrize(
    ("licence", "test", "passes"),
    [
        ("Apache-2.0", "osi-weights", True),
        ("MIT", "osi-weights", True),
        ("GPL-2.0-only WITH Classpath-exception-2.0", "osi-software", True),
        ("PostgreSQL", "osi-software", True),
        ("OFL-1.1", "osi-software", True),
        # ODbL is not approved by the OSI, so it fails the software test and passes the data one.
        ("ODbL-1.0", "osi-software", False),
        ("ODbL-1.0", "open-data", True),
        ("OGL-UK-3.0", "open-data", True),
        # The owner's list for data is a recognised open-data licence, not any licence.
        ("CC-BY-NC-4.0", "open-data", False),
        ("Apache-2.0", "open-data", False),
        # A weights licence that is not OSI-approved fails, whatever it is called.
        ("CC-BY-NC-4.0", "osi-weights", False),
        ("Llama-3.1-Community", "osi-weights", False),
        ("LicenseRef-Proprietary", "osi-software", False),
        # `restricted` is the name of failing: nothing passes it.
        ("MIT", "restricted", False),
        # Each term of an AND must pass; one term of an OR is enough.
        ("MIT AND LicenseRef-Proprietary", "osi-software", False),
        ("MIT OR LicenseRef-Proprietary", "osi-software", True),
        ("Apache-2.0", "not-a-test", False),
    ],
)
def test_the_definition_is_applied_by_the_stated_test(
    reg: Any, licence: str, test: str, passes: bool
) -> None:
    assert reg.licence_passes(licence, test) is passes


# --- planted faults, each at the shape the code reads --------------------------------------------


def test_a_new_from_line_in_a_dockerfile_is_flagged(
    reg: Any, rows: list[dict[str, Any]], sources: dict[str, str]
) -> None:
    key = "services/ner/Dockerfile"
    sources[key] += "\nFROM alpine:3.21 AS extra\nRUN true\n"
    found = _violations(reg, rows, sources)
    assert any("alpine" in v and "not in the register" in v for v in found), found


def test_a_from_line_naming_an_earlier_stage_is_not_an_image(
    reg: Any, rows: list[dict[str, Any]], sources: dict[str, str]
) -> None:
    key = "services/ner/Dockerfile"
    sources[key] += "\nFROM python:3.12-slim AS again\nFROM again\nFROM runtime-${CONDUIT_JAVA}\n"
    assert _violations(reg, rows, sources) == []


def test_a_new_service_image_in_the_render_is_flagged(
    reg: Any, rows: list[dict[str, Any]], sources: dict[str, str]
) -> None:
    sources["harness/render.py"] += (
        "\n\ndef _more(images):\n"
        '    images.append(ServiceImage("newthing", "example/newthing:1.0"))\n'
    )
    found = _violations(reg, rows, sources)
    assert any("example/newthing" in v and "not in the register" in v for v in found), found


def test_a_new_image_constant_in_the_harness_is_flagged(
    reg: Any, rows: list[dict[str, Any]], sources: dict[str, str]
) -> None:
    sources["harness/cluster.py"] += '\nSIDECAR_IMAGE = "example/sidecar:2.0"\n'
    found = _violations(reg, rows, sources)
    assert any("example/sidecar" in v and "not in the register" in v for v in found), found


def test_a_new_pulled_model_is_flagged(
    reg: Any, rows: list[dict[str, Any]], sources: dict[str, str]
) -> None:
    text = sources["harness/render.py"]
    line = next(ln for ln in text.splitlines() if "pull_and_verify moondream" in ln)
    planted = line.replace("moondream:1.8b-v2-q4_K_M c865c80afc38", "newmodel:3b 0123456789ab")
    assert planted != line
    sources["harness/render.py"] = text.replace(line, line + "\n" + planted, 1)
    found = _violations(reg, rows, sources)
    assert any("newmodel:3b" in v and "not in the register" in v for v in found), found


def test_a_new_model_in_a_closed_model_list_is_flagged(
    reg: Any, rows: list[dict[str, Any]], sources: dict[str, str]
) -> None:
    key = "packages/schemas/deployment.py"
    sources[key] = sources[key].replace(
        '"qwen2.5:14b-instruct": "7cdf5a0187d5",',
        '"qwen2.5:14b-instruct": "7cdf5a0187d5",\n    "newmodel:72b": "feedfacecafe",',
        1,
    )
    found = _violations(reg, rows, sources)
    assert any("newmodel:72b" in v and "not in the register" in v for v in found), found


def test_a_new_font_family_in_fonts_json_is_flagged(
    reg: Any, rows: list[dict[str, Any]], sources: dict[str, str]
) -> None:
    key = "packages/design/fonts.json"
    document = json.loads(sources[key])
    document["fonts"].append(
        {"family": "Comic Neue", "role": "ui", "source": "@fontsource/comic-neue",
         "weights": [400], "licence": "OFL-1.1"}
    )  # fmt: skip
    sources[key] = json.dumps(document, indent=2)
    found = _violations(reg, rows, sources)
    assert any("Comic Neue" in v and "not in the register" in v for v in found), found


def test_a_new_map_entry_in_osprey_yaml_is_flagged(
    reg: Any, rows: list[dict[str, Any]], sources: dict[str, str]
) -> None:
    document = yaml.safe_load(sources["osprey.yaml"])
    document["map"]["providers"].append(
        {"id": "osm-extra", "label": "Extra", "kind": "vector",
         "licence": {"id": "ODbL", "redistributable": True, "client_scope": "open"},
         "source": "file:///data/tiles/extra.pmtiles"}
    )  # fmt: skip
    sources["osprey.yaml"] = yaml.safe_dump(document)
    found = _violations(reg, rows, sources)
    assert any("osm-extra" in v and "not in the register" in v for v in found), found


def test_a_new_provider_file_is_flagged(
    reg: Any, rows: list[dict[str, Any]], sources: dict[str, str]
) -> None:
    sources["providers/new-basemap.yaml"] = "id: new-basemap\nlicence:\n  id: OGL-UK-3.0\n"
    found = _violations(reg, rows, sources)
    assert any("new-basemap" in v and "not in the register" in v for v in found), found


def test_a_new_region_in_the_basemap_build_is_flagged(
    reg: Any, rows: list[dict[str, Any]], sources: dict[str, str]
) -> None:
    key = "scripts/build_local_basemap.py"
    text = sources[key]
    sources[key] = text.replace(
        '    "texas": "https://download.geofabrik.de/north-america/us/texas-latest.osm.pbf",',
        '    "texas": "https://download.geofabrik.de/north-america/us/texas-latest.osm.pbf",\n'
        '    "iceland": "https://download.geofabrik.de/europe/iceland-latest.osm.pbf",',
        1,
    )
    assert sources[key] != text
    found = _violations(reg, rows, sources)
    assert any("osm-local-iceland" in v and "not in the register" in v for v in found), found


def test_a_changed_image_digest_is_a_pin_that_differs(
    reg: Any, rows: list[dict[str, Any]], sources: dict[str, str]
) -> None:
    key = "services/api/Dockerfile"
    text = sources[key]
    changed = text.replace("@sha256:ebfbb18d11ff", "@sha256:000000000000", 1)
    assert changed != text
    sources[key] = changed
    found = _violations(reg, rows, sources)
    assert any(
        "eclipse-temurin" in v and "pin differs" in v and "000000000000" in v for v in found
    ), found
    assert not any("not in the register" in v and "eclipse-temurin" in v for v in found), found


def test_a_changed_image_tag_in_the_render_is_a_pin_that_differs(
    reg: Any, rows: list[dict[str, Any]], sources: dict[str, str]
) -> None:
    text = sources["harness/render.py"]
    sources["harness/render.py"] = text.replace("valkey/valkey:8.0", "valkey/valkey:9.0", 1)
    found = _violations(reg, rows, sources)
    assert any("valkey/valkey" in v and "pin differs" in v and "9.0" in v for v in found), found


def test_a_changed_manifest_id_in_the_pull_script_is_a_pin_that_differs(
    reg: Any, rows: list[dict[str, Any]], sources: dict[str, str]
) -> None:
    text = sources["harness/render.py"]
    old = "pull_and_verify qwen2.5:0.5b-instruct a8b0c5157701"
    changed = text.replace(old, "pull_and_verify qwen2.5:0.5b-instruct ffffffffffff")
    assert changed != text
    sources["harness/render.py"] = changed
    found = _violations(reg, rows, sources)
    assert any(
        "0.5b-instruct" in v and "pin differs" in v and "ffffffffffff" in v for v in found
    ), found


def test_a_pull_script_and_a_closed_list_that_disagree_on_a_pin_are_flagged(
    reg: Any, rows: list[dict[str, Any]], sources: dict[str, str]
) -> None:
    """The embeddings model is named twice (the pull script and `EMBEDDING_MODELS`): change one and
    the code names two pins for it, and the register can hold only one of them."""
    text = sources["harness/render.py"]
    old = "pull_and_verify all-minilm:22m-l6-v2-fp16 1b226e2802db"
    changed = text.replace(old, "pull_and_verify all-minilm:22m-l6-v2-fp16 ffffffffffff")
    assert changed != text
    sources["harness/render.py"] = changed
    found = _violations(reg, rows, sources)
    assert any(
        "all-minilm" in v and "ffffffffffff" in v and "not in the register" in v for v in found
    ), found


def test_a_changed_stanza_model_pin_file_is_a_pin_that_differs(
    reg: Any, rows: list[dict[str, Any]], sources: dict[str, str]
) -> None:
    sources["services/ner/models.sha256"] += "0" * 64 + "  en/extra/extra.pt\n"
    found = _violations(reg, rows, sources)
    assert any("stanza:en" in v and "pin differs" in v for v in found), found


def test_a_row_the_code_no_longer_names_is_flagged(
    reg: Any, rows: list[dict[str, Any]], sources: dict[str, str]
) -> None:
    sources["packages/design/fonts.json"] = json.dumps(
        {"fonts": [f for f in json.loads(sources["packages/design/fonts.json"])["fonts"]
                   if f["family"] != "IBM Plex Mono"]}
    )  # fmt: skip
    found = _violations(reg, rows, sources)
    assert any("IBM Plex Mono" in v and "no code names" in v for v in found), found


def test_a_confirmed_row_with_no_where_read_is_flagged(
    reg: Any, rows: list[dict[str, Any]], sources: dict[str, str]
) -> None:
    broken = copy.deepcopy(rows)
    _row(broken, "qwen2.5:0.5b-instruct")["where_read"] = " "
    found = _violations(reg, broken, sources)
    assert any("qwen2.5:0.5b-instruct" in v and "where it was read" in v for v in found), found


def test_a_conditional_row_with_no_owner_ruling_is_flagged(
    reg: Any, rows: list[dict[str, Any]], sources: dict[str, str]
) -> None:
    broken = copy.deepcopy(rows)
    _row(broken, "GDS Transport").pop("owner_ruling")
    found = _violations(reg, broken, sources)
    assert any("GDS Transport" in v and "owner ruling" in v for v in found), found


def test_a_restricted_row_that_is_not_conditional_is_flagged(
    reg: Any, rows: list[dict[str, Any]], sources: dict[str, str]
) -> None:
    broken = copy.deepcopy(rows)
    _row(broken, "GDS Transport")["status"] = "confirmed"
    found = _violations(reg, broken, sources)
    assert any("GDS Transport" in v and "fails the definition" in v for v in found), found


def test_a_licence_that_does_not_pass_its_stated_test_is_flagged(
    reg: Any, rows: list[dict[str, Any]], sources: dict[str, str]
) -> None:
    broken = copy.deepcopy(rows)
    _row(broken, "moondream:1.8b-v2-q4_K_M")["licence"] = "CC-BY-NC-4.0"
    _row(broken, "valkey/valkey")["licence"] = "ODbL-1.0"
    found = _violations(reg, broken, sources)
    assert any("moondream" in v and "does not pass" in v and "osi-weights" in v for v in found)
    assert any("valkey/valkey" in v and "does not pass" in v and "osi-software" in v for v in found)


def test_a_test_that_is_not_one_of_the_four_is_flagged(
    reg: Any, rows: list[dict[str, Any]], sources: dict[str, str]
) -> None:
    broken = copy.deepcopy(rows)
    _row(broken, "qwen2.5:7b-instruct")["test"] = "looks-fine"
    found = _violations(reg, broken, sources)
    assert any("qwen2.5:7b-instruct" in v and "looks-fine" in v and "one of" in v for v in found)


def test_an_unconfirmed_row_may_not_state_a_licence_and_must_say_what_to_read(
    reg: Any, rows: list[dict[str, Any]], sources: dict[str, str]
) -> None:
    broken = copy.deepcopy(rows)
    row = _row(broken, "qwen2.5:0.5b-instruct")
    row["status"] = "unconfirmed"
    found = _violations(reg, broken, sources)
    assert any(
        "qwen2.5:0.5b-instruct" in v and "unconfirmed" in v and "licence" in v for v in found
    )
    assert any("qwen2.5:0.5b-instruct" in v and "must_read" in v for v in found)


def test_a_name_held_for_the_owner_that_is_also_registered_is_flagged(
    reg: Any, rows: list[dict[str, Any]], sources: dict[str, str]
) -> None:
    found = reg.find_register_violations(
        rows, reg.named_by_code(sources), held=frozenset({"valkey/valkey"})
    )
    assert any(
        "valkey/valkey" in v and "held for the owner" in v and "registered" in v for v in found
    )


def test_a_held_name_the_code_names_is_not_a_missing_row_but_the_release_refuses(
    reg: Any, rows: list[dict[str, Any]], sources: dict[str, str]
) -> None:
    held = frozenset({"ghcr.io/berriai/litellm"})
    assert held <= reg.HELD_FOR_OWNER
    assert not any(r["name"] in held for r in rows), "a held row is not registered"
    assert reg.find_register_violations(rows, reg.named_by_code(sources), held=held) == []
    # Without the hold the same code and register fail: the name is named and not registered.
    found = reg.find_register_violations(rows, reg.named_by_code(sources), held=frozenset())
    assert any("ghcr.io/berriai/litellm" in v and "not in the register" in v for v in found)


def test_the_gate_leg_reaches_main_and_main_fails_naming_a_planted_image(
    reg: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`python -m tools.licence_check` is what `make licence-check` and ci.yml run: plant a new
    `FROM` in the sources the leg reads and the run exits 1 and names it, where with the real
    sources it exits 0 (the other legs are given no packages so only this one can fail)."""
    from tools import licence_check

    monkeypatch.setattr(licence_check, "run_pip_licenses", lambda extra: [])
    monkeypatch.setattr("sys.argv", ["licence_check"])
    assert licence_check.main() == 0
    assert "the licence register agrees with the code" in capsys.readouterr().out

    real = reg.read_sources()
    planted = {
        **real,
        "services/ner/Dockerfile": real["services/ner/Dockerfile"] + "\nFROM alpine:3.21\n",
    }
    monkeypatch.setattr(reg, "read_sources", lambda *a, **k: planted)
    assert licence_check.main() == 1
    assert "alpine" in capsys.readouterr().err


def test_the_python_allowlist_reads_the_two_spellings_the_specification_allows() -> None:
    from tools import licence_check

    assert licence_check.is_allowed("OFL-1.1") and licence_check.is_allowed("Python-2.0")
