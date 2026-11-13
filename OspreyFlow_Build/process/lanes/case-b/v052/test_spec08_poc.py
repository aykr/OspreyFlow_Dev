"""Spec 08's runner on poc (spec08_poc.py), offline: every case of the over-the-wire module has a
disposition (runs, or not on poc with its reason), both ways; the plugin skips exactly the ones that
cannot run, and swaps the module's Keycloak sign-in for the Entra stand-in's token."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import spec08_poc as s8


def test_every_case_of_the_module_has_a_disposition_and_no_other() -> None:
    cases = s8.cases_in(s8.MODULE.read_text(encoding="utf-8"))
    assert len(cases) >= 27, cases  # a floor, so the reading cannot find nothing and agree
    s8.check_cases(cases)


def test_a_new_case_in_the_module_stops_the_run() -> None:
    cases = [*s8.DISPOSITIONS, "test_b22_a_row_nobody_placed"]
    with pytest.raises(s8.Undisposed, match="test_b22_a_row_nobody_placed"):
        s8.check_cases(cases)


def test_a_disposition_for_a_case_that_is_gone_stops_the_run() -> None:
    cases = [c for c in s8.DISPOSITIONS if c != "test_b1_every_rendering_of_one_number_resolves_to_a_single_endpoint"]
    with pytest.raises(s8.Undisposed, match="test_b1_every"):
        s8.check_cases(cases)


def test_every_reason_says_why() -> None:
    for case, reason in s8.DISPOSITIONS.items():
        assert reason is None or len(reason) > 20, case


def test_the_seed_count_is_what_the_table_says() -> None:
    seeded = [c for c, r in s8.DISPOSITIONS.items() if r == s8.NO_SEED]
    runs = [c for c, r in s8.DISPOSITIONS.items() if r is None]
    assert len(seeded) + len(runs) == len(s8.DISPOSITIONS)
    assert "test_the_analysts_own_door_opens" in runs
    assert "test_b7_a_shared_messaging_handle_is_common_to_the_second_cohort" in seeded


class Item:
    def __init__(self, name: str, module: Any, path: Path = s8.MODULE) -> None:
        self.name, self.originalname, self.module, self.path = name, name, module, path
        self.markers: list[Any] = []

    def add_marker(self, marker: Any) -> None:
        self.markers.append(marker)


def test_the_plugin_skips_exactly_the_cases_that_cannot_run_and_swaps_the_sign_in() -> None:
    module = SimpleNamespace(_sign_in_as_the_demo_analyst=lambda: "a Keycloak token")
    items = [Item(c, module) for c in s8.DISPOSITIONS]
    other = Item("test_elsewhere", SimpleNamespace(), Path("tests/test_other.py"))
    s8.mark([*items, other], mint=lambda: "a stand-in token")
    for item in items:
        skipped = [m for m in item.markers if m.name == "skip"]
        if s8.DISPOSITIONS[item.name] is None:
            assert not skipped, item.name
        else:
            assert len(skipped) == 1 and s8.DISPOSITIONS[item.name] in skipped[0].kwargs["reason"], item.name
    assert other.markers == []
    assert module._sign_in_as_the_demo_analyst() == "a stand-in token"


def test_the_plugin_refuses_a_module_that_gained_a_case() -> None:
    module = SimpleNamespace(_sign_in_as_the_demo_analyst=lambda: "x")
    items = [Item(c, module) for c in [*s8.DISPOSITIONS, "test_b22_new"]]
    with pytest.raises(s8.Undisposed):
        s8.mark(items, mint=lambda: "t")


def test_the_glass_sign_in_code_is_read_from_the_standins_redirect() -> None:
    location = "https://ospreyflow.r1.test/?code=abc123&state=s1&session_state=x"
    assert s8.code_from_redirect(location, "s1") == "abc123"
    with pytest.raises(ValueError, match="state"):
        s8.code_from_redirect(location, "another")
    with pytest.raises(ValueError, match="no code"):
        s8.code_from_redirect("https://ospreyflow.r1.test/?error=access_denied&state=s1", "s1")
