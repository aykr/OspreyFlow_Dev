"""Step 4's search query set from a generated client-size set (`scripts.client_size_queries`).

Offline, on a small generated set: every row is drawn from a record `m10-measure` reads by the
product's own rule (`principal_may_read`), each class holds what the runner sends (a prefix, a
changed name, a filtered phrase, an identifier expected first), and a seed fixes the file. Red first
(rule 15): a row drawn from a SECRET document, an exact row expecting a record other than the one
visible holder of its number, and a class with too few rows are each refused before anything is
written; the plants take the shape `build` emits, so each is refused by its own check.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from scripts import client_size_queries as q
from scripts import generate_client_size as gen

SCALE = 0.0002
GRAPH_SCALE = 0.01
PER_CLASS = 20


@pytest.fixture(scope="module")
def folder(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("client-size-queries")
    gen.generate(out, seed=11, scale=SCALE, graph_scale=GRAPH_SCALE, say=lambda *_a: None)
    return out


def _run(folder: Path, out: Path, *extra: str) -> dict[str, Any]:
    argv = ["--from", str(folder), "--out", str(out), "--per-class", str(PER_CLASS), *extra]
    assert q.main(argv) == 0
    rows = [json.loads(line) for line in (out / "queries.jsonl").read_text().splitlines()]
    return {"rows": rows, "counts": json.loads((out / "counts.json").read_text())}


@pytest.fixture(scope="module")
def made(folder: Path, tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    return _run(folder, tmp_path_factory.mktemp("queries"))


@pytest.fixture(scope="module")
def world(folder: Path) -> dict[str, Any]:
    case_records = q.records(folder, "intel")
    measure = q.measure_principal(next(iter(case_records.values())).dataset)
    readable = {
        i for i, r in case_records.items() if r.type == "Document" and q.may_read(measure, r)
    }
    return {
        "records": case_records,
        "measure": measure,
        "texts": q.texts(folder, "intel", readable),
    }


def _by_class(made: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    return [r for r in made["rows"] if r["class"] == kind]


def test_each_class_holds_its_count_and_the_counts_are_recorded(made: dict[str, Any]) -> None:
    assert Counter(r["class"] for r in made["rows"]) == {k: PER_CLASS for k in q.CLASSES}
    counts = made["counts"]
    assert counts["counts"] == {k: PER_CLASS for k in q.CLASSES}
    assert counts["seed"] == q.DEFAULT_SEED and counts["principal"] == q.MEASURE
    assert len(counts["manifest_sha256"]) == 64
    assert all(counts["eligible"][k] >= PER_CLASS for k in q.CLASSES)


def test_every_row_is_drawn_from_a_record_the_measured_principal_reads(
    folder: Path, made: dict[str, Any], world: dict[str, Any]
) -> None:
    for row in made["rows"]:
        assert q.may_read(world["measure"], world["records"][row["from"]]), row
    # `build` itself draws from the visible records, whatever texts it is given: here every
    # document's, the SECRET ones' too, so the command's reading only readable texts hides nothing.
    every_text = q.texts(folder, "intel", set(world["records"]))
    rows, _eligible = q.build(
        world["records"], every_text, world["measure"], seed=q.DEFAULT_SEED, per_class=PER_CLASS
    )
    assert rows and all(q.may_read(world["measure"], world["records"][r["from"]]) for r in rows)


def test_the_case_holds_documents_the_measured_principal_cannot_read(world: dict[str, Any]) -> None:
    """Else the SECRET refusal below would be shown on a set where it never arises."""
    hidden = [
        r for r in world["records"].values()
        if r.type == "Document" and not q.may_read(world["measure"], r)
    ]  # fmt: skip
    assert hidden and {r.handling.classification for r in hidden} == {"SECRET"}


def test_suggest_rows_are_short_prefixes_of_a_persons_names(
    made: dict[str, Any], world: dict[str, Any]
) -> None:
    for row in _by_class(made, "suggest"):
        person = world["records"][row["from"]]
        assert person.type == "Person" and 2 <= len(row["query"]) <= 6
        names = (str(person.props["given_names"]).split(" ")[0], person.props["family_name"])
        assert any(n.startswith(row["query"]) for n in names)


def test_names_rows_change_the_name_each_of_three_ways(
    made: dict[str, Any], world: dict[str, Any]
) -> None:
    rows = _by_class(made, "names")
    for row in rows:
        person = world["records"][row["from"]]
        given = str(person.props["given_names"]).split(" ")[0]
        assert row["query"] != f"{given} {person.props['family_name']}"
    for row in (r for r in rows if r["change"] == "variant"):
        person = world["records"][row["from"]]
        given = str(person.props["given_names"]).split(" ")[0]
        changed = set(row["query"].split()) - {given, person.props["family_name"]}
        assert len(changed) == 1, row
        word = changed.pop()
        groups = (*q.plan.FORENAME_GROUPS, *q.plan.SURNAME_GROUPS)
        assert any(word in g and (given in g or person.props["family_name"] in g) for g in groups)
    changes = Counter(r["change"] for r in rows)
    assert set(changes) == set(q.CHANGES)
    assert max(changes.values()) - min(changes.values()) <= 1, "a third each"


def test_fulltext_rows_are_phrases_of_their_document_within_its_dataset_and_dates(
    made: dict[str, Any], world: dict[str, Any]
) -> None:
    for row in _by_class(made, "fulltext"):
        doc = world["records"][row["from"]]
        assert 2 <= len(row["query"].split()) <= 6
        assert row["query"] in " ".join(world["texts"][doc.id].split())
        f = row["filters"]
        assert f["datasets"] == [doc.dataset] == ["cs-intel"]
        day = date.fromisoformat(str(doc.props["sent_at"])[:10])
        assert date.fromisoformat(f["date_from"]) <= day <= date.fromisoformat(f["date_to"])


def test_exact_rows_expect_the_one_record_holding_their_number(
    made: dict[str, Any], world: dict[str, Any]
) -> None:
    for row in _by_class(made, "exact"):
        assert row["expect_first"] == row["from"]
        assert row["expect_first"].startswith("cs-intel-number-")
        holders = [
            r.id for r in world["records"].values()
            if q.may_read(world["measure"], r) and row["query"] in q._numbers(r)
        ]  # fmt: skip
        assert holders == [row["expect_first"]]


def test_a_seed_fixes_the_file(folder: Path, made: dict[str, Any], tmp_path: Path) -> None:
    again = _run(folder, tmp_path / "again")
    other = _run(folder, tmp_path / "other", "--seed", "5")
    assert again["rows"] == made["rows"]
    assert other["rows"] != made["rows"]


def test_m9_has_five_names_and_five_suggest_rows_first(made: dict[str, Any]) -> None:
    assert len(_by_class(made, "names")[:5]) == 5 and len(_by_class(made, "suggest")[:5]) == 5


def _check(rows: list[dict[str, Any]], world: dict[str, Any], per_class: int = 1) -> None:
    q.check_queries(rows, world["records"], world["texts"], world["measure"], per_class=per_class)


def _one_each(made: dict[str, Any]) -> list[dict[str, Any]]:
    return [_by_class(made, k)[0] for k in q.CLASSES]


def test_the_rows_as_built_pass_the_check(made: dict[str, Any], world: dict[str, Any]) -> None:
    """The control for the plants below: each changes one row of a set the check passes."""
    _check(_one_each(made), world)


def test_a_row_from_a_secret_document_is_refused(
    made: dict[str, Any], world: dict[str, Any]
) -> None:
    """Red first: a fulltext row drawn by `fulltext_row` itself from a SECRET document."""
    secret = next(
        r for r in world["records"].values()
        if r.type == "Document" and r.handling.classification == "SECRET"
    )  # fmt: skip
    planted = q.fulltext_row(secret, "the account was opened in the name of a third party", 4)
    assert planted is not None
    with pytest.raises(q.QuerySetRefused, match="cannot read"):
        _check([*_one_each(made), planted], world)


def test_an_exact_row_expecting_a_record_it_does_not_name_is_refused(
    made: dict[str, Any], world: dict[str, Any]
) -> None:
    row = _by_class(made, "exact")[0]
    hidden_doc = next(
        r.id for r in world["records"].values()
        if r.type == "Document" and not q.may_read(world["measure"], r)
    )  # fmt: skip
    with pytest.raises(q.QuerySetRefused, match="does not name its expect_first"):
        _check([*_one_each(made)[:3], {**row, "expect_first": hidden_doc}], world)


def test_an_exact_row_whose_number_two_visible_records_hold_is_refused(
    made: dict[str, Any], world: dict[str, Any]
) -> None:
    row = _by_class(made, "exact")[0]
    holder = world["records"][row["from"]]
    twin = q.Record(id="cs-intel-number-twin", type=holder.type, dataset=holder.dataset,
                    handling=holder.handling, props=holder.props)  # fmt: skip
    with pytest.raises(q.QuerySetRefused, match="names 2 visible records"):
        q.check_queries(
            _one_each(made), {**world["records"], twin.id: twin}, world["texts"], world["measure"],
            per_class=1,
        )  # fmt: skip


def test_a_fulltext_row_without_its_date_filter_is_refused(
    made: dict[str, Any], world: dict[str, Any]
) -> None:
    row = _by_class(made, "fulltext")[0]
    planted = {**row, "filters": {"datasets": row["filters"]["datasets"]}}
    with pytest.raises(q.QuerySetRefused, match="lacks a dataset and a date filter"):
        _check([planted], world)


def test_a_class_with_too_few_rows_is_refused_in_words(
    made: dict[str, Any], world: dict[str, Any]
) -> None:
    rows = [r for r in made["rows"] if r["class"] != "exact"] + _by_class(made, "exact")[:3]
    with pytest.raises(q.QuerySetRefused, match=f"exact 3, where each class needs {PER_CLASS}"):
        _check(rows, world, per_class=PER_CLASS)


def test_the_command_writes_nothing_when_the_set_is_too_small(folder: Path, tmp_path: Path) -> None:
    out = tmp_path / "small"
    with pytest.raises(q.QuerySetRefused, match="too few rows"):
        q.main(["--from", str(folder), "--out", str(out), "--per-class", "100000"])
    assert not (out / "queries.jsonl").exists()


def test_a_names_row_changing_only_case_or_word_order_is_refused(
    made: dict[str, Any], world: dict[str, Any]
) -> None:
    """Red first: the register form ("FAMILY Given") is the name itself to an analyser folding case
    and order, so it would time an exact name as M3."""
    row = next(r for r in _by_class(made, "names") if r["change"] == "variant")
    person = world["records"][row["from"]]
    given = str(person.props["given_names"]).split(" ")[0]
    planted = {**row, "query": f"{str(person.props['family_name']).upper()} {given}"}
    with pytest.raises(q.QuerySetRefused, match="case or word order alone"):
        _check([*_one_each(made)[:1], planted, *_one_each(made)[2:]], world)
