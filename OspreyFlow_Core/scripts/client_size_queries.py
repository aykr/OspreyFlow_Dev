"""Step 4's search query set (M1, M3, M4, M5; ADR-149 Amendment 2) from a generated client-size set.

    python -m scripts.client_size_queries --from DIR --out FOLDER [--case intel] [--per-class 200]
                                          [--seed 4]

One JSON-lines file, `queries.jsonl`, read by `scripts.measure_search` and
`tests/perf/test_search_budget_live.py`, each row a query `m10-measure` sends in the measure case
(the source `--case` names; the intelligence reports by default). The runner reads `class`, `query`
and, by class, `expect_first` or `filters`; `from` (the record the row was drawn from) is for the
check below and for a reader of the file, and is not read by the runner.

- **`suggest`** (M1): a 2 to 6 character prefix of a Person's first given name or family name, as
  the source spells it.
- **`names`** (M3): a Person's name ("given family") with one change, a third each: a keying slip
  (`client_size_plan.slip`), a sound-alike (`client_size_plan.sound_alike`), or a spelling variant
  (another spelling of the forename or surname from its group, `client_size_plan.FORENAME_GROUPS`
  and `SURNAME_GROUPS`, as B's generator spells the same person in other records). A change of case
  or word order alone is refused: the search folds both, so it would time an exact name.
- **`fulltext`** (M4): a phrase of 2 to 6 words from a document's text, with `filters` naming the
  case's dataset and dates bracketing the document's `sent_at` ("with a dataset and a date filter").
- **`exact`** (M5): a phone number as a person types it (its `value_raw` or its E.164), whose
  `expect_first` is the graph's node id of the one record holding it (the load keeps a generated
  row's id as its node id, `load_client_size.node_writes`).

Every row is drawn from a record `m10-measure` may read in the case (the product's own rule,
`ontology.handling.principal_may_read`; the subjects at the source's OS/C and only the OS/C
documents) and checked before anything is written (`check_queries`): a row from a record it cannot
read, an exact row whose `expect_first` is not the one visible record holding its number, or a class
with fewer than `--per-class` rows is refused, so the file never times a query that finds nothing
the measured principal may see. The rows are chosen by a hash of the seed, the class and each
record's id, so a seed gives the same file every run; `counts.json` beside it records the seed, each
class's count and eligible count, and the manifest's SHA-256.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from scripts import client_size_plan as plan
from scripts.client_size_leaks import Record, may_read, records

from schemas.domain import Principal
from schemas.search import MAX_QUERY_CHARS

MEASURE = "m10-measure"
CLASSES = ("suggest", "names", "fulltext", "exact")
#: The search's own floor for a suggestion (`SUGGEST_MIN_CHARS`), and the contract's ceiling.
PREFIX_CHARS = (2, 6)
PHRASE_WORDS = (2, 6)
#: How far either side of a document's day its date filter reaches, at most.
DATE_SLACK_DAYS = 30
DEFAULT_SEED = 4


class QuerySetRefused(ValueError):
    """A row that would time a query proving nothing, or a class too small to time."""


def measure_principal(dataset: str) -> Principal:
    """`m10-measure` as the Conduit resolves it reading the measure case (as granted on stack d,
    `process/lanes/rules/v052-load/B_RECORD.md`)."""
    return Principal(
        id=MEASURE, clearance="OFFICIAL-SENSITIVE", org_unit="unit-intel",
        receivable_handling_codes=["P", "C"], datasets=[dataset],
    )  # fmt: skip


def _rng(seed: int, *where: object) -> random.Random:
    return random.Random(":".join(str(w) for w in (seed, *where)))


def _ranked(ids: Iterable[str], seed: int, kind: str) -> list[str]:
    return sorted(ids, key=lambda i: hashlib.sha256(f"{seed}:{kind}:{i}".encode()).hexdigest())


def _first_given(record: Record) -> str:
    return str(record.props.get("given_names") or "").split(" ")[0]


def _family(record: Record) -> str:
    return str(record.props.get("family_name") or "")


# --- Drawing each class ---------------------------------------------------------------------------


def suggest_row(record: Record, seed: int) -> dict[str, Any] | None:
    r = _rng(seed, "suggest", record.id)
    name = r.choice([n for n in (_first_given(record), _family(record)) if n] or [""])
    if len(name) < PREFIX_CHARS[0]:
        return None
    length = r.randint(PREFIX_CHARS[0], min(PREFIX_CHARS[1], len(name)))
    return {"class": "suggest", "query": name[:length], "from": record.id}


CHANGES = ("slip", "sound_alike", "variant")


def _variant(given: str, family: str, kind: str, r: random.Random) -> str:
    if kind == "slip":
        return f"{given} {plan.slip(family, r)}"
    if kind == "sound_alike":
        # The family name where a rule applies to it, else the given name.
        heard = plan.sound_alike(family, r)
        return f"{given} {heard}" if heard != family else f"{plan.sound_alike(given, r)} {family}"
    # Another spelling of the same name in its group, as B's generator gives other records of the
    # same person (`client_size_plan.spell`'s "variant"), never one differing only in case.
    options = [(a, family) for a in _alternatives(given, plan.FORENAME_GROUPS)] + [
        (given, a) for a in _alternatives(family, plan.SURNAME_GROUPS)
    ]
    if not options:
        return f"{given} {family}"
    other_given, other_family = r.choice(options)
    return f"{other_given} {other_family}"


def _alternatives(name: str, groups: Sequence[Sequence[str]]) -> list[str]:
    for group in groups:
        if name in group:
            return [a for a in group if a.casefold() != name.casefold()]
    return []


def _folded(name: str) -> list[str]:
    """A name as an analyser that folds case and word order reads it."""
    return sorted(name.casefold().split())


def names_row(record: Record, seed: int, kind: str) -> dict[str, Any] | None:
    """A changed name of the change `kind`, or None where it leaves the name as it is (an exact
    match is not M3's; the caller draws the next person for the same change, so the three stay a
    third each)."""
    given, family = _first_given(record), _family(record)
    if not given or not family:
        return None
    query = _variant(given, family, kind, _rng(seed, "names", record.id))
    if _folded(query) == _folded(f"{given} {family}"):
        return None
    return {"class": "names", "query": query, "change": kind, "from": record.id}


_WORD_EDGE = re.compile(r"^\W+|\W+$")


def fulltext_row(record: Record, text: str, seed: int) -> dict[str, Any] | None:
    words = text.split()
    if len(words) < PHRASE_WORDS[0]:
        return None
    r = _rng(seed, "fulltext", record.id)
    for _attempt in range(8):
        length = r.randint(PHRASE_WORDS[0], min(PHRASE_WORDS[1], len(words)))
        start = r.randrange(len(words) - length + 1)
        phrase = _WORD_EDGE.sub("", " ".join(words[start : start + length]))
        # A phrase of short words alone ("of the") finds nearly everything and measures little.
        if any(len(_WORD_EDGE.sub("", w)) >= 4 for w in phrase.split()):
            break
    else:
        return None
    day = _sent_day(record)
    before, after = r.randint(0, DATE_SLACK_DAYS), r.randint(0, DATE_SLACK_DAYS)
    filters = {
        "datasets": [record.dataset],
        "date_from": (day - timedelta(days=before)).isoformat(),
        "date_to": (day + timedelta(days=after)).isoformat(),
    }
    return {"class": "fulltext", "query": phrase, "filters": filters, "from": record.id}


def _sent_day(record: Record) -> date:
    return datetime.strptime(str(record.props["sent_at"]), "%Y-%m-%dT%H:%M:%SZ").date()


def _numbers(record: Record) -> list[str]:
    p = record.props
    return [str(v) for v in (p.get("value_raw"), p.get("e164")) if v]


def exact_row(record: Record, seed: int) -> dict[str, Any] | None:
    forms = _numbers(record)
    if not forms:
        return None
    query = _rng(seed, "exact", record.id).choice(forms)
    return {"class": "exact", "query": query, "expect_first": record.id, "from": record.id}


# --- Reading the set ------------------------------------------------------------------------------


def _is_number(record: Record) -> bool:
    return record.type == "Endpoint" and record.props.get("endpoint_kind") == "msisdn"


def texts(folder: Path, source_key: str, only: set[str]) -> dict[str, str]:
    """Each document's text, for the documents in `only`, in one pass over the source's files."""
    out: dict[str, str] = {}
    for path in sorted((folder / source_key).glob("*.texts.jsonl")):
        with path.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    row = json.loads(line)
                    if row["document_id"] in only:
                        out[row["document_id"]] = row["text"]
    return out


def build(
    case_records: Mapping[str, Record],
    case_texts: Mapping[str, str],
    measure: Principal,
    *,
    seed: int,
    per_class: int,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Up to `per_class` rows a class, each from a record `measure` reads, and each class's count
    of eligible records."""
    visible = {i: r for i, r in case_records.items() if may_read(measure, r)}
    people = [i for i, r in visible.items() if r.type == "Person"]
    documents = [i for i, r in visible.items() if r.type == "Document" and i in case_texts]
    numbers = [i for i, r in visible.items() if _is_number(r)]
    held = _holders(visible.values())
    unique_numbers = [i for i in numbers if all(len(held[v]) == 1 for v in _numbers(visible[i]))]
    draws: dict[str, tuple[list[str], Any]] = {
        "suggest": (people, lambda i, _n: suggest_row(visible[i], seed)),
        "names": (people, lambda i, n: names_row(visible[i], seed, CHANGES[n % 3])),
        "fulltext": (documents, lambda i, _n: fulltext_row(visible[i], case_texts[i], seed)),
        "exact": (unique_numbers, lambda i, _n: exact_row(visible[i], seed)),
    }
    rows: list[dict[str, Any]] = []
    eligible: dict[str, int] = {}
    for kind in CLASSES:
        ids, draw = draws[kind]
        eligible[kind] = len(ids)
        taken = 0
        for record_id in _ranked(ids, seed, kind):
            if taken == per_class:
                break
            row = draw(record_id, taken)
            if row is not None:
                rows.append(row)
                taken += 1
    return rows, eligible


def _holders(recs: Iterable[Record]) -> dict[str, set[str]]:
    """Each written number (either form) and the visible records holding it."""
    out: dict[str, set[str]] = {}
    for r in recs:
        for value in _numbers(r):
            out.setdefault(value, set()).add(r.id)
    return out


def check_queries(
    rows: Sequence[dict[str, Any]],
    case_records: Mapping[str, Record],
    case_texts: Mapping[str, str],
    measure: Principal,
    *,
    per_class: int,
) -> None:
    """Refuse a row that would prove nothing timed, and a class with fewer than `per_class` rows."""
    visible = [r for r in case_records.values() if may_read(measure, r)]
    held = _holders(visible)
    for row in rows:
        kind, query = row.get("class"), row.get("query")
        if kind not in CLASSES:
            raise QuerySetRefused(f"a row of class {kind!r}: the classes are {', '.join(CLASSES)}")
        if not isinstance(query, str) or not query.strip() or len(query) > MAX_QUERY_CHARS:
            raise QuerySetRefused(
                f"a {kind} row's query {query!r} is empty or over the search's cap"
            )
        record = case_records.get(row.get("from", ""))
        if record is None:
            raise QuerySetRefused(f"the {kind} row {query!r} names no record of the measure case")
        if not may_read(measure, record):
            raise QuerySetRefused(
                f"the {kind} row {query!r} is drawn from {record.id} "
                f"({record.handling.classification}/{record.handling.handling_code}), "
                f"which {MEASURE} cannot read, so it times a query for a record it may not see"
            )
        _check_class(kind, row, record, case_texts, held)
    counts = {k: sum(1 for r in rows if r["class"] == k) for k in CLASSES}
    short = {k: n for k, n in counts.items() if n < per_class}
    if short:
        raise QuerySetRefused(
            "too few rows to time, "
            + ", ".join(f"{k} {n}" for k, n in short.items())
            + f", where each class needs {per_class} (the runner would repeat queries)"
        )


def _check_class(
    kind: str,
    row: dict[str, Any],
    record: Record,
    case_texts: Mapping[str, str],
    held: Mapping[str, set[str]],
) -> None:
    query = row["query"]
    if kind == "suggest":
        names = [_first_given(record), _family(record)]
        if not PREFIX_CHARS[0] <= len(query) <= PREFIX_CHARS[1] or not any(
            n.startswith(query) for n in names
        ):
            raise QuerySetRefused(
                f"the suggest row {query!r} is not a 2 to 6 character prefix of {record.id}'s names"
            )
    elif kind == "names":
        if record.type != "Person" or _folded(query) == _folded(
            f"{_first_given(record)} {_family(record)}"
        ):
            raise QuerySetRefused(
                f"the names row {query!r} is not a changed name of a Person "
                "(a change of case or word order alone is the name itself to the search)"
            )
    elif kind == "fulltext":
        text = case_texts.get(record.id, "")
        f = row.get("filters") or {}
        day = _sent_day(record)
        if record.type != "Document" or " ".join(query.split()) not in " ".join(text.split()):
            raise QuerySetRefused(
                f"the fulltext row {query!r} is not a phrase of {record.id}'s text"
            )
        low, high = f.get("date_from"), f.get("date_to")
        if (
            f.get("datasets") != [record.dataset]
            or not isinstance(low, str)
            or not isinstance(high, str)
            or not date.fromisoformat(low) <= day <= date.fromisoformat(high)
        ):
            raise QuerySetRefused(
                f"the fulltext row {query!r} lacks a dataset and a date filter holding {record.id}"
            )
    elif kind == "exact":
        expected = row.get("expect_first")
        if expected != record.id or query not in _numbers(record):
            raise QuerySetRefused(
                f"the exact row {query!r} does not name its expect_first {expected!r}"
            )
        if held.get(query, set()) != {record.id}:
            raise QuerySetRefused(
                f"the exact row {query!r} names {len(held.get(query, set()))} visible records, "
                "so none can be expected first"
            )


# --- The command ----------------------------------------------------------------------------------


def _write(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _documents(case_records: Mapping[str, Record]) -> Iterator[str]:
    return (i for i, r in case_records.items() if r.type == "Document")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.client_size_queries")
    parser.add_argument("--from", dest="folder", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--case", default="intel", help="the source whose case is measured")
    parser.add_argument("--per-class", type=int, default=200)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args(argv)
    case_records = records(args.folder, args.case)
    dataset = next(iter(case_records.values())).dataset
    measure = measure_principal(dataset)
    readable = {i for i in _documents(case_records) if may_read(measure, case_records[i])}
    case_texts = texts(args.folder, args.case, readable)
    rows, eligible = build(
        case_records, case_texts, measure, seed=args.seed, per_class=args.per_class
    )
    check_queries(rows, case_records, case_texts, measure, per_class=args.per_class)
    args.out.mkdir(parents=True, exist_ok=True)
    _write(args.out / "queries.jsonl", rows)
    counts = {
        "case": args.case, "dataset": dataset, "principal": MEASURE, "seed": args.seed,
        "per_class": args.per_class,
        "counts": {k: sum(1 for r in rows if r["class"] == k) for k in CLASSES},
        "eligible": eligible,
        "names_by_change": {c: sum(1 for r in rows if r.get("change") == c)
                            for c in CHANGES},
        "manifest_sha256": _sha256(args.folder / "manifest.json"),
    }  # fmt: skip
    (args.out / "counts.json").write_text(json.dumps(counts, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(counts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
