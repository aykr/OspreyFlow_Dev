"""ADR-127 Amendment 23: the seed gives a picture its subject's classification and handling code
and keeps no action or sanitisation code, so readers are unchanged only if no picture subject
carries one and every element of the plan is handled `P`. Over Brief 1's plan, no store."""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest
from demo_fixtures import pid_plan


@pytest.fixture(scope="module")
def demo() -> Any:
    return pid_plan.build_plan("demo")


def subjects_with_a_code_the_picture_would_lose(plan: Any) -> list[str]:
    """Each picture subject whose handling carries an action or a sanitisation code."""
    held = {e.key: e for e in plan.entities}
    return [
        key
        for key in plan.picture_subjects
        if held[key].handling.action_code or held[key].handling.sanitisation_code
    ]


def elements_not_handled_p(plan: Any) -> list[str]:
    """Each entity or link whose handling code is not `P`."""
    return [e.key for e in (*plan.entities, *plan.links) if e.handling.handling_code != "P"]


def test_no_picture_subject_carries_an_action_or_sanitisation_code(demo: Any) -> None:
    assert len(demo.picture_subjects) == 1_633
    assert subjects_with_a_code_the_picture_would_lose(demo) == []


def test_every_element_is_handled_p(demo: Any) -> None:
    assert demo.entities and demo.links
    assert elements_not_handled_p(demo) == []


def test_the_checks_fail_for_a_planted_subject_and_element(demo: Any) -> None:
    """Shown red (rule 15): a subject given an action code, a subject given a sanitisation code and
    an element handled `C` are each found."""
    first, second = demo.picture_subjects[:2]
    entities = tuple(
        dataclasses.replace(e, handling=dataclasses.replace(e.handling, action_code="A1"))
        if e.key == first
        else dataclasses.replace(
            e, handling=dataclasses.replace(e.handling, sanitisation_code="S2")
        )
        if e.key == second
        else e
        for e in demo.entities
    )
    planted = dataclasses.replace(demo, entities=entities)
    assert subjects_with_a_code_the_picture_would_lose(planted) == [first, second]
    link = dataclasses.replace(
        demo.links[0], handling=dataclasses.replace(demo.links[0].handling, handling_code="C")
    )
    assert elements_not_handled_p(dataclasses.replace(demo, links=(link, *demo.links[1:]))) == [
        link.key
    ]
