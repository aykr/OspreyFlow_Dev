"""The client-size synthetic dataset's generator (ROUTE_052 step B, `v052-load`;
`process/lanes/rules/v052-load/DESIGN.md`).

Offline and tiny: the set is written at `--scale 0.0005 --graph-scale 0.02` (about 13,000 nodes,
50,000 analytics rows) into a temporary folder. What would fail if each promise broke (rule 12):
the same seed writing other bytes; a source, a marking or a plant going missing; the big source not
growing with `--scale`; a link to a node the set never writes (the bulk loader refuses it); a
record the ontology refuses; a link written by two files (which would break the loader's resume
rule); a real-looking identifier.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from scripts import client_size_plan as plan
from scripts import generate_client_size as gen

from demo_fixtures.pid_names import STAFF_NAMES, SURNAMES
from ontology.packs import load_deployment_ontology
from ontology.validation import validate_edge_endpoints, validate_properties

SCALE = 0.0005
GRAPH_SCALE = 0.02
SEED = 7


def _quiet(*_a: object, **_k: object) -> None:
    return None


@pytest.fixture(scope="module")
def generated(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, Any]]:
    out = tmp_path_factory.mktemp("client-size")
    return out, gen.generate(out, seed=SEED, scale=SCALE, graph_scale=GRAPH_SCALE, say=_quiet)


def _rows(
    out: Path, manifest: dict[str, Any], kind: str
) -> Iterator[tuple[dict[str, Any], dict[str, Any]]]:
    for entry in manifest["files"]:
        if entry["kind"] == kind:
            with (out / entry["path"]).open(encoding="utf-8") as handle:
                for line in handle:
                    yield entry, json.loads(line)


def _events(out: Path, manifest: dict[str, Any]) -> Iterator[tuple[dict[str, Any], dict[str, str]]]:
    for entry in manifest["files"]:
        if entry["kind"] == "events":
            with (out / entry["path"]).open(encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    yield entry, row


# --- Determinism ------------------------------------------------------------------------------


def test_the_same_seed_writes_the_same_bytes_whatever_the_job_count(
    generated: tuple[Path, dict[str, Any]], tmp_path: Path
) -> None:
    out, first = generated
    second = gen.generate(
        tmp_path / "again", seed=SEED, scale=SCALE, graph_scale=GRAPH_SCALE, jobs=3, say=_quiet
    )
    assert second == first
    assert (tmp_path / "again" / "manifest.json").read_bytes() == (
        out / "manifest.json"
    ).read_bytes()
    for entry in first["files"][:5]:
        assert (tmp_path / "again" / entry["path"]).read_bytes() == (
            out / entry["path"]
        ).read_bytes()


def test_another_seed_writes_other_bytes(
    generated: tuple[Path, dict[str, Any]], tmp_path: Path
) -> None:
    _out, first = generated
    other = gen.generate(
        tmp_path / "other", seed=SEED + 1, scale=SCALE, graph_scale=GRAPH_SCALE, say=_quiet
    )
    assert {e["path"]: e["sha256"] for e in other["files"]} != {
        e["path"]: e["sha256"] for e in first["files"]
    }


def test_every_file_in_the_manifest_is_the_file_on_disk(
    generated: tuple[Path, dict[str, Any]],
) -> None:
    import hashlib

    out, manifest = generated
    for entry in manifest["files"]:
        data = (out / entry["path"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry["sha256"], entry["path"]
        assert len(data) == entry["bytes"]


# --- Sources and markings ----------------------------------------------------------------------


def test_twelve_sources_each_its_own_dataset_and_marking_all_present(
    generated: tuple[Path, dict[str, Any]],
) -> None:
    _out, manifest = generated
    sources = manifest["sources"]
    assert 10 <= len(sources) <= 15
    assert len({s["dataset"] for s in sources}) == len(sources)
    for s in sources:
        assert s["counts"].get("nodes", 0) > 0, s["key"]
    markings = {(s["marking"]["classification"], s["marking"]["handling_code"]) for s in sources}
    assert {c for c, _ in markings} == {"OFFICIAL", "OFFICIAL-SENSITIVE", "SECRET"}
    assert {h for _, h in markings} == {"P", "C", "R"}
    assert len({s["marking"]["owning_unit"] for s in sources}) >= 8


def test_the_intelligence_reports_mark_rows_three_ways(
    generated: tuple[Path, dict[str, Any]],
) -> None:
    out, manifest = generated
    seen = Counter(
        (row.get("marking") or {}).get("classification", "source")
        + "/"
        + (row.get("marking") or {}).get("handling_code", "")
        for entry, row in _rows(out, manifest, "nodes")
        if entry["source"] == "intel" and row["type"] == "Document"
    )
    assert set(seen) == {"OFFICIAL-SENSITIVE/C", "SECRET/C", "SECRET/R"}


def test_calls_are_the_largest_source_and_in_the_tens_of_millions_at_scale_one(
    generated: tuple[Path, dict[str, Any]],
) -> None:
    _out, manifest = generated
    events = {s["key"]: s["counts"].get("events", 0) for s in manifest["sources"]}
    assert max(events, key=lambda k: events[k]) == "calls"
    projected = events["calls"] / SCALE
    assert 50_000_000 <= projected <= 75_000_000, projected


def test_the_big_source_grows_linearly_with_scale(tmp_path: Path) -> None:
    def calls(scale: float, where: str) -> int:
        result = gen.generate(
            tmp_path / where, seed=SEED, scale=scale, graph_scale=GRAPH_SCALE, say=_quiet
        )
        return next(s for s in result["sources"] if s["key"] == "calls")["counts"]["events"]

    one, two, four = calls(SCALE, "one"), calls(2 * SCALE, "two"), calls(4 * SCALE, "four")
    assert 1.9 <= two / one <= 2.1
    assert 3.8 <= four / one <= 4.2


# --- What the rows hold ------------------------------------------------------------------------


def test_every_record_is_one_the_deployment_ontology_accepts(
    generated: tuple[Path, dict[str, Any]],
) -> None:
    out, manifest = generated
    schema = load_deployment_ontology()
    types: dict[str, str] = {}
    for _entry, row in _rows(out, manifest, "nodes"):
        entity = schema.entity_type(row["type"])
        assert entity is not None, row["type"]
        validate_properties(entity, row["props"])
        types[row["id"]] = row["type"]
    for _entry, row in _rows(out, manifest, "edges"):
        edge_type = schema.edge_type(row["type"])
        assert edge_type is not None, row["type"]
        validate_properties(edge_type, row.get("props") or {})
        assert row["s"] in types and row["t"] in types, f"{row['id']} links a node never written"
        validate_edge_endpoints(edge_type, source_type=types[row["s"]], target_type=types[row["t"]])
    same_as = schema.edge_type("SAME_AS")
    assert same_as is not None
    for _entry, row in _rows(out, manifest, "same_as"):
        assert row["s"] in types and row["t"] in types, row["id"]
        validate_properties(
            same_as, {"score": row["score"], "model_version": "m", "comparison_vector": "{}"}
        )


def test_no_link_is_written_by_two_files(generated: tuple[Path, dict[str, Any]]) -> None:
    """The loader's resume rule (a collision on a rerun is the file's own earlier write) holds
    only if no pair is written by two files."""
    out, manifest = generated
    schema = load_deployment_ontology()
    first_file: dict[tuple[str, ...], str] = {}
    for entry, row in _rows(out, manifest, "edges"):
        edge_type = schema.edge_type(row["type"])
        assert edge_type is not None
        ends = (row["s"], row["t"]) if edge_type.directed else tuple(sorted((row["s"], row["t"])))
        key = (row["type"], *ends)
        assert first_file.setdefault(key, entry["path"]) == entry["path"], key
    ids = [row["id"] for _e, row in _rows(out, manifest, "edges")]
    ids += [row["id"] for _e, row in _rows(out, manifest, "same_as")]
    assert len(ids) == len(set(ids))


def test_each_links_count_and_dates_are_its_events(generated: tuple[Path, dict[str, Any]]) -> None:
    out, manifest = generated
    links = {row["id"]: row for _e, row in _rows(out, manifest, "edges")}
    seen: Counter[str] = Counter()
    first: dict[str, str] = {}
    last: dict[str, str] = {}
    for _entry, event in _events(out, manifest):
        link = links[event["edge_id"]]
        assert (link["s"], link["t"], link["type"]) == (
            event["source_id"],
            event["target_id"],
            event["edge_type"],
        )
        seen[event["edge_id"]] += 1
        at = event["occurred_at"]
        first[event["edge_id"]] = min(first.get(event["edge_id"], at), at)
        last[event["edge_id"]] = max(last.get(event["edge_id"], at), at)
    assert seen
    for link_id, count in seen.items():
        assert links[link_id].get("occ", 1) == count
        assert (links[link_id]["from"], links[link_id]["to"]) == (first[link_id], last[link_id])


def test_every_document_has_its_full_text_and_the_texts_are_client_length(
    generated: tuple[Path, dict[str, Any]],
) -> None:
    out, manifest = generated
    documents = {
        row["id"]: entry["source"]
        for entry, row in _rows(out, manifest, "nodes")
        if row["type"] == "Document"
    }
    lengths: dict[str, list[int]] = defaultdict(list)
    for entry, row in _rows(out, manifest, "texts"):
        assert documents.pop(row["document_id"]) == entry["source"]
        lengths[entry["source"]].append(len(row["text"].encode()))
    assert documents == {}
    mean = {source: sum(v) / len(v) for source, v in lengths.items()}
    assert 2_500 <= mean["intel"] <= 6_000, mean
    assert 5_000 <= mean["casefiles"] <= 11_000, mean
    assert 1_200 <= mean["sars"] <= 4_000, mean
    assert 1_500 <= mean["covert"] <= 5_000, mean


def test_a_document_names_its_subjects_in_its_text(generated: tuple[Path, dict[str, Any]]) -> None:
    out, manifest = generated
    texts = {row["document_id"]: row["text"] for _e, row in _rows(out, manifest, "texts")}
    named = 0
    for _entry, row in _rows(out, manifest, "nodes"):
        if row["type"] == "Document" and row["props"]["title"].startswith("Intelligence report: "):
            subject = row["props"]["title"].removeprefix("Intelligence report: ").split(",")[0]
            assert subject in texts[row["id"]]
            named += 1
    assert named > 10


# --- Variants, sound-alikes and merge candidates -------------------------------------------------


def _people(out: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [row["props"] for _e, row in _rows(out, manifest, "nodes") if row["type"] == "Person"]


def test_names_are_spelt_several_ways_across_the_sources(
    generated: tuple[Path, dict[str, Any]],
) -> None:
    out, manifest = generated
    people = _people(out, manifest)
    given = Counter(p["given_names"] for p in people)
    family = Counter(p["family_name"] for p in people)
    mohammed = set(plan.FORENAME_GROUPS[0])
    assert len(mohammed & set(given)) >= 4, sorted(mohammed & set(given))
    assert {"Smith", "Smyth"} <= set(family)
    assert any(not name.isascii() for name in given | family), "no accented spelling to fold"
    texts = " ".join(row["text"] for _e, row in _rows(out, manifest, "texts"))
    assert sum(name in texts for name in mohammed) >= 3


def test_the_planted_candidates_cross_datasets_and_include_near_misses(
    generated: tuple[Path, dict[str, Any]],
) -> None:
    out, manifest = generated
    rows = [row for _e, row in _rows(out, manifest, "same_as")]
    assert {row["truth"] for row in rows} == {"same", "different"}
    distances = Counter(d for row in rows if row["truth"] == "same" for d in row["distance"])
    assert {"exact", "variant", "sound_alike", "slip", "identifier"} <= set(distances)
    for row in rows:
        assert row["s"].split("-")[1] != row["t"].split("-")[1] or row["t"].startswith("cs-iban"), (
            row
        )
        assert (row["score"] >= 0.8) == (row["truth"] == "same"), row
    by_plant = Counter(e["stream"] for e, _r in _rows(out, manifest, "same_as"))
    for left, _lb, right, _rb, _share in plan.SAME_AS_PAIRS:
        assert by_plant[f"people-{left}-{right}"] > 0, (left, right)
    assert by_plant["orgs"] and by_plant["accounts"] and by_plant["numbers"]


def test_a_same_candidate_joins_two_records_of_one_person(
    generated: tuple[Path, dict[str, Any]],
) -> None:
    out, manifest = generated
    people = {
        row["id"]: row["props"]
        for _e, row in _rows(out, manifest, "nodes")
        if row["type"] == "Person"
    }
    checked = 0
    for _entry, row in _rows(out, manifest, "same_as"):
        if row["s"] in people and row["t"] in people:
            same_birth = people[row["s"]]["date_of_birth"] == people[row["t"]]["date_of_birth"]
            assert same_birth == (row["truth"] == "same") or row["truth"] == "different"
            if row["truth"] == "same":
                assert same_birth, row
                checked += 1
    assert checked > 50


# --- Nothing real ------------------------------------------------------------------------------

_E164 = re.compile(r"\+44\d{9,10}")
_WRITTEN = re.compile(r"\b07\d{3} ?\d{6}\b")
_NINO = re.compile(r"\b[A-Z]{2}\d{6}[A-D]\b")
_EMAIL = re.compile(r"[\w.+-]+@([\w-]+\.)+\w+")
_POSTCODE = re.compile(r"\b[A-Z]{1,2}\d{1,2} \d[A-Z]{2}\b")


def test_no_identifier_could_be_a_real_one(generated: tuple[Path, dict[str, Any]]) -> None:
    out, manifest = generated
    for entry in manifest["files"]:
        content = (out / entry["path"]).read_text(encoding="utf-8")
        for number in _E164.findall(content):
            assert number.startswith("+447700") and not number.startswith("+447700900"), number
        for number in _WRITTEN.findall(content):
            assert number.replace(" ", "").startswith("07700"), number
            assert not number.replace(" ", "").startswith("07700900"), number
        for nino in _NINO.findall(content):
            assert nino[:2] in ("TN", "NT", "BG", "GB", "KN", "NK", "ZZ"), nino
        for match in _EMAIL.finditer(content):
            assert match.group(0).endswith(("@example.org", "@example.net")), match.group(0)
        for code in _POSTCODE.findall(content):
            assert code.startswith("ZZ"), code
        for value in re.findall(r"\bGB\d{2}[A-Z]{4}\d{14}\b", content):
            assert value[4:8] == "XSYN", value
        for value in re.findall(r"\b\d{15}\b", content):
            assert value.startswith("35999"), value


def test_no_name_is_one_the_prison_intelligence_dataset_owns() -> None:
    """The PID's own name test fails on any of its surnames in another file; the invented
    surnames are built at run time, so they are checked here as well."""
    pid = {name.lower() for name in SURNAMES} | {name.lower() for name in STAFF_NAMES}
    assert not pid & {name.lower() for name in plan.invented_surnames()}
    for module in (plan, gen):
        text = Path(module.__file__).read_text()
        for name in SURNAMES:
            assert not re.search(rf"\b{re.escape(name)}\b", text, re.IGNORECASE), name


def test_the_synthetic_number_range_skips_the_drama_block_the_pid_uses() -> None:
    assert plan.msisdn(899_999) == "+447700899999"
    assert plan.msisdn(900_000) == "+447700901000"
    with pytest.raises(ValueError):
        plan.msisdn(999_000)


# --- The command -------------------------------------------------------------------------------


def test_a_folder_inside_the_repository_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    inside = Path(gen.__file__).resolve().parent / "client-size-out"
    assert gen.main(["--out", str(inside), "--scale", "0.0001"]) == 2
    assert "inside the git working tree" in capsys.readouterr().err
    assert not inside.exists()


def test_a_folder_already_holding_a_set_is_refused(
    generated: tuple[Path, dict[str, Any]], capsys: pytest.CaptureFixture[str]
) -> None:
    out, _manifest = generated
    before = (out / "manifest.json").read_bytes()
    assert gen.main(["--out", str(out), "--scale", "0.0001"]) == 2
    assert "already holds a generated set" in capsys.readouterr().err
    assert (out / "manifest.json").read_bytes() == before
