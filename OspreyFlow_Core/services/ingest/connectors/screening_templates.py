"""The screening-list connector's mapping templates (`06_DECISIONS.md` ADR-140 Amendment 9
decision 3; Amendment 13).

One template per known format maps a publisher's file to **the one screening shape**
(`staging_catalogue.SCREENING_COLUMNS`: the publisher's reference, primary name, aliases, date of
birth, nationality, identifiers, programme, listing, entity type). A format's template reads the
file through its Knowledge Adapter (`knowledge_adapters.screening_lists`, each with its own golden
files), so a template adds no parsing of its own. A list no template covers, such as a client's own
CSV, is mapped by the **blank** template: each screening field is one of the file's columns, picked
by name, and many values in one cell are split on a separator chosen from a closed set. Nothing here
evaluates text (rule 8).

**Nothing is dropped silently** (rule 2). A row the blank template cannot map (no reference, no
name, a party type it cannot tell, an alias holding the shape's own separator) refuses the
**whole list**, naming each such row by its number and never by its content (rule 7): a screening
list missing one listed party would screen as clean the very party it lists. A format adapter's
skipped entries (a vessel, an aircraft) are counted, as the adapter counts them.

Every golden file is synthetic (rule 9): `tests/connectors/golden/`.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping
from dataclasses import dataclass, field

from knowledge_adapters.errors import NormalisationError
from knowledge_adapters.screening_lists import LIST_ADAPTERS, ListedParty
from schemas.list_connector import BlankListMapping, ListTemplate

from ..staging_catalogue import SCREENING_COLUMNS

#: The shape's own separator for many values in one cell, as `staging_catalogue` writes them.
_MANY = "|"

#: Each template's name in words, for a refusal.
TEMPLATE_WORDS: dict[str, str] = {
    "ofac_sdn": "OFAC SDN",
    "ofsi_consolidated": "OFSI consolidated",
    "uk_sanctions_list": "UK Sanctions List",
    "un_consolidated": "UN consolidated",
    "eu_consolidated": "EU consolidated",
    "opensanctions": "OpenSanctions",
    "blank": "blank",
}

#: The files a template reads, by role: `main` always; OFAC's companions when they are there.
_FILES: dict[str, tuple[str, ...]] = {"ofac_sdn": ("main", "alt_csv", "add_csv")}

_PARTY_WORDS = {"person": "Person", "organisation": "Organisation", "organization": "Organisation"}


class TemplateRefused(Exception):
    """The file could not be mapped by its template, in words; nothing of it is kept."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("; ".join(problems))


@dataclass(frozen=True)
class MappedList:
    """A file in the one screening shape: its rows, in file order, and what was counted."""

    rows: list[dict[str, object]]
    #: The publisher's own version, when its format states one; else `None`.
    version_hint: str | None = None
    skipped: int = 0
    notes: list[str] = field(default_factory=list)


def template_files(template: ListTemplate | str) -> tuple[str, ...]:
    """The roles of the files a template reads."""
    return _FILES.get(template, ("main",))


def _row(party: ListedParty) -> dict[str, object]:
    return {
        "ref": party.ref,
        "primary_name": party.name,
        "aliases": _MANY.join(party.aliases) or None,
        "date_of_birth": party.date_of_birth,
        "nationality": party.country,
        "identifiers": None,
        "programme": None,
        "listing": party.listing,
        "entity_type": party.entity_type,
    }


def _text(files: Mapping[str, bytes], role: str, words: str) -> str:
    try:
        return files[role].decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise TemplateRefused([f"the {words} file is not UTF-8 text; nothing was read"]) from exc


def _format(template: str, files: Mapping[str, bytes]) -> MappedList:
    words = TEMPLATE_WORDS[template]
    if "main" not in files:
        raise TemplateRefused([f"the {words} template needs its list's file"])
    main = _text(files, "main", words)
    extras = {r: _text(files, r, words) for r in template_files(template)[1:] if r in files}
    try:
        parsed = LIST_ADAPTERS[template](main, **extras)
    except NormalisationError as exc:
        raise TemplateRefused(
            [f"the file is not one the {words} template can read: {exc}; nothing was read"]
        ) from exc
    for party in parsed.entries:
        if any(_MANY in alias for alias in party.aliases):
            raise TemplateRefused(
                [f"an alias of entry {party.ref} holds {_MANY!r}, which separates aliases"]
            )
    notes = [f"{parsed.skipped} entries neither a person nor an organisation were not read"]
    return MappedList(
        rows=[_row(p) for p in parsed.entries],
        version_hint=parsed.version,
        skipped=parsed.skipped,
        notes=notes if parsed.skipped else [],
    )


def _many(cell: str | None, separator: str) -> list[str]:
    if not cell:
        return []
    return [v.strip() for v in cell.split(separator) if v.strip()]


def _blank(files: Mapping[str, bytes], mapping: BlankListMapping) -> MappedList:
    if "main" not in files:
        raise TemplateRefused(["the blank template needs the list's file"])
    reader = csv.DictReader(io.StringIO(_text(files, "main", "list's")))
    header = [h.strip() for h in (reader.fieldnames or [])]
    reader.fieldnames = header
    picked = {
        "ref": mapping.ref,
        "primary_name": mapping.primary_name,
        "aliases": mapping.aliases,
        "date_of_birth": mapping.date_of_birth,
        "nationality": mapping.nationality,
        "identifiers": mapping.identifiers,
        "programme": mapping.programme,
        "entity_type": mapping.entity_type_column,
    }
    lacking = [c for c in picked.values() if c is not None and c not in header]
    if lacking:
        raise TemplateRefused(
            [
                f"the file has no column {c!r}, which the mapping picks"
                for c in dict.fromkeys(lacking)
            ]  # noqa: E501
        )

    def cell(row: Mapping[str, str | None], field_name: str) -> str | None:
        column = picked[field_name]
        value = (row.get(column) or "").strip() if column else ""
        return value or None

    rows: list[dict[str, object]] = []
    problems: list[str] = []
    seen: set[str] = set()
    for number, raw in enumerate(reader, start=1):
        ref, name = cell(raw, "ref"), cell(raw, "primary_name")
        if ref is None:
            problems.append(f"row {number} has no reference")
        if name is None:
            problems.append(f"row {number} has no name")
        party = mapping.entity_type
        if mapping.entity_type_column is not None:
            party = _PARTY_WORDS.get((cell(raw, "entity_type") or "").lower())  # type: ignore[assignment]
            if party is None:
                problems.append(f"row {number} does not say Person or Organisation")
        aliases = _many(cell(raw, "aliases"), mapping.separator)
        identifiers = _many(cell(raw, "identifiers"), mapping.separator)
        if any(_MANY in v for v in aliases + identifiers):
            problems.append(
                f"row {number} holds {_MANY!r} in a name or number, which separates them"
            )
        if ref is not None and ref in seen:
            problems.append(f"row {number} repeats an earlier row's reference")
        if ref is not None:
            seen.add(ref)
        rows.append(
            {
                "ref": ref,
                "primary_name": name,
                "aliases": _MANY.join(aliases) or None,
                "date_of_birth": cell(raw, "date_of_birth"),
                "nationality": cell(raw, "nationality"),
                "identifiers": _MANY.join(identifiers) or None,
                "programme": cell(raw, "programme"),
                "listing": mapping.listing,
                "entity_type": party,
            }
        )
    if problems:
        raise TemplateRefused(problems + ["nothing of the list was kept"])
    return MappedList(rows=rows)


def screening_rows(
    template: ListTemplate, files: Mapping[str, bytes], mapping: BlankListMapping | None = None
) -> MappedList:
    """The file (and, for OFAC, its companions) mapped by its template to the screening shape."""
    if template == "blank":
        if mapping is None:
            raise TemplateRefused(["the blank template needs the list's own mapping"])
        mapped = _blank(files, mapping)
    else:
        mapped = _format(template, files)
    for row in mapped.rows:
        assert tuple(row) == SCREENING_COLUMNS
    return mapped
