"""ADR-110 Amendment 16 through the Conduit's stamping graph (ADR-099 Amendment 15): a returning
row's load's revert has `restore_link_state` as its only graph write, so the wrapper guards it as it
guards the revert's other writes. In a case reading a composite it is refused before the adapter is
asked. Outside one it goes through and the kept figures are cleared after it. And it is declared on
the wrapper, never passed on by `__getattr__`, so a wrapper without it cannot restore through the
adapter unguarded. Red with the guard removed, and with the declared method removed
(`process/lanes/studio/L1.2a_RED_RECORD.md`)."""

from __future__ import annotations

from typing import Any

import pytest
from schemas.domain import Handling
from schemas.ingest import LinkPriorState
from services.api.dataset_scope import (
    CompositeReadOnlyError,
    DatasetStampingGraph,
    set_case_datasets,
    stamping,
)

from tests.services.api.test_composite_read_only import (
    _composite_store,
    _in_the_composite_case,
)


class Restoring:
    """An adapter's restore, recorded."""

    def __init__(self) -> None:
        self.restored: list[str] = []

    async def begin_transaction(self) -> str:
        return "tx"

    async def restore_link_state(self, state: LinkPriorState, tx: Any) -> bool:
        self.restored.append(state.edge_id)
        return True


def _state() -> LinkPriorState:
    return LinkPriorState(
        edge_id="link-1", edge_type="TRANSACTED", revision=1, load_id="load-1",
        handling=Handling(classification="OFFICIAL", handling_code="P", originator="unit-1",
                          owning_unit="unit-1"),
        stored={}, left_digest="digest",
    )  # fmt: skip


async def test_a_restore_in_a_composite_case_is_refused_before_the_adapter_is_asked() -> None:
    store, _ = await _in_the_composite_case()
    inner = Restoring()
    stamped = stamping(inner, registry=store)  # type: ignore[arg-type]

    with pytest.raises(CompositeReadOnlyError):
        await stamped.restore_link_state(_state(), "tx")

    assert inner.restored == []


async def test_a_restore_outside_a_composite_goes_through_and_clears_the_kept_figures() -> None:
    store = await _composite_store()
    set_case_datasets(None)
    inner = Restoring()
    stamped = stamping(inner, registry=store)  # type: ignore[arg-type]
    cleared: list[bool] = []

    async def clear() -> None:
        cleared.append(True)

    stamped.after_write(clear)
    assert await stamped.restore_link_state(_state(), "tx") is True
    assert inner.restored == ["link-1"] and cleared == [True]


def test_the_restore_is_declared_on_the_wrapper_and_never_passed_on() -> None:
    assert "restore_link_state" in DatasetStampingGraph.__dict__
    stamped = DatasetStampingGraph(Restoring())  # type: ignore[arg-type]
    with pytest.raises(AttributeError):
        DatasetStampingGraph.__getattr__(stamped, "restore_link_state")
