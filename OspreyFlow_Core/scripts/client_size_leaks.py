"""Step 4's leak cases (M10, ADR-149 Amendment 2) from a generated client-size set (`v052-load`).

    python -m scripts.client_size_leaks --from DIR --out FOLDER [--case intel] [--limit 500]

Two JSON-lines files, for `scripts.measure_search.measure_leaks`, each case a search in the measure
case (the source `--case` names; the intelligence reports by default, where `m10-measure` draws and
`m10-part` reads):

- **`leaks.jsonl`**: a record of the measure case's own dataset that the part-cleared principal
  (`m10-part`) may not read, by its marking (SECRET, or a restricted code of another unit). The
  query finds it; its id, and its distinguishing words (its title or name, where no record that
  principal may read in the case has the same), must appear nowhere in that principal's answer;
  and `control` names the cleared subject that must find it, or the case proves nothing.
- **`never_join.jsonl`**: each planted SAME_AS candidate that truly joins (`truth` `same`) a record
  the part-cleared principal reads in the measure case to a record of another dataset. Searched by
  the visible record's name, the other's id (and its spelling, where no visible record has it) must
  never be returned nor merged in (ADR-099 Amendment 2: no join across cases). Its control is in
  the other record's own case (`partner_case`, from the load's ledger), the cleared subject of that
  case's unit, and must find it there by the same query, or the case shows no reach and proves
  nothing.

**Every subject is of the unit of the case it searches.** The Conduit opens a case only for a
principal whose `org_unit` is the case's `owning_unit`, whatever it is granted
(`services/api/investigations.py`, ADR-036's boundary), and a case's unit is its source's marking's
(`load_client_size`'s cases stage). So `m10-part` is of the measure case's unit, and each control is
`m10-cleared-<the unit of the case it searches>`, cleared SECRET with codes P C R. A record no such
control may read (a code-R record of another unit than its case's) can be shown to nobody who opens
the case, so it is no case: it is left out and counted (`kept_out`), never given a control of
another unit, which the case would refuse with a 404 and so prove nothing (step 4's first M10 run
on stack d, 14 November 2026: every case refused so).

**A hidden word is checked only where the reader could not see it anyway.** A case's `never_text`
keeps a hidden record's words only where nothing `m10-part` may read in the measure case holds them,
as a substring, case folded, as `measure_leaks` compares: no visible record's property and no
visible document's text (`visible_corpus`). The words are often visible in their own right: a hidden
partner's number inside the visible record's own `+44…`, a hidden spelling of a name in a visible
report (step 4's second M10 run on stack d, 14 November 2026: 65 of its never-join cases failed so,
with no hidden id in any answer). The ids are checked whatever the words. The words dropped are
counted (`never_text_dropped`).

Visibility is the product's own rule (`ontology.handling.principal_may_read`, the three axes),
asked of the principals the subjects stand for (`counts.json`'s `subjects`, the claims step 4's
issuer gives them, `process/lanes/rules/v052-load/B_RECORD.md`). Before anything is written every
case is checked (`check_leaks`, `check_never_join`): a hidden record the part-cleared principal
could read, a control that could not, or a subject of another unit than the case it searches, is
refused, so the file never holds a case that passes by proving nothing.
At most `--limit` cases a list, chosen by a hash of each record's id (the same set every run); the
counts of every eligible case are printed and written to `counts.json` beside them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ontology.handling import load_uk_le_scheme, principal_may_read
from schemas.domain import Handling, Principal

SCHEME = load_uk_le_scheme()
PART = "m10-part"


def cleared_name(unit: str) -> str:
    """The cleared control of the cases of `unit`."""
    return f"m10-cleared-{unit}"


def case_units(folder: Path) -> dict[str, str]:
    """Each dataset's case's unit: its source's marking's `owning_unit`, which the loader's cases
    stage makes the case's `owning_unit`, the unit the Conduit opens it to."""
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    return {s["dataset"]: s["marking"]["owning_unit"] for s in manifest["sources"]}


def subjects(dataset: str, units: Mapping[str, str]) -> dict[str, Principal]:
    """Each M10 subject as the Conduit would resolve it reading the measure case (its datasets the
    case's own), with the claims step 4's issuer gives it: the part-cleared of the measure case's
    unit, and a cleared control of each case's unit."""
    cleared = {
        cleared_name(unit): Principal(
            id=cleared_name(unit), clearance="SECRET", org_unit=unit,
            receivable_handling_codes=["P", "C", "R"], datasets=[dataset],
        )
        for unit in sorted(set(units.values()))
    }  # fmt: skip
    part = Principal(
        id=PART, clearance="OFFICIAL-SENSITIVE", org_unit=units[dataset],
        receivable_handling_codes=["P", "C"], datasets=[dataset],
    )  # fmt: skip
    return {**cleared, PART: part}


@dataclass(frozen=True)
class Record:
    id: str
    type: str
    dataset: str
    handling: Handling
    props: Mapping[str, Any]

    @property
    def words(self) -> str:
        """What distinguishes it in an answer: a document's title, a person's full name, an
        organisation's name, a number as written."""
        p = self.props
        if self.type == "Document":
            return str(p.get("title") or "")
        if self.type == "Person":
            return " ".join(str(p[k]) for k in ("given_names", "family_name") if p.get(k))
        return str(p.get("name") or p.get("value_raw") or "")


def _handling(marking: Mapping[str, str]) -> Handling:
    return Handling(
        classification=marking["classification"], handling_code=marking["handling_code"],
        originator=marking["originator"], owning_unit=marking["owning_unit"],
    )  # fmt: skip


def _rows(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def records(
    folder: Path, source_key: str | None = None, *, only: set[str] | None = None
) -> dict[str, Record]:
    """The nodes of one source (or of every source), each with its own marking where the row gives
    one, else its source's; `only` keeps those ids alone, read in one pass over the files."""
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    out: dict[str, Record] = {}
    for source in manifest["sources"]:
        if source_key is not None and source["key"] != source_key:
            continue
        for path in sorted((folder / source["key"]).glob("*.nodes.jsonl")):
            for row in _rows(path):
                if only is not None and row["id"] not in only:
                    continue
                out[row["id"]] = Record(
                    id=row["id"], type=row["type"], dataset=source["dataset"],
                    handling=_handling(row.get("marking") or source["marking"]),
                    props=row["props"],
                )  # fmt: skip
    return out


def may_read(principal: Principal, record: Record) -> bool:
    return principal_may_read(record.handling, [record.dataset], principal, SCHEME)


def control_for(record: Record, cleared: Mapping[str, Principal], unit: str) -> str | None:
    """The control of the case's unit, if it reads `record`; else none, since a subject of any
    other unit cannot open the case."""
    name = cleared_name(unit)
    return name if name in cleared and may_read(cleared[name], record) else None


def _marking(record: Record) -> str:
    h = record.handling
    return f"{h.classification}/{h.handling_code} {h.owning_unit}"


def _sample(items: Iterable[dict[str, Any]], key: str, limit: int) -> list[dict[str, Any]]:
    ranked = sorted(items, key=lambda c: hashlib.sha256(c[key].encode()).hexdigest())
    return sorted(ranked[:limit], key=lambda c: c[key])


def leak_cases(
    case_records: Mapping[str, Record], people: Mapping[str, Principal], unit: str
) -> tuple[list[dict[str, Any]], Counter[str]]:
    """The leak cases, and the hidden records left out by marking: those no subject who opens the
    case (of `unit`) may read."""
    part = people[PART]
    cleared = {n: p for n, p in people.items() if n != PART}
    seen_words = {r.words for r in case_records.values() if may_read(part, r)}
    cases = []
    kept_out: Counter[str] = Counter()
    for record in case_records.values():
        if may_read(part, record) or not record.words:
            continue
        control = control_for(record, cleared, unit)
        if control is None:
            kept_out[_marking(record)] += 1  # nobody who opens the case reads it: no case
            continue
        cases.append({
            "name": f"hidden {record.type} {record.id} ({record.handling.classification}/"
                    f"{record.handling.handling_code}, {record.handling.owning_unit})",
            "route": "search", "query": record.words, "never_ids": [record.id],
            "never_text": [] if record.words in seen_words else [record.words],
            "control": control, "hidden": record.id,
        })  # fmt: skip
    return cases, kept_out


def in_dataset(principal: Principal, dataset: str) -> Principal:
    """The same subject reading another case: its datasets that case's."""
    return principal.model_copy(update={"datasets": [dataset]})


def partner_cases(folder: Path) -> dict[str, str]:
    """Each dataset's case id, from the load's ledger (`load_state.json`) and the manifest."""
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    ledger = json.loads((folder / "load_state.json").read_text(encoding="utf-8"))
    return {s["dataset"]: ledger["cases"][s["key"]] for s in manifest["sources"]}


def never_join_cases(
    folder: Path,
    case_records: Mapping[str, Record],
    people: Mapping[str, Principal],
    cases_by_dataset: Mapping[str, str],
    units: Mapping[str, str],
) -> tuple[list[dict[str, Any]], Counter[str]]:
    part = people[PART]
    visible = {i: r for i, r in case_records.items() if may_read(part, r)}
    seen_words = {r.words for r in visible.values()}
    pairs: list[tuple[str, str, str]] = []
    for path in sorted((folder / "same_as").glob("*.jsonl")):
        for row in _rows(path):
            if row["truth"] != "same":
                continue
            ends = [row["s"], row["t"]]
            mine = [e for e in ends if e in visible]
            if len(mine) != 1:
                continue
            other_id = ends[1 - ends.index(mine[0])]
            if other_id not in case_records:  # both in the case's dataset is not across cases
                pairs.append((row["id"], mine[0], other_id))
    others = records(folder, only={other for _p, _m, other in pairs})
    cleared = {n: p for n, p in people.items() if n != PART}
    cases = []
    kept_out: Counter[str] = Counter()
    for pair_id, mine_id, other_id in pairs:
        other = others[other_id]
        there = {n: in_dataset(p, other.dataset) for n, p in cleared.items()}
        control = control_for(other, there, units[other.dataset])
        if control is None:
            kept_out[f"{other.dataset}: {_marking(other)}"] += 1  # no reach can be shown there
            continue
        cases.append({
            "name": f"never joined: {mine_id} and {other_id} ({pair_id})",
            "route": "search", "query": visible[mine_id].words, "never_ids": [other_id],
            "never_text": [] if other.words in seen_words else [other.words],
            "control": control, "partner_case": cases_by_dataset[other.dataset],
            "visible": mine_id, "hidden": other_id, "other_dataset": other.dataset,
        })  # fmt: skip
    return cases, kept_out


class LeakCaseRefused(ValueError):
    """A case that would pass by proving nothing: its hidden record readable by the principal it
    is hidden from, not readable by its control, or searched by a subject the case is not opened
    to."""


def _opens(people: Mapping[str, Principal], name: str, unit: str, case: dict[str, Any],
           what: str) -> None:  # fmt: skip
    """Refuse a subject the case gate refuses: one not of the searched case's unit."""
    if people[name].org_unit != unit:
        raise LeakCaseRefused(
            f"{case['name']}: {what} {name} is of {people[name].org_unit}, and the case it "
            f"searches is {unit}'s: the case is opened only to its own unit, so the search is "
            "refused (404) and proves nothing"
        )


def check_leaks(cases: Iterable[dict[str, Any]], case_records: Mapping[str, Record],
                people: Mapping[str, Principal], unit: str,
                corpus: str | None = None) -> None:  # fmt: skip
    cases = list(cases)
    if corpus is not None:
        _check_words(cases, corpus)
    for case in cases:
        _opens(people, PART, unit, case, "the part-cleared")
        _opens(people, case["control"], unit, case, "its control")
        record = case_records[case["hidden"]]
        if may_read(people[PART], record):
            raise LeakCaseRefused(
                f"{case['name']}: {PART} may read {record.id}, so it hides nothing"
            )
        if not may_read(people[case["control"]], record):
            raise LeakCaseRefused(f"{case['name']}: its control {case['control']} cannot read it")


def check_never_join(cases: Iterable[dict[str, Any]], case_records: Mapping[str, Record],
                     people: Mapping[str, Principal], others: Mapping[str, Record],
                     units: Mapping[str, str], dataset: str,
                     corpus: str | None = None) -> None:  # fmt: skip
    cases = list(cases)
    if corpus is not None:
        _check_words(cases, corpus)
    for case in cases:
        partner = others[case["hidden"]]
        _opens(people, PART, units[dataset], case, "the part-cleared")
        _opens(people, case["control"], units[partner.dataset], case, "its control")
        if not may_read(in_dataset(people[case["control"]], partner.dataset), partner):
            raise LeakCaseRefused(
                f"{case['name']}: its control {case['control']} cannot read it in its own case"
            )
        if case["hidden"] in case_records:
            raise LeakCaseRefused(f"{case['name']}: both records are in the measure case's dataset")
        if not may_read(people[PART], case_records[case["visible"]]):
            raise LeakCaseRefused(f"{case['name']}: {PART} cannot read the record it searches by")


def _document_texts(folder: Path, source_key: str, only: set[str]) -> Iterator[str]:
    """The texts of the documents in `only`, in one pass over the source's files."""
    for path in sorted((folder / source_key).glob("*.texts.jsonl")):
        for row in _rows(path):
            if row["document_id"] in only:
                yield str(row["text"])


def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for inner in value.values():
            yield from _strings(inner)
    elif isinstance(value, list | tuple):
        for inner in value:
            yield from _strings(inner)


def visible_corpus(
    folder: Path, source_key: str, case_records: Mapping[str, Record], part: Principal
) -> str:
    """Everything `part` may read in the measure case that an answer could show, lower-cased, one
    string: each visible record's properties and each visible document's text."""
    visible = [r for r in case_records.values() if may_read(part, r)]
    parts = [s for r in visible for s in _strings(dict(r.props))]
    documents = {r.id for r in visible if r.type == "Document"}
    parts += _document_texts(folder, source_key, documents)
    return "\n".join(parts).lower()


def seen(word: str, corpus: str) -> bool:
    """Whether `word` shows in what the part-cleared reader may read, as `measure_leaks` compares
    an answer's strings: a substring, lower-cased."""
    return word.lower() in corpus


def withhold_seen_words(
    cases: list[dict[str, Any]], corpus: str
) -> tuple[list[dict[str, Any]], int]:
    """Each case with its `never_text` cut to the words nothing visible holds, and how many went."""
    kept, dropped = [], 0
    for case in cases:
        words = [w for w in case["never_text"] if not seen(w, corpus)]
        dropped += len(case["never_text"]) - len(words)
        kept.append({**case, "never_text": words})
    return kept, dropped


def _check_words(cases: Iterable[dict[str, Any]], corpus: str) -> None:
    for case in cases:
        for word in case.get("never_text", []):
            if seen(word, corpus):
                raise LeakCaseRefused(
                    f"{case['name']}: its hidden word {word!r} is in what {PART} may read, so "
                    "finding it in an answer would be no leak"
                )


def _write(path: Path, cases: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for case in cases:
            f.write(json.dumps(case, sort_keys=True) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.client_size_leaks")
    parser.add_argument("--from", dest="folder", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--case", default="intel", help="the source whose case is measured")
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args(argv)
    case_records = records(args.folder, args.case)
    dataset = next(iter(case_records.values())).dataset
    units = case_units(args.folder)
    people = subjects(dataset, units)
    leaks, leaks_out = leak_cases(case_records, people, units[dataset])
    joins, joins_out = never_join_cases(
        args.folder, case_records, people, partner_cases(args.folder), units
    )
    check_leaks(leaks, case_records, people, units[dataset])
    check_never_join(
        joins, case_records, people, records(args.folder, only={c["hidden"] for c in joins}),
        units, dataset,
    )  # fmt: skip
    eligible = (len(leaks), len(joins))
    leaks, joins = _sample(leaks, "hidden", args.limit), _sample(joins, "hidden", args.limit)
    corpus = visible_corpus(args.folder, args.case, case_records, people[PART])
    leaks, leaks_dropped = withhold_seen_words(leaks, corpus)
    joins, joins_dropped = withhold_seen_words(joins, corpus)
    check_leaks(leaks, case_records, people, units[dataset], corpus)
    check_never_join(
        joins, case_records, people, records(args.folder, only={c["hidden"] for c in joins}),
        units, dataset, corpus,
    )  # fmt: skip
    used = sorted({PART, *(c["control"] for c in (*leaks, *joins))})
    args.out.mkdir(parents=True, exist_ok=True)
    _write(args.out / "leaks.jsonl", leaks)
    _write(args.out / "never_join.jsonl", joins)
    counts = {
        "case": args.case, "dataset": dataset, "case_unit": units[dataset], "limit": args.limit,
        "leaks_eligible": eligible[0], "never_join_eligible": eligible[1],
        "leaks_kept_out": dict(sorted(leaks_out.items())),
        "never_join_kept_out": dict(sorted(joins_out.items())),
        "never_text_dropped": {"leaks": leaks_dropped, "never_join": joins_dropped},
        "subjects": {
            n: {"clearance": people[n].clearance, "org_unit": people[n].org_unit,
                "codes": list(people[n].receivable_handling_codes)}
            for n in used
        },
        "leaks_by_control": {c: sum(1 for x in leaks if x["control"] == c)
                             for c in sorted({x["control"] for x in leaks})},
        "never_join_by_control": {c: sum(1 for x in joins if x["control"] == c)
                                  for c in sorted({x["control"] for x in joins})},
    }  # fmt: skip
    (args.out / "counts.json").write_text(json.dumps(counts, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(counts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
