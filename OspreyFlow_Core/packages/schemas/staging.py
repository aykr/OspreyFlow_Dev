"""Staging steps: the recipe's `staging:` list (ADR-140 decision 11; `09_INGEST_STUDIO.md` §9;
redesign brief §6; the redesign's phase 7).

A pipeline's staging steps sit between its source tables and Map. Each step reads one or more
**tables** by name and gives one table, named by the step's `id`. A table name is either one of the
pipeline's source tables (the name its rows are given to the engine under) or an earlier step's
`id`. **The last step is the table Map reads**; every earlier step must feed a later one, so no step
is dangling (`services/ingest/staging_catalogue.staging_rule_violations`).

The catalogue is closed (rule 8): Lookup, Join, Filter, Derive, Union, Dedupe. Each is a declared
record, and every value-changing part of it is a Knowledge Adapter with a golden file: a Join's
normalised key names an adapter from `knowledge_adapters.REGISTRY`, a Derive names an operation from
`knowledge_adapters.derive.DERIVE_OPERATIONS`. No field anywhere holds an expression, and an
unknown key is refused (`extra="forbid"`), so a step cannot smuggle one in under a new name. The
expert steps (SQL transform, fuzzy match) are phase 8's and are not in this union.

Provenance: every staged row carries its `source_refs`, one per input row it came from (a Join two,
a Union one, a Dedupe's survivor those of every row it stood for), and the element Map writes from
it lists one `SourceRef` per ref in its `provenance.sources` (the orchestrator's settlement of 8
November 2026, Q2 (a)).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

#: A step's id, which later steps read it by: lower-case, as a YAML key reads plainly.
StepId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")]
#: A table a step reads: a source table's name or an earlier step's id.
TableName = Annotated[str, Field(min_length=1, max_length=128)]
#: A column of a table.
ColumnName = Annotated[str, Field(min_length=1, max_length=256)]

#: Derive's catalogue (`knowledge_adapters.derive.DERIVE_OPERATIONS`; brief §6), as the schema
#: refuses anything else. `tests/knowledge_adapters/test_derive.py` holds the two lists equal.
DeriveOperation = Literal[
    "concat", "split", "substring", "date_parse", "arithmetic", "case_when", "normalise"
]


class _Step(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: StepId
    #: Plain words for the canvas and the run report; optional.
    label: str | None = None


class AddedColumn(BaseModel):
    """A column a Lookup or a Join brings across, optionally renamed."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    column: ColumnName
    as_: ColumnName | None = Field(default=None, alias="as")


class LookupStep(_Step):
    """Add columns from a reference list on a key: every row of `input` is kept, and a row whose
    key is not in the list keeps empty cells for the added columns (counted, never dropped). The
    list is the dataset's own, or a screening list the dataset subscribes to (ADR-140 Amendment 9
    decision 3); its key column is the list's own `key_column`."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    kind: Literal["lookup"]
    input: TableName
    #: The reference list, by name (`list:` in the YAML).
    list_: str = Field(alias="list", min_length=1)
    #: The column of `input` whose value is looked up in the list's key column.
    on: ColumnName
    #: A Knowledge Adapter both sides are read through before they are compared; `None` = exact.
    normalise: str | None = None
    add: list[AddedColumn] = Field(min_length=1)


class JoinStep(_Step):
    """Join two tables on a declared key, never a guessed one (brief §6): exact, or each side read
    through the same Knowledge Adapter first (E.164, prison number, IBAN…). A row of `left` with
    several matches gives one row per match, each carrying both sides' refs."""

    kind: Literal["join"]
    left: TableName
    right: TableName
    left_key: ColumnName
    right_key: ColumnName
    normalise: str | None = None
    how: Literal["inner", "left"] = "inner"
    #: The right table's columns brought across; the left table's are all kept.
    add: list[AddedColumn] = Field(min_length=1)


class FilterCondition(BaseModel):
    """One declared condition on a column: exactly one of `is`, `equals` or `in`."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    field: ColumnName
    is_: Literal["not_null", "null"] | None = Field(default=None, alias="is")
    equals: str | None = None
    in_: list[str] | None = Field(default=None, alias="in", min_length=1)

    @model_validator(mode="after")
    def _exactly_one(self) -> FilterCondition:
        given = [
            n
            for n, v in (("is", self.is_), ("equals", self.equals), ("in", self.in_))
            if v is not None
        ]
        if len(given) != 1:
            raise ValueError(
                f"a filter condition on {self.field!r} names exactly one of is, equals or in, "
                f"not {', '.join(given) or 'none'}"
            )
        return self


class FilterStep(_Step):
    """Keep the rows for which every condition holds; the others are counted, not lost."""

    kind: Literal["filter"]
    input: TableName
    keep: list[FilterCondition] = Field(min_length=1)


class DeriveStep(_Step):
    """A new column from a catalogued operation over named columns (brief §6). `settings` are the
    operation's declared settings (a separator, a part, a time zone…), data and never code; the
    operation refuses a wrong one in words, as its golden file shows."""

    kind: Literal["derive"]
    input: TableName
    column: ColumnName
    operation: DeriveOperation
    columns: list[ColumnName] = Field(min_length=1)
    settings: dict[str, Any] = Field(default_factory=dict)


class UnionStep(_Step):
    """Stack tables with the same columns; each row keeps its own refs."""

    kind: Literal["union"]
    inputs: list[TableName] = Field(min_length=2)


class DedupeStep(_Step):
    """Drop repeats on declared columns (today's deduplication key, as a step). The first row in
    the input's order stands for its repeats and carries all their refs, so the element it becomes
    names every source row it stands for; the repeats are counted."""

    kind: Literal["dedupe"]
    input: TableName
    on: list[ColumnName] = Field(min_length=1)


StagingStep = Annotated[
    LookupStep | JoinStep | FilterStep | DeriveStep | UnionStep | DedupeStep,
    Field(discriminator="kind"),
]


def step_inputs(step: StagingStep) -> list[str]:
    """The tables a step reads, in order."""
    if isinstance(step, JoinStep):
        return [step.left, step.right]
    if isinstance(step, UnionStep):
        return list(step.inputs)
    return [step.input]


ALL_MODELS: tuple[type[BaseModel], ...] = (
    AddedColumn,
    LookupStep,
    JoinStep,
    FilterCondition,
    FilterStep,
    DeriveStep,
    UnionStep,
    DedupeStep,
)
