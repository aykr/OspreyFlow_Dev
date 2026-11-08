"""A dataset's domain model's store (`services/api/target_models.py`; ADR-140 decisions 4 and 5,
R12; `01_DOMAIN_MODEL.md` §2.2b), in memory. The same rules on Postgres, enforced by its indexes
too, are `test_target_models_store.py`.

What a mistake here would do, and the case that catches it:

- two drafts at once, so two people's edits race and one is lost:
  `test_a_second_draft_is_refused_in_words`;
- two live versions, so what runs is ambiguous:
  `test_making_a_draft_live_makes_the_old_live_previous`;
- a revert rewriting the version it reverts to: `test_a_revert_is_a_new_draft_never_a_rewrite`;
- an extension deleted rather than retired, so a loaded node's type disappears:
  `test_an_extension_is_retired_never_deleted`;
- a POLE core type redefined as an extension: `test_a_core_type_cannot_be_an_extension`;
- making live a draft other than the one shown (changed since it was opened):
  `test_making_live_names_the_draft_it_saw`.

Each is red with its rule removed (`test_each_rule_fails_with_it_alone_removed`).
"""

from __future__ import annotations

from typing import Any

import pytest
from services.api import target_models
from services.api.target_models import (
    CORE_TYPES_FOR_TESTS,
    InMemoryTargetModelStore,
    TargetModelRefused,
)

from schemas.dataset_model import ModelExtension, TargetModelDraftInput
from schemas.domain import Principal

ENGINEER = Principal(id="d.engineer", clearance="OFFICIAL", org_unit="unit-1")
DATASET = "dataset-1"


def _store() -> InMemoryTargetModelStore:
    return InMemoryTargetModelStore(core_types=CORE_TYPES_FOR_TESTS)


def _vessel(added_in: int, retired_in: int | None = None) -> ModelExtension:
    return ModelExtension(
        name="Vessel", kind="entity_type", added_in=added_in, retired_in=retired_in
    )


async def _live_with_a_vessel(store: InMemoryTargetModelStore) -> None:
    """Version 1 live, with FIBO and the `Vessel` extension."""
    await store.open_draft(DATASET, ENGINEER)
    await store.save_draft(
        DATASET, TargetModelDraftInput(packs={"fibo": 3}, extensions=[_vessel(1)]), ENGINEER
    )
    await store.make_live(DATASET, 1, ENGINEER)


async def test_a_dataset_with_no_model_opens_version_one_as_bare_pole() -> None:
    store = _store()
    assert await store.live(DATASET) is None
    draft = await store.open_draft(DATASET, ENGINEER)
    assert (draft.version, draft.state, draft.packs, draft.extensions) == (1, "draft", {}, [])


async def test_a_second_draft_is_refused_in_words() -> None:
    store = _store()
    await store.open_draft(DATASET, ENGINEER)
    with pytest.raises(TargetModelRefused, match="already has a draft"):
        await store.open_draft(DATASET, ENGINEER)


async def test_making_a_draft_live_makes_the_old_live_previous() -> None:
    store = _store()
    await _live_with_a_vessel(store)
    await store.open_draft(DATASET, ENGINEER)
    live, before = await store.make_live(DATASET, 2, ENGINEER)
    assert (live.version, live.state, live.made_live_by) == (2, "live", ENGINEER.id)
    assert before is not None and (before.version, before.state) == (1, "previous")
    states = [(m.version, m.state) for m in await store.versions(DATASET)]
    assert states == [(1, "previous"), (2, "live")]
    assert await store.draft(DATASET) is None


async def test_a_draft_opens_as_a_copy_of_live_and_editing_it_changes_nothing_live() -> None:
    store = _store()
    await _live_with_a_vessel(store)
    draft = await store.open_draft(DATASET, ENGINEER)
    assert (draft.version, draft.packs, draft.extensions) == (2, {"fibo": 3}, [_vessel(1)])
    await store.save_draft(
        DATASET, TargetModelDraftInput(packs={"fibo": 3, "stix": 1}, extensions=[_vessel(1)]),
        ENGINEER,
    )  # fmt: skip
    live = await store.live(DATASET)
    assert live is not None and live.packs == {"fibo": 3}


async def test_a_revert_is_a_new_draft_never_a_rewrite() -> None:
    store = _store()
    await _live_with_a_vessel(store)
    await store.open_draft(DATASET, ENGINEER)
    await store.save_draft(
        DATASET, TargetModelDraftInput(packs={"fibo": 3, "stix": 1}, extensions=[_vessel(1)]),
        ENGINEER,
    )  # fmt: skip
    await store.make_live(DATASET, 2, ENGINEER)
    reverted = await store.revert(DATASET, 1, ENGINEER)
    assert (reverted.version, reverted.state, reverted.reverted_from) == (3, "draft", 1)
    assert reverted.packs == {"fibo": 3}
    (one,) = [m for m in await store.versions(DATASET) if m.version == 1]
    assert (one.state, one.packs) == ("previous", {"fibo": 3})  # version 1 as it was


async def test_a_revert_is_refused_while_a_draft_is_open() -> None:
    store = _store()
    await _live_with_a_vessel(store)
    await store.open_draft(DATASET, ENGINEER)
    with pytest.raises(TargetModelRefused, match="already has a draft"):
        await store.revert(DATASET, 1, ENGINEER)


async def test_an_extension_is_retired_never_deleted() -> None:
    store = _store()
    await _live_with_a_vessel(store)
    await store.open_draft(DATASET, ENGINEER)
    with pytest.raises(TargetModelRefused, match="retired, never deleted.*Vessel"):
        await store.save_draft(DATASET, TargetModelDraftInput(packs={"fibo": 3}), ENGINEER)
    retired = await store.save_draft(
        DATASET, TargetModelDraftInput(packs={"fibo": 3}, extensions=[_vessel(1, retired_in=2)]),
        ENGINEER,
    )  # fmt: skip
    assert retired.extensions == [_vessel(1, retired_in=2)]


async def test_a_revert_keeps_a_later_extension_as_retired() -> None:
    """Reverting to a version before an extension was added does not delete it: it is retired in
    the new draft, so a node already loaded with that type keeps a type that exists."""
    store = _store()
    await store.open_draft(DATASET, ENGINEER)
    await store.make_live(DATASET, 1, ENGINEER)
    await store.open_draft(DATASET, ENGINEER)
    await store.save_draft(DATASET, TargetModelDraftInput(extensions=[_vessel(2)]), ENGINEER)
    await store.make_live(DATASET, 2, ENGINEER)
    reverted = await store.revert(DATASET, 1, ENGINEER)
    assert reverted.extensions == [_vessel(2, retired_in=3)]


async def test_a_new_extension_is_added_in_the_draft_and_an_old_one_is_unchanged() -> None:
    store = _store()
    await _live_with_a_vessel(store)
    await store.open_draft(DATASET, ENGINEER)
    with pytest.raises(TargetModelRefused, match="added in this draft, version 2"):
        await store.save_draft(
            DATASET,
            TargetModelDraftInput(extensions=[_vessel(1), ModelExtension(
                name="Port", kind="entity_type", added_in=1)]),
            ENGINEER,
        )  # fmt: skip
    with pytest.raises(TargetModelRefused, match="Vessel.*cannot be changed"):
        await store.save_draft(
            DATASET,
            TargetModelDraftInput(extensions=[ModelExtension(
                name="Vessel", kind="link_type", added_in=1)]),
            ENGINEER,
        )  # fmt: skip


async def test_a_core_type_cannot_be_an_extension() -> None:
    store = _store()
    await store.open_draft(DATASET, ENGINEER)
    with pytest.raises(TargetModelRefused, match="Person is a POLE core type"):
        await store.save_draft(
            DATASET,
            TargetModelDraftInput(extensions=[ModelExtension(
                name="Person", kind="entity_type", added_in=1)]),
            ENGINEER,
        )  # fmt: skip


async def test_making_live_names_the_draft_it_saw() -> None:
    store = _store()
    await _live_with_a_vessel(store)
    with pytest.raises(TargetModelRefused, match="no draft"):
        await store.make_live(DATASET, 2, ENGINEER)
    await store.open_draft(DATASET, ENGINEER)
    with pytest.raises(TargetModelRefused, match="the draft is version 2, not 3"):
        await store.make_live(DATASET, 3, ENGINEER)


async def test_a_discarded_draft_leaves_live_as_it_was() -> None:
    store = _store()
    await _live_with_a_vessel(store)
    await store.open_draft(DATASET, ENGINEER)
    await store.discard_draft(DATASET)
    assert await store.draft(DATASET) is None
    assert [m.version for m in await store.versions(DATASET)] == [1]
    with pytest.raises(TargetModelRefused, match="no draft"):
        await store.discard_draft(DATASET)


# --- each rule red with it alone removed --------------------------------------------------------


def _without(monkeypatch: pytest.MonkeyPatch, rule: str) -> None:
    def allowed(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(target_models, rule, allowed)


@pytest.mark.parametrize(
    "rule",
    ["_refuse_a_second_draft", "_refuse_a_deleted_extension", "_refuse_a_core_type"],
)
async def test_each_rule_fails_with_it_alone_removed(
    rule: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 15, red: each refusal above, removed alone, lets its write through."""
    _without(monkeypatch, rule)
    store = _store()
    if rule == "_refuse_a_second_draft":
        await store.open_draft(DATASET, ENGINEER)
        await store.open_draft(DATASET, ENGINEER)  # a second draft, not refused
        assert len([m for m in await store.versions(DATASET) if m.state == "draft"]) == 2
    elif rule == "_refuse_a_deleted_extension":
        await _live_with_a_vessel(store)
        await store.open_draft(DATASET, ENGINEER)
        saved = await store.save_draft(DATASET, TargetModelDraftInput(packs={"fibo": 3}), ENGINEER)
        assert saved.extensions == []  # the Vessel deleted
    else:
        await store.open_draft(DATASET, ENGINEER)
        core = ModelExtension(name="Person", kind="entity_type", added_in=1)
        saved = await store.save_draft(DATASET, TargetModelDraftInput(extensions=[core]), ENGINEER)
        assert saved.extensions == [core]


async def test_a_revert_brings_back_an_extension_its_version_had_and_it_saves() -> None:
    """Retiring is not forever: a revert to a version that had the extension has it in force
    again, and the draft saves as it stands."""
    store = _store()
    await _live_with_a_vessel(store)
    await store.open_draft(DATASET, ENGINEER)
    await store.save_draft(
        DATASET, TargetModelDraftInput(packs={"fibo": 3}, extensions=[_vessel(1, retired_in=2)]),
        ENGINEER,
    )  # fmt: skip
    await store.make_live(DATASET, 2, ENGINEER)
    reverted = await store.revert(DATASET, 1, ENGINEER)
    assert reverted.extensions == [_vessel(1)]
    again = await store.save_draft(
        DATASET, TargetModelDraftInput(packs={"fibo": 3}, extensions=[_vessel(1)]), ENGINEER
    )
    assert again.extensions == [_vessel(1)]
