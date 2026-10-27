"""ADR-130 Amendment 2, "a read that is written back": `sources_in_full()` is the scope a writer
reads an element in, so what it writes back is the stored record and not a withheld list. It is a
context variable, so it holds for one task and no other."""

from __future__ import annotations

import asyncio

import pytest

from ontology.handling import sources_in_full, withhold_sources
from tests.ontology.test_withhold_sources import _node, _principal

TWO = ["Z1001ZZ", "Z1002ZZ"]


def _withheld() -> bool:
    return withhold_sources(_node(TWO), _principal(["Z1001ZZ"])).provenance.sources_withheld


def test_inside_the_scope_the_sources_are_kept() -> None:
    node = _node(TWO)
    with sources_in_full():
        assert withhold_sources(node, _principal(["Z1001ZZ"])) is node


def test_outside_the_scope_they_are_withheld() -> None:
    assert _withheld() is True
    with sources_in_full():
        pass
    assert _withheld() is True


async def test_the_scope_does_not_leak_across_concurrent_tasks() -> None:
    inside_entered = asyncio.Event()
    outside_done = asyncio.Event()

    async def inside() -> bool:
        with sources_in_full():
            inside_entered.set()
            await outside_done.wait()
            return _withheld()

    async def outside() -> bool:
        await inside_entered.wait()
        result = _withheld()
        outside_done.set()
        return result

    kept_inside, withheld_outside = await asyncio.gather(inside(), outside())
    assert kept_inside is False
    assert withheld_outside is True


def test_the_scope_is_reset_after_an_exception() -> None:
    with pytest.raises(RuntimeError):
        with sources_in_full():
            raise RuntimeError("a write failed")
    assert _withheld() is True


def test_scopes_nest_and_the_outer_one_survives_the_inner() -> None:
    with sources_in_full():
        with sources_in_full():
            pass
        assert _withheld() is False
    assert _withheld() is True
