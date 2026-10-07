"""ADR-101: ArcadeDB 26 sends a Gremlin map as `{"result": [{"key", "value"}, ...]}`, 25.5.1 as the
map itself. The adapter reads the second shape everywhere, so the client turns the first into it.
What a mistake would do: every `elementMap()` read on 26.10.1 fails on a missing `id` (measured:
83 of 114 graph conformance cases), or, if the record id won over the `id` property, every node
read back under its storage RID instead of its own id (the last case)."""

from __future__ import annotations

from adapters.graph_arcadedb.client import _gremlin_row


def _entries(**pairs: object) -> list[dict[str, object]]:
    return [{"key": k, "value": v} for k, v in pairs.items()]


def test_a_map_sent_as_entries_reads_as_the_map() -> None:
    row = {"result": _entries(label="mx_Person", reverted=False)}
    assert _gremlin_row(row) == {"label": "mx_Person", "reverted": False}


def test_a_nested_map_reads_as_a_map_too() -> None:
    row = {"result": _entries(node=_entries(label="mx_Person"), degree=3)}
    assert _gremlin_row(row) == {"node": {"label": "mx_Person"}, "degree": 3}


def test_a_scalar_and_a_map_already_a_dict_are_left_alone() -> None:
    assert _gremlin_row({"result": 6}) == {"result": 6}
    assert _gremlin_row({"id": "n1", "label": "mx_Person"}) == {"id": "n1", "label": "mx_Person"}
    assert _gremlin_row({"result": []}) == {"result": []}


def test_the_id_property_wins_over_the_record_id() -> None:
    # `elementMap()` on 26.10.1: T.id ("#1:0") first, then the `id` property.
    row = {"result": [{"key": "id", "value": "#1:0"}, {"key": "label", "value": "mx_Person"},
                      {"key": "id", "value": "01M4BC4VP1CRQEJKHSQEWKDFSP"}]}
    assert _gremlin_row(row)["id"] == "01M4BC4VP1CRQEJKHSQEWKDFSP"
