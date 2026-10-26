"""ADR-127 decision 5: the key a kept row is remembered by must be unambiguous.

`dedup_key` hashes an encoding of the canonicalised key parts. A join on a separator made two
different rows one key (`("a|b", "c")` and `("a", "b|c")`), and the text `"None"` the same key as an
absent part; with keys kept for good, a distinct row would be skipped on every later run. The parts
are now a JSON list of strings (a fixed order, the definition's own; `ensure_ascii=False`; fixed
separators), and a row with an empty or unresolved part is **unkeyed**: it loads every time and
keeps no key, which is what the engine already does for a part that does not resolve. The golden
values below are the hashes of the exact encodings, so a change to the encoding fails here, not in a
store that has already kept keys under the old one."""

from __future__ import annotations

from hashlib import sha256

import pytest
from services.ingest.engine import dedup_fingerprint, dedup_key, encode_key_parts
from services.ingest.transforms import connector_params_in_use

from schemas.ingest import DeduplicateConfig, FieldBinding

A, B = FieldBinding(field="a"), FieldBinding(field="b")


def _hash(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def test_the_encoding_is_a_json_list_of_strings_and_its_hash_is_the_golden_one() -> None:
    assert encode_key_parts(["a", "b"]) == _hash('["a","b"]')
    assert encode_key_parts(["a"]) == _hash('["a"]')
    assert encode_key_parts(["é", "日本"]) == _hash('["é","日本"]'), "not escaped to ASCII"


def test_two_rows_that_a_separator_would_have_made_one_key_are_two() -> None:
    first = dedup_key({"a": "a|b", "b": "c"}, [A, B])
    second = dedup_key({"a": "a", "b": "b|c"}, [A, B])
    assert first is not None and second is not None and first != second
    assert encode_key_parts(["a|b", "c"]) != encode_key_parts(["a", "b|c"])
    # Nor does a quote or a bracket in a value run into the next part.
    assert encode_key_parts(['a","b']) != encode_key_parts(["a", "b"])


def test_the_text_none_is_not_an_absent_part() -> None:
    assert encode_key_parts(["None"]) == _hash('["None"]'), "the text is a key like any other"
    assert encode_key_parts([None]) is None, "an absent part is unkeyed"
    assert encode_key_parts(["a", None]) is None


def test_an_empty_part_is_unkeyed_not_a_key_of_the_empty_string() -> None:
    assert encode_key_parts([""]) is None
    assert encode_key_parts(["a", ""]) is None
    assert encode_key_parts([" "]) == _hash('[" "]'), "only truly empty is empty"


def test_a_part_that_does_not_resolve_is_unkeyed_as_before() -> None:
    """The engine already treats a key field that fails to resolve as unkeyed (its own singleton
    group, rejected by the normal per-row resolution with the real reason)."""
    assert dedup_key({"a": "x"}, [A, B]) is None, "b is missing"
    assert dedup_key({"a": "x", "b": ""}, [A, B]) is None, "b is empty"
    assert dedup_key({"a": "x", "b": "y"}, [A, B]) is not None


def test_the_order_of_the_definition_is_the_order_of_the_key() -> None:
    row = {"a": "1", "b": "2"}
    assert dedup_key(row, [A, B]) != dedup_key(row, [B, A])


def test_a_datetime_part_is_the_utc_instant_to_the_second() -> None:
    bind = [FieldBinding(field="t", transform="datetime")]
    one = dedup_key({"t": "2026-03-10T10:00:00Z"}, bind)
    other = dedup_key({"t": "2026-03-10 10:00:00+00:00"}, bind)
    assert one is not None and one == other, "two spellings of one instant are one key (§7 rule 2)"


def test_a_rows_key_does_not_change_with_the_columns_it_does_not_name() -> None:
    assert dedup_key({"a": "x", "b": "y", "c": "1"}, [A, B]) == dedup_key(
        {"a": "x", "b": "y", "c": "2"}, [A, B]
    )


# --- the fingerprint of a definition (a new version must not re-key rows already loaded) ---------


def _config(*bindings: FieldBinding) -> DeduplicateConfig:
    return DeduplicateConfig(key=list(bindings))


def test_the_same_definition_has_the_same_fingerprint() -> None:
    assert dedup_fingerprint(_config(A, B)) == dedup_fingerprint(_config(A, B))
    assert dedup_fingerprint(_config(FieldBinding(field="a", transform="msisdn"))) == (
        dedup_fingerprint(_config(FieldBinding(transform="msisdn", field="a")))
    )


@pytest.mark.parametrize(
    "changed",
    [
        _config(A),
        _config(B, A),
        _config(A, B, FieldBinding(field="c")),
        _config(FieldBinding(field="a", transform="msisdn"), B),
        _config(FieldBinding(field="a", map={"x": "y"}), B),
        _config(A, FieldBinding(field="c")),
    ],
    ids=["fewer fields", "reordered", "more fields", "a transform", "a map", "another field"],
)
def test_any_change_to_what_makes_a_key_changes_the_fingerprint(changed: DeduplicateConfig) -> None:
    assert dedup_fingerprint(changed) != dedup_fingerprint(_config(A, B))


def test_the_fingerprint_is_a_hash_of_a_fixed_encoding() -> None:
    assert dedup_fingerprint(_config(A)) == _hash('[{"field":"a"}]')


# --- the connector settings that feed a key part are part of the definition ----------------------

DATE = FieldBinding(field="when", transform="datetime")


def test_the_connector_date_order_a_datetime_key_part_uses_is_in_the_fingerprint() -> None:
    config = _config(A, DATE)
    dmy = dedup_fingerprint(config, {"date_order": "dmy", "source_crs": None})
    mdy = dedup_fingerprint(config, {"date_order": "mdy", "source_crs": None})
    assert dmy != mdy
    assert dmy != dedup_fingerprint(config, {"date_order": None, "source_crs": None})


def test_the_source_crs_a_coordinate_key_part_uses_is_in_the_fingerprint() -> None:
    config = _config(FieldBinding(field="lat", transform="coordinate_lat"))
    assert dedup_fingerprint(config, {"source_crs": "EPSG:4326"}) != dedup_fingerprint(
        config, {"source_crs": "EPSG:27700"}
    )


def test_a_setting_no_key_part_uses_is_not_in_the_fingerprint() -> None:
    plain = _config(A, DATE)
    assert dedup_fingerprint(plain, {"date_order": "dmy", "source_crs": "EPSG:4326"}) == (
        dedup_fingerprint(plain, {"date_order": "dmy", "source_crs": "EPSG:27700"})
    )
    # A key with no transform uses no setting at all, and keeps its golden fingerprint.
    assert dedup_fingerprint(_config(A), {"date_order": "mdy", "source_crs": "x"}) == _hash(
        '[{"field":"a"}]'
    )


def test_an_order_the_transform_names_itself_overrides_the_connectors_and_is_not_its_setting() -> (
    None
):
    named = _config(FieldBinding(field="when", transform="datetime(date_order=dmy)"))
    assert dedup_fingerprint(named, {"date_order": "dmy"}) == dedup_fingerprint(
        named, {"date_order": "mdy"}
    )
    assert connector_params_in_use("datetime(date_order=dmy)") == ()
    assert connector_params_in_use("datetime") == ("date_order",)
    assert connector_params_in_use("datetime(part=x)") == ("date_order",)
    assert connector_params_in_use("msisdn") == ()
    assert connector_params_in_use("not a transform!") == ()


def test_a_fields_binding_uses_the_settings_of_its_transform_too() -> None:
    pair = _config(FieldBinding(fields=["lon", "lat"], transform="coordinate_lon"))
    assert dedup_fingerprint(pair, {"source_crs": "a"}) != dedup_fingerprint(
        pair, {"source_crs": "b"}
    )
