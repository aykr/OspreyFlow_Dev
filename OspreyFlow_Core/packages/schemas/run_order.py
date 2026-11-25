"""A dataset's run order on the wire (slice IS6a; ADR-140 Amendment 22 item 8; ADR-141
Amendment 2 point 6).

The order is **"runs after" links**: for each pipeline of the dataset, the pipelines it runs
after. A pipeline with no link runs after nothing. It is stored with the dataset, versioned (a
number per save, with who saved it and when), and a save names the number its person read.
Nothing here runs a pipeline.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

#: At most this many pipelines in an order, and this many links from one: a bound so that a body
#: cannot be unbounded.
MAX_ENTRIES = 500


class RunOrderEntry(BaseModel):
    """One pipeline and the pipelines it runs after."""

    model_config = ConfigDict(extra="forbid")

    pipeline_id: str = Field(min_length=1, max_length=200)
    runs_after: list[str] = Field(default_factory=list, max_length=MAX_ENTRIES)


class RunOrderSave(BaseModel):
    """A save: the links as the person now has them, and the number of the stored order they read
    (0 when none was stored). The number is required and is an integer, never a string or a flag:
    a client that sends none cannot skip the check."""

    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(strict=True, ge=0)
    entries: list[RunOrderEntry] = Field(max_length=MAX_ENTRIES)

    @model_validator(mode="after")
    def _one_entry_for_each_pipeline(self) -> RunOrderSave:
        seen = [e.pipeline_id for e in self.entries]
        if len(set(seen)) != len(seen):
            raise ValueError("entries: each pipeline is given once")
        return self


class RunOrderView(BaseModel):
    """The stored order as the reader may see it: only the links among the pipelines they may
    see, and no entry for a pipeline with none (so an entry never says that a pipeline runs
    after something it may not name). `version` is 0, with no `saved_by` and no `saved_at`, when
    no order has been saved."""

    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    version: int = Field(ge=0)
    saved_by: str | None = None
    saved_at: datetime | None = None
    entries: list[RunOrderEntry]


ALL_MODELS: tuple[type[BaseModel], ...] = (RunOrderEntry, RunOrderSave, RunOrderView)
