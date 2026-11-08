"""Each screening-list template maps its synthetic golden file to the one screening shape
(`06_DECISIONS.md` ADR-140 Amendment 9 decision 3; Amendment 13; rule 9: every file invented).

What a mistake would do, and the case that catches it:
- a template that drops aliases, a date of birth or a nationality on the way to the screening shape,
  so a listed party is screened on its primary name alone —
  `test_each_format_template_maps_its_golden_file` (per template);
- the blank template reading a column other than the one picked, or splitting many values wrongly —
  `test_the_blank_template_maps_its_golden_file`;
- a client's row with no reference or no name, or a party type the mapping cannot tell, dropped
  silently (rule 2): the whole list refused instead, naming the rows by number, never their
  content (rule 7) — `test_a_row_the_blank_template_cannot_map_refuses_the_list_by_its_row`;
- a mapped column the file does not have read as empty —
  `test_a_column_the_file_lacks_is_refused_by_name`;
- an alias that holds the screening shape's own separator, which would split one name into two —
  `test_an_alias_holding_the_separator_is_refused`;
- a template offered that no adapter reads — `test_every_template_but_blank_is_an_adapter`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import get_args

import pytest
from services.ingest.connectors.screening_templates import (
    TemplateRefused,
    screening_rows,
    template_files,
)
from services.ingest.staging_catalogue import SCREENING_COLUMNS

from knowledge_adapters.screening_lists import LIST_ADAPTERS
from schemas.list_connector import BlankListMapping, ListTemplate

HERE = Path(__file__).parent / "golden"
INPUTS = Path(__file__).parents[1] / "knowledge_adapters" / "golden" / "screening_lists"

#: Each format's synthetic input, by the file role its template reads.
FORMAT_INPUTS: dict[str, dict[str, str]] = {
    "ofac_sdn": {"main": "ofac_sdn.SDN.CSV", "alt_csv": "ofac_sdn.ALT.CSV",
                 "add_csv": "ofac_sdn.ADD.CSV"},
    "ofsi_consolidated": {"main": "ofsi_consolidated.csv"},
    "uk_sanctions_list": {"main": "uk_sanctions_list.xml"},
    "un_consolidated": {"main": "un_consolidated.xml"},
    "eu_consolidated": {"main": "eu_consolidated.xml"},
    "opensanctions": {"main": "opensanctions.ftm.json"},
}  # fmt: skip


def _files(template: str) -> dict[str, bytes]:
    return {role: (INPUTS / name).read_bytes() for role, name in FORMAT_INPUTS[template].items()}


def _golden(name: str) -> list[dict[str, object]]:
    return json.loads((HERE / name).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _mapping() -> BlankListMapping:
    text = (HERE / "blank_client_list.mapping.json").read_text()
    return BlankListMapping.model_validate_json(text)


@pytest.mark.parametrize("template", sorted(FORMAT_INPUTS))
def test_each_format_template_maps_its_golden_file(template: str) -> None:
    mapped = screening_rows(template, _files(template))  # type: ignore[arg-type]
    assert mapped.rows == _golden(f"{template}.screening.json")
    for row in mapped.rows:
        assert tuple(row) == SCREENING_COLUMNS


def test_the_blank_template_maps_its_golden_file() -> None:
    files = {"main": (HERE / "blank_client_list.csv").read_bytes()}
    mapped = screening_rows("blank", files, _mapping())
    assert mapped.rows == _golden("blank_client_list.screening.json")
    assert mapped.skipped == 0


def test_every_template_but_blank_is_an_adapter() -> None:
    templates = set(get_args(ListTemplate))
    assert templates - {"blank"} == set(LIST_ADAPTERS)
    assert set(FORMAT_INPUTS) == templates - {"blank"}
    assert template_files("ofac_sdn") == ("main", "alt_csv", "add_csv")


def _blank(text: str, **mapping: object) -> list[dict[str, object]]:
    base: dict[str, object] = {"ref": "id", "primary_name": "name"}
    base.update(mapping)
    return screening_rows(
        "blank", {"main": text.encode()}, BlankListMapping.model_validate(base)
    ).rows


def test_a_row_the_blank_template_cannot_map_refuses_the_list_by_its_row() -> None:
    with pytest.raises(TemplateRefused) as refused:
        _blank("id,name\nA1,Secret Person\n,Nameless Ref\nA3,\n")
    words = str(refused.value)
    assert "row 2" in words and "row 3" in words
    assert "Nameless" not in words and "Secret" not in words
    with pytest.raises(TemplateRefused) as typed:
        _blank("id,name,kind\nA1,Someone,vessel\n", entity_type=None, entity_type_column="kind")
    assert "row 1" in str(typed.value) and "vessel" not in str(typed.value)


def test_a_column_the_file_lacks_is_refused_by_name() -> None:
    with pytest.raises(TemplateRefused, match="Born"):
        _blank("id,name\nA1,Someone\n", date_of_birth="Born")


def test_an_alias_holding_the_separator_is_refused() -> None:
    with pytest.raises(TemplateRefused, match="row 1"):
        _blank("id,name,aka\nA1,Someone,One|Two\n", aliases="aka", separator=";")


def test_a_format_file_the_template_cannot_read_is_refused_in_words() -> None:
    with pytest.raises(TemplateRefused, match="OFAC SDN"):
        screening_rows("ofac_sdn", {"main": b"not,an,sdn,file\n"})
