"""The rule editor's reads and requests (`06_DECISIONS.md` ADR-146 decision 3 and Amendment 6,
L2.11): the datasets a rule may be declared on, each with its live domain model's types and links
and the screening lists it may read; and *Test*'s result.

TypeScript is generated from these models (`generate_ts.py`); drift fails the build.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from schemas.domain import OntologySchema
from schemas.list_connector import OfferedList


class RuleDatasetOffer(BaseModel):
    """A dataset a rule may be declared on: the case's chosen source or composite, never a layer or
    a drawn dataset (ADR-146 decision 3). `ontology` is the deployment's ontology narrowed to the
    dataset's live model (its whole ontology while it has no model yet, as boards read it), so the
    conditions offer no type outside it; `lists` are the screening and reference lists it may read
    (its own and those it subscribes to); `second_person` says *Make live* waits for another
    person's approval (the dataset's policy, ADR-145 A3)."""

    id: str
    name: str
    kind: Literal["source", "composite"]
    second_person: bool
    ontology: OntologySchema
    lists: list[OfferedList] = Field(default_factory=list)


class RuleTestResult(BaseModel):
    """*Test* (ADR-146 decision 3): how many alerts the draft would have raised over the dataset's
    last `days` days, run as its author, and the version it ran on."""

    rule_id: str
    version: int = Field(ge=1)
    days: int = Field(ge=1)
    would_raise: int = Field(ge=0)
    words: str


ALL_MODELS = (RuleDatasetOffer, RuleTestResult)
