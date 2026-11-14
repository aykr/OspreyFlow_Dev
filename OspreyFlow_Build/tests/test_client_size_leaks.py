"""Step 4's leak cases from a generated client-size set (`scripts.client_size_leaks`, M10).

Offline, on a tiny generated set: every leak case hides a record from the part-cleared subject
that its control reads, by the product's own rule (`principal_may_read`); a case that would pass by
proving nothing (a visible record called hidden, a control that cannot read it) is refused before
anything is written; every never-join case joins a visible record of the measure case to a record
of another dataset; and every subject is of the unit of the case it searches, since the Conduit
opens a case only to its own unit (`services/api/investigations.py`). Red first (rule 15): a
generator letting a visible-visible pair through, a control that cannot read its record, or a
subject of another unit than its case's (step 4's first M10 run on stack d: every case refused 404),
is refused by the check.
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
    return case_records, leaks.subjects("cs-intel", leaks.case_units(folder))


INTEL = leaks.cleared_name("unit-intel")


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


def test_every_subject_is_of_the_unit_of_the_case_it_searches(
    folder: Path, made: dict[str, Any]
) -> None:
    _case_records, people = _world(folder)
    units = leaks.case_units(folder)
    assert units["cs-intel"] == "unit-intel" and people[leaks.PART].org_unit == "unit-intel"
    assert {c["control"] for c in made["leaks"]} == {INTEL}
    others = leaks.records(folder, only={c["hidden"] for c in made["never_join"]})
    for case in made["never_join"]:
        assert people[case["control"]].org_unit == units[others[case["hidden"]].dataset]
    subjects = made["counts"]["subjects"]
    assert subjects[leaks.PART] == {"clearance": "OFFICIAL-SENSITIVE", "org_unit": "unit-intel",
                                    "codes": ["P", "C"]}  # fmt: skip
    controls = {c["control"] for c in (*made["leaks"], *made["never_join"])}
    assert set(subjects) == {leaks.PART, *controls}


def test_a_restricted_record_of_another_unit_is_kept_out_and_counted(
    folder: Path, made: dict[str, Any]
) -> None:
    """The intelligence reports' SECRET/R reports are unit-intel-covert's: nobody who opens the
    unit-intel case reads them, so they are no case, and the count says so."""
    case_records, _people = _world(folder)
    assert not [c for c in made["leaks"] if case_records[c["hidden"]].handling.handling_code == "R"]
    restricted = sum(1 for r in case_records.values()
                     if r.handling.handling_code == "R" and r.words)  # fmt: skip
    assert restricted, "the set has SECRET/R reports of unit-intel-covert"
    assert made["counts"]["leaks_kept_out"] == {"SECRET/R unit-intel-covert": restricted}


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
    case = {"name": "planted", "hidden": visible.id, "control": INTEL}
    with pytest.raises(leaks.LeakCaseRefused, match="hides nothing"):
        leaks.check_leaks([case], case_records, people, "unit-intel")


def test_a_control_that_cannot_read_its_record_is_refused(folder: Path) -> None:
    case_records, people = _world(folder)
    covert = next(r for r in case_records.values() if r.handling.handling_code == "R")
    case = {"name": "planted", "hidden": covert.id, "control": INTEL}
    with pytest.raises(leaks.LeakCaseRefused, match="cannot read it"):
        leaks.check_leaks([case], case_records, people, "unit-intel")


def test_a_never_join_pair_inside_one_dataset_is_refused(folder: Path) -> None:
    case_records, people = _world(folder)
    two = [r.id for r in case_records.values() if leaks.may_read(people[leaks.PART], r)][:2]
    case = {"name": "planted", "visible": two[0], "hidden": two[1], "control": INTEL}
    with pytest.raises(leaks.LeakCaseRefused, match="both records"):
        leaks.check_never_join(
            [case], case_records, people, case_records, leaks.case_units(folder), "cs-intel"
        )


def test_a_never_join_control_that_cannot_read_the_partner_in_its_case_is_refused(
    folder: Path, made: dict[str, Any]
) -> None:
    """Red first: a control of the partner's case's unit not cleared for its code shows no reach."""
    case_records, people = _world(folder)
    others = leaks.records(folder, only={c["hidden"] for c in made["never_join"]})
    restricted = next(
        c for c in made["never_join"] if others[c["hidden"]].handling.handling_code == "R"
    )
    control = people[restricted["control"]]
    uncleared = {
        **people,
        control.id: control.model_copy(update={"receivable_handling_codes": ["P", "C"]}),
    }
    with pytest.raises(leaks.LeakCaseRefused, match="cannot read it in its own case"):
        leaks.check_never_join(
            [restricted], case_records, uncleared, others, leaks.case_units(folder), "cs-intel"
        )


def test_a_leak_control_of_another_unit_than_the_case_is_refused(
    folder: Path, made: dict[str, Any]
) -> None:
    """Red first, the shape the generator emitted before: a SECRET/C report of the unit-intel case
    controlled by unit-fiu's cleared subject, which may read the record but cannot open the case."""
    case_records, people = _world(folder)
    case = {**made["leaks"][0], "control": leaks.cleared_name("unit-fiu")}
    assert leaks.may_read(people[case["control"]], case_records[case["hidden"]])
    with pytest.raises(leaks.LeakCaseRefused, match="opened only to its own unit"):
        leaks.check_leaks([case], case_records, people, "unit-intel")


def test_a_never_join_control_of_another_unit_than_the_partners_case_is_refused(
    folder: Path, made: dict[str, Any]
) -> None:
    """Red first: a cs-calls partner (unit-comms' case) controlled by unit-fiu, as before."""
    case_records, people = _world(folder)
    others = leaks.records(folder, only={c["hidden"] for c in made["never_join"]})
    calls = next(c for c in made["never_join"] if others[c["hidden"]].dataset == "cs-calls")
    planted = {**calls, "control": leaks.cleared_name("unit-fiu")}
    with pytest.raises(leaks.LeakCaseRefused, match="opened only to its own unit"):
        leaks.check_never_join(
            [planted], case_records, people, others, leaks.case_units(folder), "cs-intel"
        )


def test_a_part_cleared_subject_of_another_unit_than_the_case_is_refused(
    folder: Path, made: dict[str, Any]
) -> None:
    """Red first: m10-part of unit-records, as before, cannot open the unit-intel case."""
    case_records, people = _world(folder)
    part = people[leaks.PART].model_copy(update={"org_unit": "unit-records"})
    with pytest.raises(leaks.LeakCaseRefused, match="the part-cleared m10-part is of unit-records"):
        leaks.check_leaks(made["leaks"][:1], case_records, {**people, leaks.PART: part},
                          "unit-intel")  # fmt: skip
