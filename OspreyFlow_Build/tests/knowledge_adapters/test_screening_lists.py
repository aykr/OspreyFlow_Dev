"""Golden tests — the screening-list connectors (`spec/06_DECISIONS.md` ADR-133 decision 4, stage (c);
`09_INGEST_STUDIO.md` §4: a connector is a Knowledge Adapter with golden files, rule 8).

Each adapter reads its synthetic golden file (`golden/screening_lists/`, rule 9: invented, shaped like
the publisher's documented export) and must return exactly the entries beside it. Each is also given
what a real mistake would hand it — another publisher's file, the successor list's CSV, a header row
where the format has none, a file cut short — and must refuse it in words, keeping nothing (rule 15:
the stand-in refuses what the real format would not be).
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from knowledge_adapters.errors import NormalisationError
from knowledge_adapters.screening_lists import (
    LIST_ADAPTERS,
    ParsedList,
    eu_consolidated,
    ofac_sdn,
    ofsi_consolidated,
    opensanctions,
    uk_sanctions_list,
    un_consolidated,
)

GOLDEN = Path(__file__).parent / "golden" / "screening_lists"


def _read(name: str) -> str:
    return (GOLDEN / name).read_text(encoding="utf-8")


def _as_expected(parsed: ParsedList, *, with_version: bool = True) -> dict[str, object]:
    out: dict[str, object] = {
        "format": parsed.format,
        "skipped": parsed.skipped,
        "entries": [{**asdict(e), "aliases": list(e.aliases)} for e in parsed.entries],
    }
    if with_version:
        out["version"] = parsed.version
    return out


def _expected(name: str) -> dict[str, object]:
    return json.loads(_read(name))  # type: ignore[no-any-return]


# --- each adapter against its golden file -------------------------------------------------------


def test_ofac_sdn_reads_its_golden_file() -> None:
    parsed = ofac_sdn(
        _read("ofac_sdn.SDN.CSV"), alt_csv=_read("ofac_sdn.ALT.CSV"), add_csv=_read("ofac_sdn.ADD.CSV")
    )
    assert _as_expected(parsed, with_version=False) == _expected("ofac_sdn.expected.json")
    # SDN.CSV says no version: its content's digest is the version, so any change is a new one.
    assert parsed.version.startswith("sha256:")
    assert ofac_sdn(_read("ofac_sdn.SDN.CSV")).version == parsed.version
    changed = _read("ofac_sdn.SDN.CSV").replace("PETROVA, Elena", "PETROVA, Yelena")
    assert ofac_sdn(changed).version != parsed.version


def test_ofsi_consolidated_reads_its_golden_file() -> None:
    assert _as_expected(ofsi_consolidated(_read("ofsi_consolidated.csv"))) == _expected(
        "ofsi_consolidated.expected.json"
    )


def test_ofsi_takes_a_stated_last_updated_line_as_the_version() -> None:
    stated = "Last Updated,28/01/2026\n" + _read("ofsi_consolidated.csv")
    assert ofsi_consolidated(stated).version == "2026-01-28"


def test_un_consolidated_reads_its_golden_file() -> None:
    assert _as_expected(un_consolidated(_read("un_consolidated.xml"))) == _expected(
        "un_consolidated.expected.json"
    )


def test_eu_consolidated_reads_its_golden_file() -> None:
    assert _as_expected(eu_consolidated(_read("eu_consolidated.xml"))) == _expected(
        "eu_consolidated.expected.json"
    )


def test_opensanctions_reads_its_golden_file() -> None:
    parsed = opensanctions(_read("opensanctions.ftm.json"), version="20261030091500-syn")
    assert _as_expected(parsed) == _expected("opensanctions.expected.json")
    # A weak alias is not matched on (OpenSanctions' own advice): it is not among the aliases.
    assert "Lena" not in parsed.entries[0].aliases


def test_uk_sanctions_list_reads_its_golden_file() -> None:
    # ADR-133 Amendment 6: a ship is counted and not screened; a partial or a second possible date
    # of birth is no exact date; a designation known by its OFSI Group ID alone keeps it; one
    # UniqueID on a second designation (another regime) is the same entry, its name an alias.
    assert _as_expected(uk_sanctions_list(_read("uk_sanctions_list.xml"))) == _expected(
        "uk_sanctions_list.expected.json"
    )


def test_every_connector_is_offered_by_name() -> None:
    assert sorted(LIST_ADAPTERS) == [
        "eu_consolidated", "ofac_sdn", "ofsi_consolidated", "opensanctions", "uk_sanctions_list",
        "un_consolidated",
    ]  # fmt: skip


# --- what each refuses, in words ------------------------------------------------------------------


def _refused(call, *args: object, **kwargs: object) -> str:  # type: ignore[no-untyped-def]
    with pytest.raises(NormalisationError) as raised:
        call(*args, **kwargs)
    return raised.value.reason


def test_ofac_refuses_a_header_row_its_format_does_not_have() -> None:
    header = "ent_num,SDN_Name,SDN_Type,Program,Title,Call_Sign,Vess_type,Tonnage,GRT,Vess_flag,Vess_owner,Remarks\r\n"
    reason = _refused(ofac_sdn, header + _read("ofac_sdn.SDN.CSV"))
    assert "line 1 of SDN.CSV has no entry number" in reason


def test_ofac_refuses_a_row_of_the_wrong_width() -> None:
    cut = '9101,"PETROVA, Elena","individual","SYN-PROG",-0- ,-0- \r\n'
    assert "has 6 fields; OFAC's specification gives 12" in _refused(ofac_sdn, cut)
    # ADD.CSV handed in as ALT.CSV: six fields where five are expected.
    assert "ALT.CSV" in _refused(
        ofac_sdn, _read("ofac_sdn.SDN.CSV"), alt_csv=_read("ofac_sdn.ADD.CSV")
    )


def test_ofac_refuses_an_empty_file() -> None:
    assert _refused(ofac_sdn, "") == "SDN.CSV holds no entries"


def test_ofsi_refuses_the_uk_sanctions_lists_csv_by_the_columns_it_lacks() -> None:
    # The FCDO's UK Sanctions List (OFSI's successor since 28 January 2026) names its columns
    # differently: "Unique ID", "Name type", "Regime Name", "OFSI Group ID".
    uksl = (
        "Last Updated,Unique ID,OFSI Group ID,UN Reference Number,Name 6,Name 1,Name 2,Name 3,"
        "Name 4,Name 5,Name type,Alias strength,Title,Regime Name\n"
        "27/01/2026,SYN0001,90001,,PETROVA,Elena,,,,,Primary Name,,,Synthetic Regime\n"
    )
    reason = _refused(ofsi_consolidated, uksl)
    assert reason.startswith("this is not OFSI's ConList.csv: no column")
    assert "“Group ID”" in reason and "“Alias Type”" in reason and "“DOB”" in reason


def test_ofsi_refuses_a_group_type_its_guide_does_not_give() -> None:
    bad = _read("ofsi_consolidated.csv").replace(",Entity,Primary name,", ",Aircraft,Primary name,")
    assert "Group Type is “Aircraft”" in _refused(ofsi_consolidated, bad)


def test_ofsi_refuses_a_row_with_no_group_id() -> None:
    lines = _read("ofsi_consolidated.csv").splitlines()
    lines[1] = lines[1].rsplit(",", 1)[0] + ","
    assert _refused(ofsi_consolidated, "\n".join(lines)) == "row 2 has no Group ID"


def test_un_refuses_the_eu_export_and_anything_not_xml() -> None:
    assert "root is <export>, not <CONSOLIDATED_LIST>" in _refused(
        un_consolidated, _read("eu_consolidated.xml")
    )
    assert "not well-formed XML" in _refused(un_consolidated, _read("un_consolidated.xml")[:400])


def test_un_refuses_a_list_with_no_date_generated() -> None:
    undated = _read("un_consolidated.xml").replace(' dateGenerated="2026-10-30T09:15:00.000Z"', "")
    assert "no dateGenerated" in _refused(un_consolidated, undated)


def test_eu_refuses_the_un_list_and_an_entity_with_no_name() -> None:
    assert "root is <CONSOLIDATED_LIST>, not <export>" in _refused(
        eu_consolidated, _read("un_consolidated.xml")
    )
    nameless = _read("eu_consolidated.xml").replace(
        '<nameAlias wholeName="Northwind Metals FZE" strong="true" logicalId="5"/>', ""
    )
    assert "800002 has no nameAlias" in _refused(eu_consolidated, nameless)


def test_xml_with_entity_expansion_is_refused_not_expanded() -> None:
    bomb = (
        '<?xml version="1.0"?><!DOCTYPE l [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;">]>'
        '<CONSOLIDATED_LIST dateGenerated="x">&b;</CONSOLIDATED_LIST>'
    )
    assert "not well-formed XML" in _refused(un_consolidated, bomb)


def test_opensanctions_refuses_the_csv_export_and_a_malformed_entity() -> None:
    csv_export = "id,schema,name,aliases,birth_date,countries\nsyn-os-0001,Person,Elena Petrova,,,\n"
    assert _refused(opensanctions, csv_export).startswith("line 1 is not a JSON object")
    not_lists = '{"id": "x", "schema": "Person", "properties": {"name": "Elena Petrova", "topics": ["sanction"]}}'
    assert "“name” is not a list of strings" in _refused(opensanctions, not_lists)
    assert "not a FollowTheMoney entity" in _refused(opensanctions, '{"name": "Elena"}')


# --- the UK Sanctions List (FCDO), ADR-133 Amendment 6 -------------------------------------------


def test_uk_sanctions_list_refuses_the_other_lists_files() -> None:
    assert "root is <CONSOLIDATED_LIST>, not <Designations>" in _refused(
        uk_sanctions_list, _read("un_consolidated.xml")
    )
    assert "root is <export>, not <Designations>" in _refused(
        uk_sanctions_list, _read("eu_consolidated.xml")
    )
    # The closed OFSI list's CSV, handed to the successor's connector by mistake.
    assert "not well-formed XML" in _refused(uk_sanctions_list, _read("ofsi_consolidated.csv"))


def test_uk_sanctions_list_refuses_a_list_with_no_date_generated() -> None:
    undated = _read("uk_sanctions_list.xml").replace("<DateGenerated>30/10/2026</DateGenerated>", "")
    assert "no DateGenerated" in _refused(uk_sanctions_list, undated)


def test_uk_sanctions_list_refuses_a_designation_it_cannot_name_or_place() -> None:
    nameless = _read("uk_sanctions_list.xml").replace(
        "<Name><Name6>NORTHWIND METALS FZE</Name6><NameType>Primary Name</NameType></Name>", ""
    ).replace(
        "<Name><Name6>NORTHWIND METAL TRADING</Name6><NameType>Primary Name Variation</NameType></Name>",
        "",
    )
    assert _refused(uk_sanctions_list, nameless) == "<Designation> SYN0003 has no name"
    aircraft = _read("uk_sanctions_list.xml").replace(
        "<IndividualEntityShip>Ship</IndividualEntityShip>",
        "<IndividualEntityShip>Aircraft</IndividualEntityShip>",
    )
    assert "IndividualEntityShip “Aircraft”" in _refused(uk_sanctions_list, aircraft)
    unidentified = _read("uk_sanctions_list.xml").replace("<OFSIGroupID>90005</OFSIGroupID>", "")
    assert "has no UniqueID and no OFSIGroupID" in _refused(uk_sanctions_list, unidentified)


def test_uk_sanctions_list_refuses_entity_expansion() -> None:
    bomb = (
        '<?xml version="1.0"?><!DOCTYPE l [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;">]>'
        "<Designations><DateGenerated>&b;</DateGenerated></Designations>"
    )
    assert "not well-formed XML" in _refused(uk_sanctions_list, bomb)
