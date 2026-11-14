"""Step 4's leak cases (M10, ADR-149 Amendment 2) from a generated client-size set (`v052-load`).

    python -m scripts.client_size_leaks --from DIR --out FOLDER [--case intel] [--limit 500]

Two JSON-lines files, for `scripts.measure_search.measure_leaks`, each case a search in the measure
case (the source `--case` names; the intelligence reports by default, where `m10-measure` draws and
`m10-part` reads):

- **`leaks.jsonl`**: a record of the measure case's own dataset that the part-cleared principal
  (`m10-part`) may not read, by its marking (SECRET, or a restricted code of another unit). The
  query finds it; its id, and its distinguishing words (its title or name, where no record that
  principal may read in the case has the same), must appear nowhere in that principal's answer;
  and `control` names the cleared subject that must find it (the one of its owning unit, for a
  restricted code), or the case proves nothing.
- **`never_join.jsonl`**: each planted SAME_AS candidate that truly joins (`truth` `same`) a record
  the part-cleared principal reads in the measure case to a record of another dataset. Searched by
  the visible record's name, the other's id (and its spelling, where no visible record has it) must
  never be returned nor merged in (ADR-099 Amendment 2: no join across cases). No control: no
  principal searching this case reaches the other dataset.

Visibility is the product's own rule (`ontology.handling.principal_may_read`, the three axes),
asked of the principals the subjects stand for (`SUBJECTS`, as granted on stack d,
`process/lanes/rules/v052-load/B_RECORD.md`). Before anything is written every case is checked
(`check_leaks`, `check_never_join`): a hidden record the part-cleared principal could read, or a
control that could not, is refused, so the file never holds a case that passes by proving nothing.
At most `--limit` cases a list, chosen by a hash of each record's id (the same set every run); the
counts of every eligible case are printed and written to `counts.json` beside them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ontology.handling import load_uk_le_scheme, principal_may_read
from schemas.domain import Handling, Principal

SCHEME = load_uk_le_scheme()
#: The units owning code-R records in the set (`client_size_plan`'s markings).
RESTRICTED_UNITS = ("unit-fiu", "unit-intel-covert", "unit-covert", "unit-border")
PART = "m10-part"


def subjects(dataset: str) -> dict[str, Principal]:
    """Each M10 subject as the Conduit would resolve it reading the measure case (its datasets the
    case's own), with the claims step 4's issuer gives it."""
    cleared = {
        f"m10-cleared-{unit}": Principal(
            id=f"m10-cleared-{unit}", clearance="SECRET", org_unit=unit,
            receivable_handling_codes=["P", "C", "R"], datasets=[dataset],
        )
        for unit in RESTRICTED_UNITS
    }  # fmt: skip
    part = Principal(
        id=PART, clearance="OFFICIAL-SENSITIVE", org_unit="unit-records",
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


def control_for(record: Record, cleared: Mapping[str, Principal]) -> str | None:
    """The cleared subject that reads `record`: its owning unit's for a restricted code, else the
    first that may."""
    own = f"m10-cleared-{record.handling.owning_unit}"
    if own in cleared and may_read(cleared[own], record):
        return own
    return next((name for name, p in cleared.items() if may_read(p, record)), None)


def _sample(items: Iterable[dict[str, Any]], key: str, limit: int) -> list[dict[str, Any]]:
    ranked = sorted(items, key=lambda c: hashlib.sha256(c[key].encode()).hexdigest())
    return sorted(ranked[:limit], key=lambda c: c[key])


def leak_cases(
    case_records: Mapping[str, Record], people: Mapping[str, Principal]
) -> list[dict[str, Any]]:
    part = people[PART]
    cleared = {n: p for n, p in people.items() if n != PART}
    seen_words = {r.words for r in case_records.values() if may_read(part, r)}
    cases = []
    for record in case_records.values():
        if may_read(part, record) or not record.words:
            continue
        control = control_for(record, cleared)
        if control is None:
            continue  # nobody granted reads it: it is no case
        cases.append({
            "name": f"hidden {record.type} {record.id} ({record.handling.classification}/"
                    f"{record.handling.handling_code}, {record.handling.owning_unit})",
            "route": "search", "query": record.words, "never_ids": [record.id],
            "never_text": [] if record.words in seen_words else [record.words],
            "control": control, "hidden": record.id,
        })  # fmt: skip
    return cases


def never_join_cases(
    folder: Path, case_records: Mapping[str, Record], people: Mapping[str, Principal]
) -> list[dict[str, Any]]:
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
    cases = []
    for pair_id, mine_id, other_id in pairs:
        other = others[other_id]
        cases.append({
            "name": f"never joined: {mine_id} and {other_id} ({pair_id})",
            "route": "search", "query": visible[mine_id].words, "never_ids": [other_id],
            "never_text": [] if other.words in seen_words else [other.words],
            "control": None, "visible": mine_id, "hidden": other_id,
            "other_dataset": other.dataset,
        })  # fmt: skip
    return cases


class LeakCaseRefused(ValueError):
    """A case that would pass by proving nothing: its hidden record readable by the principal it
    is hidden from, or not readable by its control."""


def check_leaks(cases: Iterable[dict[str, Any]], case_records: Mapping[str, Record],
                people: Mapping[str, Principal]) -> None:  # fmt: skip
    for case in cases:
        record = case_records[case["hidden"]]
        if may_read(people[PART], record):
            raise LeakCaseRefused(
                f"{case['name']}: {PART} may read {record.id}, so it hides nothing"
            )
        if not may_read(people[case["control"]], record):
            raise LeakCaseRefused(f"{case['name']}: its control {case['control']} cannot read it")


def check_never_join(cases: Iterable[dict[str, Any]], case_records: Mapping[str, Record],
                     people: Mapping[str, Principal]) -> None:  # fmt: skip
    for case in cases:
        if case["hidden"] in case_records:
            raise LeakCaseRefused(f"{case['name']}: both records are in the measure case's dataset")
        if not may_read(people[PART], case_records[case["visible"]]):
            raise LeakCaseRefused(f"{case['name']}: {PART} cannot read the record it searches by")


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
    people = subjects(dataset)
    leaks = leak_cases(case_records, people)
    joins = never_join_cases(args.folder, case_records, people)
    check_leaks(leaks, case_records, people)
    check_never_join(joins, case_records, people)
    args.out.mkdir(parents=True, exist_ok=True)
    _write(args.out / "leaks.jsonl", _sample(leaks, "hidden", args.limit))
    _write(args.out / "never_join.jsonl", _sample(joins, "hidden", args.limit))
    counts = {
        "case": args.case, "dataset": dataset, "limit": args.limit,
        "leaks_eligible": len(leaks), "never_join_eligible": len(joins),
        "leaks_by_control": {c: sum(1 for x in leaks if x["control"] == c)
                             for c in sorted({x["control"] for x in leaks})},
    }  # fmt: skip
    (args.out / "counts.json").write_text(json.dumps(counts, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(counts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
