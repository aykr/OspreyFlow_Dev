"""Screening-list connectors as Knowledge Adapters (`06_DECISIONS.md` ADR-133 decision 4, stage (c);
`09_INGEST_STUDIO.md` §4: a transform is a Knowledge Adapter with golden test files, never an
expression — rule 8).

Each function reads one publisher's own export format and returns the list as `ListedParty`
entries: the publisher's own reference, sanction / PEP / adverse-media, person or organisation, the
primary name, its aliases, one exact date of birth when the list gives exactly one, and a country.
A vessel, an aircraft or a ship is neither a person nor an organisation a customer could be, so it
is counted in `skipped`, never dropped silently (rule 2). A file that is not the format is refused,
in words, with `NormalisationError` — the same rejection every Knowledge Adapter raises — and
nothing of it is kept.

**What each format is read from** (the publisher's own documentation; `00_ARCHITECTURE.md` §7 has
each licence). Where a field could not be confirmed from the publisher's documentation it is marked
*unverified* below, and the golden files follow the documented shape only:

- **OFAC SDN** (`ofac_sdn`): `SDN.CSV`, with `ALT.CSV` and `ADD.CSV` optional, per OFAC's data
  specification (dat_spec, updated 25 September 2023): no header row; twelve columns `ent_num,
  SDN_Name, SDN_Type, Program, Title, Call_Sign, Vess_type, Tonnage, GRT, Vess_flag, Vess_owner,
  Remarks`; null written `-0-`; a date of birth only inside Remarks, as `DOB 17 Jan 1941;`.
  *Unverified:* `SDN_Type` values other than `individual` (`vessel` and `aircraft` are read as
  skipped, anything null as an organisation), and a trailing end-of-file character (tolerated).
  The CSV carries no version: the version is the content's SHA-256.
- **HM Treasury OFSI consolidated list** (`ofsi_consolidated`): `ConList.csv`, per OFSI's
  *Consolidated List … Format Guide* (28 February 2022): one row per permutation of name, date of
  birth, address and regime, rows of one target sharing a `Group ID`; `Name 6` the surname or the
  entity's whole name; `DOB` dd/mm/yyyy; `Group Type` Individual, Entity or Ship; `Alias Type`
  Primary Name, Primary Name Variation, AKA or FKA. *Unverified:* a first line reading `Last
  Updated,<date>` before the header (tolerated, and its date taken as the version when present).
  Otherwise the version is the latest `Last Updated`. **The OFSI Consolidated List closed on 28
  January 2026**; the FCDO's UK Sanctions List is now the only source of UK designations (gov.uk).
- **UN Security Council consolidated list** (`un_consolidated`): `consolidated.xml`.
  *Unverified from the UN's own documentation* (its list page and schema could not be read when
  this was built): the element names `CONSOLIDATED_LIST` (`dateGenerated`, the version),
  `INDIVIDUAL`/`ENTITY`, `DATAID`, `REFERENCE_NUMBER`, `FIRST_NAME` … `FOURTH_NAME`,
  `INDIVIDUAL_ALIAS`/`ENTITY_ALIAS` `ALIAS_NAME`, `INDIVIDUAL_DATE_OF_BIRTH` (`TYPE_OF_DATE`,
  `DATE`), `NATIONALITY/VALUE`, `ENTITY_ADDRESS/COUNTRY` — taken from a secondary description.
- **EU consolidated financial sanctions list** (`eu_consolidated`): the FSF XML 1.1 export.
  *Unverified from the Commission's own schema* (its XSD refused to be read): `export`
  (`generationDate`, the version), `sanctionEntity` (`logicalId`), `subjectType` (`code` person or
  enterprise), `nameAlias` (`wholeName`), `birthdate` (`birthdate`), `citizenship` and `address`
  (`countryIso2Code`). Read by local name, whatever the namespace.
- **OpenSanctions** (`opensanctions`): `entities.ftm.json`, one FollowTheMoney entity per line, per
  OpenSanctions' bulk-data documentation: `id`, `schema`, `properties` (every property a list of
  strings: `name`, `alias`, `birthDate`, `nationality`, `country`, `topics`). Topics `sanction…`,
  `role.pep`/`role.rca`, and `crime…`/`poi`/`reg.…`/`debarment` give the listing; an entity with
  none is not a target and is skipped. `weakAlias` is not matched on, as the documentation advises.
  The version is the dataset's `version` from its `index.json` when given, else the SHA-256.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal
from xml.etree.ElementTree import Element

from defusedxml import ElementTree as DefusedET

from .errors import NormalisationError

Listing = Literal["sanction", "pep", "adverse_media"]
PartyType = Literal["Person", "Organisation"]


@dataclass(frozen=True)
class ListedParty:
    """One entry, as the screening store holds it. `ref` is the publisher's own reference."""

    ref: str
    listing: Listing
    entity_type: PartyType
    name: str
    aliases: tuple[str, ...] = ()
    date_of_birth: str | None = None
    country: str | None = None


@dataclass(frozen=True)
class ParsedList:
    format: str
    version: str
    entries: tuple[ListedParty, ...]
    #: Entries that are neither a person nor an organisation (a vessel, an aircraft, a ship), or an
    #: OpenSanctions entity that is not a target: counted, not silently dropped.
    skipped: int = 0


def _digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _refuse(adapter: str, raw: str, reason: str) -> NormalisationError:
    return NormalisationError(adapter, raw[:80], reason)


def _one_date(values: Iterable[str | None]) -> str | None:
    """A date of birth only when the list gives exactly one exact date: a second possible date, or
    a year alone, must not rule a customer out (`screening.screen`)."""
    found = {v for v in values if v}
    return found.pop() if len(found) == 1 else None


def _aliases(primary: str, names: Iterable[str]) -> tuple[str, ...]:
    seen: list[str] = []
    for name in names:
        name = name.strip()
        if name and name != primary and name not in seen:
            seen.append(name)
    return tuple(seen)


# --- OFAC SDN -------------------------------------------------------------------------------------

_OFAC = "ofac_sdn"
_OFAC_COLUMNS = 12
_OFAC_DOB = re.compile(r"\bDOB (\d{1,2} [A-Z][a-z]{2} \d{4})\b")


def _ofac_null(value: str) -> str:
    value = value.strip()
    return "" if value == "-0-" else value


def _ofac_rows(text: str, adapter: str, width: int, name: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for number, row in enumerate(csv.reader(io.StringIO(text)), start=1):
        if not row or (len(row) == 1 and row[0].strip() in ("", "\x1a")):
            continue  # a blank line, or the end-of-file character (unverified, tolerated)
        if len(row) != width:
            raise _refuse(
                adapter,
                ",".join(row),
                f"line {number} of {name} has {len(row)} fields; OFAC's specification gives "
                f"{width} — this is not {name}",
            )
        if not _ofac_null(row[0]).isdigit():
            raise _refuse(adapter, row[0], f"line {number} of {name} has no entry number (ent_num)")
        rows.append([_ofac_null(v) for v in row])
    return rows


def _ofac_dob(remarks: str) -> str | None:
    found = []
    for match in _OFAC_DOB.findall(remarks):
        try:
            found.append(datetime.strptime(match, "%d %b %Y").date().isoformat())
        except ValueError:
            continue
    return _one_date(found)


def ofac_sdn(sdn_csv: str, *, alt_csv: str | None = None, add_csv: str | None = None) -> ParsedList:
    """OFAC's Specially Designated Nationals list from `SDN.CSV`, with its aliases (`ALT.CSV`) and
    addresses (`ADD.CSV`) when given. Every entry is a sanction."""
    rows = _ofac_rows(sdn_csv, _OFAC, _OFAC_COLUMNS, "SDN.CSV")
    if not rows:
        raise _refuse(_OFAC, sdn_csv, "SDN.CSV holds no entries")
    aliases: dict[str, list[str]] = defaultdict(list)
    for row in _ofac_rows(alt_csv or "", _OFAC, 5, "ALT.CSV"):
        aliases[row[0]].append(row[3])
    countries: dict[str, str] = {}
    for row in _ofac_rows(add_csv or "", _OFAC, 6, "ADD.CSV"):
        if row[4]:
            countries.setdefault(row[0], row[4])
    entries: list[ListedParty] = []
    skipped = 0
    for ent_num, name, sdn_type, *_rest, remarks in rows:
        kind = sdn_type.lower()
        if kind in ("vessel", "aircraft"):
            skipped += 1
            continue
        if not name:
            raise _refuse(_OFAC, ent_num, f"entry {ent_num} of SDN.CSV has no name")
        person = kind == "individual"
        entries.append(
            ListedParty(
                ref=ent_num,
                listing="sanction",
                entity_type="Person" if person else "Organisation",
                name=name,
                aliases=_aliases(name, aliases.get(ent_num, [])),
                date_of_birth=_ofac_dob(remarks) if person else None,
                country=countries.get(ent_num),
            )
        )
    return ParsedList(
        format=_OFAC, version=_digest(sdn_csv), entries=tuple(entries), skipped=skipped
    )


# --- HM Treasury OFSI consolidated list -----------------------------------------------------------

_OFSI = "ofsi_consolidated"
_OFSI_REQUIRED = (
    "Name 6", "Name 1", "Name 2", "Name 3", "Name 4", "Name 5", "DOB", "Nationality", "Country",
    "Group Type", "Alias Type", "Last Updated", "Group ID",
)  # fmt: skip
_OFSI_TYPES: dict[str, PartyType | None] = {"individual": "Person", "entity": "Organisation",
                                             "ship": None}  # fmt: skip


def _ofsi_date(value: str) -> str | None:
    value = value.strip()
    try:
        return datetime.strptime(value, "%d/%m/%Y").date().isoformat()
    except ValueError:
        return None  # a partly known date (`00/00/1970`, unverified) is no exact date


def _ofsi_name(row: dict[str, str], person: bool) -> str:
    surname = row["Name 6"].strip()
    if not person:
        return surname
    given = " ".join(row[f"Name {i}"].strip() for i in range(1, 6) if row[f"Name {i}"].strip())
    return f"{surname}, {given}" if given else surname


def ofsi_consolidated(conlist_csv: str) -> ParsedList:
    """HM Treasury OFSI's Consolidated List of Asset Freeze Targets from `ConList.csv`: each Group
    ID one target, its primary name and every other name as aliases. Every entry is a sanction."""
    lines = conlist_csv.lstrip("﻿").splitlines()
    stated: str | None = None
    if lines and lines[0].startswith("Last Updated"):
        stated = _ofsi_date(lines[0].split(",", 1)[1] if "," in lines[0] else "")
        lines = lines[1:]
    reader = csv.DictReader(io.StringIO("\n".join(lines)))
    header = [h.strip() for h in (reader.fieldnames or [])]
    missing = [c for c in _OFSI_REQUIRED if c not in header]
    if missing:
        raise _refuse(
            _OFSI,
            ",".join(header),
            "this is not OFSI's ConList.csv: no column " + ", ".join(f"“{c}”" for c in missing),
        )
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    updated: list[str] = []
    for number, raw in enumerate(reader, start=2):
        row = {k.strip(): (v or "") for k, v in raw.items() if k is not None}
        group = row["Group ID"].strip()
        if not group:
            raise _refuse(_OFSI, row["Name 6"], f"row {number} has no Group ID")
        if row["Group Type"].strip().lower() not in _OFSI_TYPES:
            raise _refuse(
                _OFSI,
                row["Group Type"],
                f"row {number}'s Group Type is “{row['Group Type']}”; the format guide gives "
                "Individual, Entity or Ship",
            )
        groups[group].append(row)
        if when := _ofsi_date(row["Last Updated"]):
            updated.append(when)
    if not groups:
        raise _refuse(_OFSI, conlist_csv, "ConList.csv holds no entries")
    entries: list[ListedParty] = []
    skipped = 0
    for group, rows in groups.items():
        kind = _OFSI_TYPES[rows[0]["Group Type"].strip().lower()]
        if kind is None:
            skipped += 1
            continue
        person = kind == "Person"
        primary_rows = [r for r in rows if r["Alias Type"].strip().lower() == "primary name"]
        name = _ofsi_name((primary_rows or rows)[0], person)
        country_field = "Nationality" if person else "Country"
        country = next((r[country_field].strip() for r in rows if r[country_field].strip()), None)
        entries.append(
            ListedParty(
                ref=group,
                listing="sanction",
                entity_type=kind,
                name=name,
                aliases=_aliases(name, (_ofsi_name(r, person) for r in rows)),
                date_of_birth=_one_date(_ofsi_date(r["DOB"]) for r in rows) if person else None,
                country=country,
            )
        )
    version = stated or max(updated, default=None) or _digest(conlist_csv)
    return ParsedList(format=_OFSI, version=version, entries=tuple(entries), skipped=skipped)


# --- XML, read safely and by local name -----------------------------------------------------------


def _xml(adapter: str, text: str, root: str) -> Element:
    try:
        element = DefusedET.fromstring(text)
    except Exception as error:  # noqa: BLE001 - malformed or unsafe XML, refused in words
        raise _refuse(adapter, text, f"this is not well-formed XML ({error})") from error
    if _local(element.tag) != root:
        raise _refuse(
            adapter, element.tag, f"the document's root is <{_local(element.tag)}>, not <{root}>"
        )
    return element


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _children(element: Element, name: str) -> list[Element]:
    return [c for c in element if _local(c.tag) == name]


def _descendants(element: Element, name: str) -> list[Element]:
    return [c for c in element.iter() if _local(c.tag) == name]


def _text(element: Element, name: str) -> str:
    found = _children(element, name)
    return (found[0].text or "").strip() if found else ""


# --- UN Security Council consolidated list -------------------------------------------------------

_UN = "un_consolidated"


def _iso(value: str) -> str | None:
    try:
        return date.fromisoformat(value.strip()[:10]).isoformat()
    except ValueError:
        return None


def un_consolidated(consolidated_xml: str) -> ParsedList:
    """The UN Security Council Consolidated List from `consolidated.xml`. Every entry is a
    sanction."""
    root = _xml(_UN, consolidated_xml, "CONSOLIDATED_LIST")
    version = root.get("dateGenerated", "").strip()
    if not version:
        raise _refuse(_UN, consolidated_xml, "the list says no dateGenerated, so it has no version")
    entries: list[ListedParty] = []
    for kind, tag, alias_tag in (("Person", "INDIVIDUAL", "INDIVIDUAL_ALIAS"),
                                 ("Organisation", "ENTITY", "ENTITY_ALIAS")):  # fmt: skip
        for item in _descendants(root, tag):
            data_id = _text(item, "DATAID")
            if not data_id:
                raise _refuse(_UN, tag, f"an <{tag}> has no DATAID")
            parts = [_text(item, f) for f in ("FIRST_NAME", "SECOND_NAME", "THIRD_NAME",
                                              "FOURTH_NAME")]  # fmt: skip
            name = " ".join(p for p in parts if p)
            if not name:
                raise _refuse(_UN, data_id, f"<{tag}> {data_id} has no name")
            aliases = [_text(a, "ALIAS_NAME") for a in _children(item, alias_tag)]
            if kind == "Person":
                dob = _one_date(
                    _iso(_text(d, "DATE"))
                    for d in _children(item, "INDIVIDUAL_DATE_OF_BIRTH")
                    if _text(d, "TYPE_OF_DATE").upper() == "EXACT"
                )
                nationality = [
                    v.text.strip()
                    for n in _children(item, "NATIONALITY")
                    for v in _children(n, "VALUE")
                    if v.text and v.text.strip()
                ]
                country = nationality[0] if nationality else None
            else:
                dob = None
                places = [_text(a, "COUNTRY") for a in _children(item, "ENTITY_ADDRESS")]
                country = next((p for p in places if p), None)
            entries.append(
                ListedParty(
                    ref=_text(item, "REFERENCE_NUMBER") or data_id,
                    listing="sanction",
                    entity_type=kind,  # type: ignore[arg-type]
                    name=name,
                    aliases=_aliases(name, aliases),
                    date_of_birth=dob,
                    country=country,
                )
            )
    return ParsedList(format=_UN, version=version, entries=tuple(entries))


# --- EU consolidated financial sanctions list ----------------------------------------------------

_EU = "eu_consolidated"
_EU_TYPES: dict[str, PartyType] = {"person": "Person", "enterprise": "Organisation"}


def eu_consolidated(fsf_xml: str) -> ParsedList:
    """The EU's consolidated financial sanctions list, the FSF XML 1.1 export. Every entry is a
    sanction."""
    root = _xml(_EU, fsf_xml, "export")
    version = root.get("generationDate", "").strip()
    if not version:
        raise _refuse(_EU, fsf_xml, "the export says no generationDate, so it has no version")
    entries: list[ListedParty] = []
    skipped = 0
    for item in _children(root, "sanctionEntity"):
        ref = (item.get("logicalId") or item.get("euReferenceNumber") or "").strip()
        if not ref:
            raise _refuse(_EU, "sanctionEntity", "a <sanctionEntity> has no logicalId")
        subject = _children(item, "subjectType")
        code = (subject[0].get("code") or "").strip().lower() if subject else ""
        kind = _EU_TYPES.get(code)
        if kind is None:
            skipped += 1
            continue
        names = [(a.get("wholeName") or "").strip() for a in _children(item, "nameAlias")]
        names = [n for n in names if n]
        if not names:
            raise _refuse(_EU, ref, f"<sanctionEntity> {ref} has no nameAlias with a wholeName")
        if kind == "Person":
            dob = _one_date(_iso(b.get("birthdate") or "") for b in _children(item, "birthdate"))
            places = [
                (c.get("countryIso2Code") or "").strip() for c in _children(item, "citizenship")
            ]
        else:
            dob = None
            places = [(c.get("countryIso2Code") or "").strip() for c in _children(item, "address")]
        entries.append(
            ListedParty(
                ref=ref,
                listing="sanction",
                entity_type=kind,
                name=names[0],
                aliases=_aliases(names[0], names[1:]),
                date_of_birth=dob,
                country=next((p for p in places if p and p != "00"), None),
            )
        )
    return ParsedList(format=_EU, version=version, entries=tuple(entries), skipped=skipped)


# --- OpenSanctions (FollowTheMoney entities) -----------------------------------------------------

_OS = "opensanctions"
_OS_TYPES: dict[str, PartyType] = {"Person": "Person", "Organization": "Organisation",
                                    "Company": "Organisation", "LegalEntity": "Organisation",
                                    "PublicBody": "Organisation"}  # fmt: skip


def _os_listing(topics: Iterable[str]) -> Listing | None:
    found = set(topics)
    if any(t == "sanction" or t.startswith("sanction.") and t != "sanction.counter" for t in found):
        return "sanction"
    if found & {"role.pep", "role.rca"}:
        return "pep"
    if any(t.startswith(("crime", "reg.")) or t in ("poi", "debarment") for t in found):
        return "adverse_media"
    return None


def _strings(props: dict[str, Any], key: str) -> list[str]:
    value = props.get(key) or []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValueError(f"the property “{key}” is not a list of strings")
    return [v.strip() for v in value if v.strip()]


def opensanctions(entities_jsonl: str, *, version: str | None = None) -> ParsedList:
    """OpenSanctions' `entities.ftm.json`, one FollowTheMoney entity per line. Only a person or an
    organisation with a sanction, PEP or adverse topic is an entry; every other entity is skipped
    and counted."""
    entries: list[ListedParty] = []
    skipped = 0
    for number, line in enumerate(entities_jsonl.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            entity = json.loads(line)
        except json.JSONDecodeError as error:
            raise _refuse(_OS, line, f"line {number} is not a JSON object ({error.msg})") from error
        if not isinstance(entity, dict) or not all(
            k in entity for k in ("id", "schema", "properties")
        ):
            raise _refuse(
                _OS, line, f"line {number} is not a FollowTheMoney entity (id, schema, properties)"
            )
        props = entity["properties"]
        if not isinstance(props, dict):
            raise _refuse(_OS, line, f"line {number}'s properties are not an object")
        kind = _OS_TYPES.get(str(entity["schema"]))
        try:
            listing = _os_listing(_strings(props, "topics"))
            names = _strings(props, "name")
            aliases = _strings(props, "alias")
            births = _strings(props, "birthDate")
            places = _strings(props, "nationality") + _strings(props, "country")
        except ValueError as error:
            raise _refuse(_OS, line, f"line {number}: {error}") from error
        if kind is None or listing is None:
            skipped += 1
            continue
        name = names[0] if names else str(entity.get("caption") or "").strip()
        if not name:
            raise _refuse(_OS, line, f"line {number} ({entity['id']}) has no name")
        entries.append(
            ListedParty(
                ref=str(entity["id"]),
                listing=listing,
                entity_type=kind,
                name=name,
                aliases=_aliases(name, [*names[1:], *aliases]),
                date_of_birth=_one_date(b for b in births if re.fullmatch(r"\d{4}-\d{2}-\d{2}", b))
                if kind == "Person"
                else None,
                country=places[0].upper() if places else None,
            )
        )
    if not entries and not skipped:
        raise _refuse(_OS, entities_jsonl, "the file holds no entities")
    return ParsedList(
        format=_OS,
        version=version or _digest(entities_jsonl),
        entries=tuple(entries),
        skipped=skipped,
    )


#: The connectors a screening-list subscription may name (`services/api/screening_refresh.py`).
LIST_ADAPTERS: dict[str, Callable[..., ParsedList]] = {
    _OFAC: ofac_sdn,
    _OFSI: ofsi_consolidated,
    _UN: un_consolidated,
    _EU: eu_consolidated,
    _OS: opensanctions,
}

__all__ = [
    "LIST_ADAPTERS",
    "ListedParty",
    "ParsedList",
    "eu_consolidated",
    "ofac_sdn",
    "ofsi_consolidated",
    "opensanctions",
    "un_consolidated",
]
