"""Step 4's leak cases from a generated client-size set (`scripts.client_size_leaks`, M10).

Offline, on a tiny generated set: every leak case hides a record from the part-cleared subject
that its control reads, by the product's own rule (`principal_may_read`); a case that would pass by
proving nothing (a visible record called hidden, a control that cannot read it) is refused before
anything is written; every never-join case joins a visible record of the measure case to a record
of another dataset. Red first (rule 15): a generator letting a visible-visible pair through, or a
control of the wrong unit, is refused by the check.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts import client_size_leaks as leaks
from scripts import generate_client_size as gen

SCALE = 0.0002
GRAPH_SCALE = 0.01


@pytest.fixture(scope="module")
def folder(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("client-size-leaks")
    manifest = gen.generate(
        out, seed=11, scale=SCALE, graph_scale=GRAPH_SCALE, say=lambda *_a: None
    )
    # The load's ledger names each source's case, as the loader's cases stage records it.
    cases = {s["key"]: f"case-{s['key']}" for s in manifest["sources"]}
    (out / "load_state.json").write_text(json.dumps({"cases": cases}), encoding="utf-8")
    return out


@pytest.fixture(scope="module")
def made(folder: Path, tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    out = tmp_path_factory.mktemp("cases")
    assert leaks.main(["--from", str(folder), "--out", str(out), "--limit", "100000"]) == 0
    read = {
        name: [json.loads(line) for line in (out / f"{name}.jsonl").read_text().splitlines()]
        for name in ("leaks", "never_join")
    }
    return {"out": out, **read, "counts": json.loads((out / "counts.json").read_text())}


def _world(folder: Path) -> tuple[dict[str, leaks.Record], dict[str, Any]]:
    case_records = leaks.records(folder, "intel")
    return case_records, leaks.subjects(next(iter(case_records.values())).dataset)


def test_each_leak_case_hides_its_record_from_the_part_cleared_and_its_control_reads_it(
    folder: Path, made: dict[str, Any]
) -> None:
    case_records, people = _world(folder)
    assert made["leaks"], "the set has hidden intelligence reports, so there are leak cases"
    for case in made["leaks"]:
        record = case_records[case["hidden"]]
        assert not leaks.may_read(people[leaks.PART], record)
        assert leaks.may_read(people[case["control"]], record)
        assert case["never_ids"] == [record.id] and case["query"]


def test_a_restricted_records_control_is_its_own_units(folder: Path, made: dict[str, Any]) -> None:
    case_records, _people = _world(folder)
    restricted = [c for c in made["leaks"] if case_records[c["hidden"]].handling.handling_code == "R"]
    assert restricted, "the set has SECRET/R reports of unit-intel-covert"
    assert {c["control"] for c in restricted} == {"m10-cleared-unit-intel-covert"}


def test_each_never_join_case_joins_a_visible_record_to_another_datasets(
    folder: Path, made: dict[str, Any]
) -> None:
    case_records, people = _world(folder)
    assert made["never_join"], "the set plants SAME_AS across the intelligence reports' dataset"
    others = leaks.records(folder, only={c["hidden"] for c in made["never_join"]})
    for case in made["never_join"]:
        partner = others[case["hidden"]]
        assert case["hidden"] not in case_records
        assert leaks.may_read(people[leaks.PART], case_records[case["visible"]])
        # The control reads the partner in the partner's own case, so the query's reach is shown.
        assert case["partner_case"] == leaks.partner_cases(folder)[partner.dataset]
        assert partner.dataset != "cs-intel"
        assert leaks.may_read(leaks.in_dataset(people[case["control"]], partner.dataset), partner)
        assert not leaks.may_read(people[leaks.PART], partner)


def test_the_counts_name_every_eligible_case(made: dict[str, Any]) -> None:
    assert made["counts"]["leaks_eligible"] == len(made["leaks"])
    assert made["counts"]["never_join_eligible"] == len(made["never_join"])


def test_a_visible_visible_pair_is_refused(folder: Path) -> None:
    """Red first: a case naming a record the part-cleared subject reads as hidden would pass by
    proving nothing; the check refuses it."""
    case_records, people = _world(folder)
    visible = next(r for r in case_records.values() if leaks.may_read(people[leaks.PART], r))
    case = {"name": "planted", "hidden": visible.id, "control": "m10-cleared-unit-fiu"}
    with pytest.raises(leaks.LeakCaseRefused, match="hides nothing"):
        leaks.check_leaks([case], case_records, people)


def test_a_control_that_cannot_read_its_record_is_refused(folder: Path) -> None:
    case_records, people = _world(folder)
    covert = next(r for r in case_records.values() if r.handling.handling_code == "R")
    case = {"name": "planted", "hidden": covert.id, "control": "m10-cleared-unit-fiu"}
    with pytest.raises(leaks.LeakCaseRefused, match="cannot read it"):
        leaks.check_leaks([case], case_records, people)


def test_a_never_join_pair_inside_one_dataset_is_refused(folder: Path) -> None:
    case_records, people = _world(folder)
    two = [r.id for r in case_records.values() if leaks.may_read(people[leaks.PART], r)][:2]
    case = {"name": "planted", "visible": two[0], "hidden": two[1],
            "control": "m10-cleared-unit-fiu"}  # fmt: skip
    with pytest.raises(leaks.LeakCaseRefused, match="both records"):
        leaks.check_never_join([case], case_records, people, case_records)


def test_a_never_join_control_that_cannot_read_the_partner_in_its_case_is_refused(
    folder: Path, made: dict[str, Any]
) -> None:
    """Red first: a control of the wrong unit for a restricted partner shows no reach."""
    case_records, people = _world(folder)
    others = leaks.records(folder, only={c["hidden"] for c in made["never_join"]})
    restricted = next(
        c for c in made["never_join"] if others[c["hidden"]].handling.handling_code == "R"
    )
    wrong = next(n for n in people if n.startswith("m10-cleared") and n != restricted["control"])
    with pytest.raises(leaks.LeakCaseRefused, match="cannot read it in its own case"):
        leaks.check_never_join([{**restricted, "control": wrong}], case_records, people, others)
