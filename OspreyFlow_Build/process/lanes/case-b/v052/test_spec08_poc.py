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
    assert len(cases) >= 29, cases  # a floor, so the reading cannot find nothing and agree
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


def test_the_counts_reported_are_the_tables() -> None:
    """The figures the README, the friction row and the orchestrator were given."""
    runs = [c for c, r in s8.DISPOSITIONS.items() if r is None]
    seeded = [c for c, r in s8.DISPOSITIONS.items() if r == s8.NO_SEED]
    assert (len(runs), len(seeded)) == (14, 15)
    assert len(runs) + len(seeded) == len(s8.DISPOSITIONS) == 29
    assert "test_b14_an_alert_opens_at_its_address_in_its_own_case_with_its_entities" in runs
    assert "test_b7_a_shared_messaging_handle_is_common_to_the_second_cohort" in seeded


class Item:
    def __init__(self, name: str, module: Any, path: Path = s8.MODULE) -> None:
        self.name, self.originalname, self.module, self.path = name, name, module, path
        self.markers: list[Any] = []

    def add_marker(self, marker: Any) -> None:
        self.markers.append(marker)


#: The seed-free halves split from seeded cases (the orchestrator's review of step 6's sheet), each with its seeded half.
SPLIT = {
    "test_the_stream_opens_through_the_proxy_with_a_ticket": "test_the_delta_stream_is_reachable_through_the_proxy",
    "test_a7_an_unknown_field_name_is_refused_rather_than_ignored": "test_a7_the_events_table_survives_a_refused_field_name",
}
#: What a case does that rests on a seed: it finds a seeded identifier, or reads a count the seed put there.
SEEDED = ("_find(", "_in_case(", '["total"] > 0', "PRINCIPAL_SUBJECT")


def _case_source(name: str) -> str:
    import ast

    source = s8.MODULE.read_text(encoding="utf-8")
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == name)
    return ast.get_source_segment(source, node) or ""


@pytest.mark.parametrize("ours, seeded", list(SPLIT.items()))
def test_a_seed_free_half_runs_on_poc_and_reaches_no_seed(ours: str, seeded: str) -> None:
    """Each split case's seed-free half runs on poc, and its body does nothing that rests on a seed (red if a seeded
    step is moved back into it); its seeded half still waits on the seed and holds what the half left out."""
    assert s8.DISPOSITIONS[ours] is None and s8.DISPOSITIONS[seeded] == s8.NO_SEED
    body = _case_source(ours)
    assert not [w for w in SEEDED if w in body], [w for w in SEEDED if w in body]
    assert [w for w in SEEDED if w in _case_source(seeded)], seeded


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


def test_a_narrowed_selection_runs_without_stopping() -> None:
    """`run -k b1` collects one case: the module's other cases are not "gone" (item 13)."""
    module = SimpleNamespace(_sign_in_as_the_demo_analyst=lambda: "x")
    items = [Item("test_b1_every_rendering_of_one_number_resolves_to_a_single_endpoint", module)]
    s8.mark(items, mint=lambda: "t")
    assert items[0].markers == []


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
