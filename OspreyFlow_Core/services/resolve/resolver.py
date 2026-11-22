"""Runs Splink over one entity type's source-fidelity nodes and returns scored candidate pairs —
`01_DOMAIN_MODEL.md` §4, `03_CONDUIT_MIDDLEWARE.md` §5.3. Pure with respect to the graph: `Node`s
in, candidates out, no `GraphPort` I/O here (`same_as_writer.py` is the one write path) — the same
"pure function over a bounded working set" shape ADR-007 already established for the Working-Set
Service's own projection, just a new caller.

Deterministic identifiers bypass this entirely, one layer up: this module is only ever called for
an entity type the ontology declares a `resolution` block for (`Person`, currently) — a type like
`Endpoint`, matched deterministically at ingest on `value_normalised`
(`09_INGEST_STUDIO.md` §4), has no `resolution` block and this module is never invoked for it.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import pandas as pd
import splink
from splink.duckdb.linker import DuckDBLinker

from schemas.domain import EntityTypeDef, Node, NodeId, PropertyType

from . import duckdb_setup
from .splink_config import CONFIG_VERSION, blocking_columns, build_settings, comparison_columns

MODEL_VERSION = f"splink-{splink.__version__}-config-{CONFIG_VERSION}"


@dataclass(frozen=True)
class SameAsCandidate:
    node_a: NodeId
    node_b: NodeId
    score: float
    #: Per-comparison Splink `gamma_<column>` levels plus the overall `match_weight` — the "full
    #: comparison vector" `01_DOMAIN_MODEL.md` §4 and `03_CONDUIT_MIDDLEWARE.md` §5.3 both name,
    #: and what Stage 5's `explain` endpoint reads back.
    comparison_vector: dict[str, Any]


@dataclass(frozen=True)
class SkippedRecord:
    """A record the run left out of the comparison, and why (C249): named by id, property and a
    typed reason, never by the value (a date of birth is `sensitivity: high`, and a record the
    reader may not see is never in the population this names)."""

    node_id: NodeId
    property: str
    #: `not_an_iso_date` / `not_an_iso_datetime`: the property's declared type is a date (or a
    #: date and time) and the record's value is not one in ISO form.
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {"node_id": self.node_id, "property": self.property, "reason": self.reason}


@dataclass(frozen=True)
class ResolutionOutcome:
    candidates: list[SameAsCandidate]
    #: Every record left out, in the population's order. Never empty-by-silence: a run that skips a
    #: record says so (rule 2's spirit).
    skipped: list[SkippedRecord]


def resolve_entity_type(nodes: Sequence[Node], entity_type: EntityTypeDef) -> list[SameAsCandidate]:
    """The scored candidate pairs alone, for a caller with no run result to carry a note (the demo
    fixture). A record with a value that cannot be cast is left out of the comparison, as in
    `resolve_entity_type_with_skips`, which the production trigger calls and which names each."""
    return resolve_entity_type_with_skips(nodes, entity_type).candidates


def resolve_entity_type_with_skips(
    nodes: Sequence[Node], entity_type: EntityTypeDef
) -> ResolutionOutcome:
    """C249. A record whose date (or date and time) property does not parse as ISO is left out of
    the comparison and named in the outcome; it used to raise `ValueError` out of the cast, so one
    bad record failed the whole type's run, the worker rolled back and marked the job failed, and
    every good record went unresolved."""
    if entity_type.resolution is None:
        return ResolutionOutcome([], [])

    settings = build_settings(entity_type)
    comparison_cols = comparison_columns(entity_type)
    # The DataFrame Splink reads from needs every column *either* block references — not only
    # comparison columns. Found as a latent bug, not by inspection alone: `Person`'s own ontology
    # config happens to compare every column it also blocks on, which is exactly what let this
    # go unnoticed until checked directly — a hypothetical entity type blocking on a column it
    # never compares would otherwise get a DuckDB "column does not exist" error the first time
    # anyone configured one.
    all_columns = list(dict.fromkeys([*blocking_columns(entity_type), *comparison_cols]))
    property_types = {p.name: p.type for p in entity_type.properties}
    df, skipped = _nodes_to_dataframe(nodes, all_columns, property_types)
    if len(df) < 2:
        return ResolutionOutcome([], skipped)

    con = duckdb_setup.new_connection()
    try:
        linker = DuckDBLinker(df, settings, connection=con)
        predictions = linker.predict()
        return ResolutionOutcome(
            _extract_candidates(predictions.as_pandas_dataframe(), comparison_cols), skipped
        )
    finally:
        con.close()


def _nodes_to_dataframe(
    nodes: Sequence[Node], columns: Sequence[str], property_types: dict[str, PropertyType]
) -> tuple[pd.DataFrame, list[SkippedRecord]]:
    """One row per node, `unique_id` plus every column a blocking rule or comparison references —
    cast to a real Python `date`/`datetime` for `PropertyType.DATE`/`DATETIME` columns, not left
    as strings, and casefolded for `PropertyType.STRING` columns. Both were found, not designed
    for in advance, checking real predictions against hand-labelled pairs before trusting
    untrained defaults (`06_DECISIONS.md` ADR-021's no-EM-training addendum):

    - Confirmed directly: DuckDB does not implicitly cast `VARCHAR` for `year(...)` (`Binder
      Error: No function matches ... year(VARCHAR)`), but infers `DATE` correctly from an actual
      `datetime.date` value in the source DataFrame.
    - Confirmed directly: `jaro_winkler_similarity('MERCER', 'Mercer')` is `0.44`, not `1.0` —
      DuckDB's string-similarity functions are case-sensitive, so `"MERCER MERCER, Dana, 1980"`
      and `"Mercer, Dana, 1980"` predicted as a near-certain *non*-match (`0.0001`) purely on
      casing, despite `soundex()` (used for blocking) already normalising case internally. Without
      this, a source rendering a name in Title Case and a source rendering it in Caps would never
      resolve to each other regardless of how identical the underlying identity is."""
    rows: list[dict[str, Any]] = []
    skipped: list[SkippedRecord] = []
    for node in nodes:
        row: dict[str, Any] = {"unique_id": node.id}
        for column in columns:
            try:
                row[column] = _cast_or_skip(node.properties.get(column), property_types.get(column))
            except _Uncastable as refused:
                # C249: the record is left out and named, never compared on a guess and never the
                # reason a whole type's run fails.
                skipped.append(SkippedRecord(node.id, column, refused.reason))
                break
        else:
            rows.append(row)
    if len(rows) < 2:
        # Nothing to compare (every record skipped, or one left): the caller says so, and the
        # all-empty temporal columns below need a frame with columns to fix.
        return pd.DataFrame(rows), skipped
    frame = pd.DataFrame(rows)
    # A date column empty in every row (a population whose every source had no such column) is
    # all `None`, which DuckDB types as INTEGER: `year(date_of_birth)` then cannot bind, and the
    # whole type's run failed (v0.6.0's package test, `Binder Error: ... 'year(INTEGER)'`). A
    # datetime dtype of nothing but `NaT` reaches DuckDB as a TIMESTAMP of NULLs, which binds.
    for column in columns:
        temporal = property_types.get(column) in (PropertyType.DATE, PropertyType.DATETIME)
        if temporal and frame[column].isna().all():
            frame[column] = pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns]")
    return frame, skipped


class _Uncastable(Exception):
    """A value that does not parse as its declared type: the record is skipped, with this reason."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _cast_or_skip(value: Any, prop_type: PropertyType | None) -> Any:
    if value is None or prop_type is None:
        return value
    if prop_type is PropertyType.DATE and isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise _Uncastable("not_an_iso_date") from exc
    if prop_type is PropertyType.DATETIME and isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError as exc:
            raise _Uncastable("not_an_iso_datetime") from exc
    if prop_type is PropertyType.STRING and isinstance(value, str):
        return value.casefold()
    return value


def _extract_candidates(predictions: pd.DataFrame, columns: Sequence[str]) -> list[SameAsCandidate]:
    gamma_columns = [f"gamma_{c}" for c in columns if f"gamma_{c}" in predictions.columns]
    candidates: list[SameAsCandidate] = []
    for row in predictions.to_dict("records"):
        vector = {"match_weight": row["match_weight"]}
        vector.update({col: row[col] for col in gamma_columns})
        candidates.append(
            SameAsCandidate(
                node_a=row["unique_id_l"],
                node_b=row["unique_id_r"],
                score=float(row["match_probability"]),
                comparison_vector=vector,
            )
        )
    return candidates


def comparison_vector_json(candidate: SameAsCandidate) -> str:
    """JSON-encoded, for `SAME_AS.comparison_vector` — a `STRING` property
    (`packages/ontology/loader.py`'s `_SYSTEM_EDGE_PROPERTIES`), since `PropertyType` has no
    generic object/JSON type."""
    return json.dumps(candidate.comparison_vector, sort_keys=True)
