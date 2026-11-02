"""ADR-139's arithmetic and resolution order (`packages/ontology/influencers.py`), without a store.

What the graph adapter decides (which records the viewer may see) is the conformance suite's
(`tests/conformance/graph_port/test_suite.py`, the `connection_strengths` cases); here, given what
it found, the strength and the influencers in force.
"""

from __future__ import annotations

import itertools
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from adapters.graph_arcadedb.weight import compute_weight
from ontology.errors import OntologyError
from ontology.influencers import (
    applies_to,
    calibrated_boost,
    connection_strength,
    legend_of,
    load_strength_defaults,
    pre_logistic,
    resolve_influencers,
)
from ontology.weights import load_weight_rules
from schemas.domain import WeightComponents
from schemas.strength import (
    ActiveInfluencer,
    CaseInfluencersInput,
    InfluencerTrigger,
    StrengthInfluencer,
)

RULES = load_weight_rules()
NOW = datetime(2026, 11, 2, tzinfo=UTC)

ASSAULT = InfluencerTrigger(entity_type="Incident", property="category", values=["assault"])


def _inf(key: str, change: str, size: float, *, trigger: InfluencerTrigger | None = None,
         types: tuple[str, ...] = ("IN_CONFLICT_WITH",), enabled: bool = True) -> StrengthInfluencer:
    return StrengthInfluencer(id=key, label=key, trigger=trigger, link_types=list(types),
                              change=change, size=size, enabled=enabled)  # type: ignore[arg-type]


def _active(*influencers: StrengthInfluencer) -> list[ActiveInfluencer]:
    return [ActiveInfluencer(influencer=i, layer="file") for i in influencers]


GRID_TYPES = ("IN_CONFLICT_WITH", "ROLE_IN", "VISITED")
KINDS = {
    "add": _inf("add", "add", 0.1348, types=GRID_TYPES),
    "multiply": _inf("multiply", "multiply", 1.6, types=GRID_TYPES),
    "weaken": _inf("weaken", "multiply", 0.5, types=GRID_TYPES),
    "floor": _inf("floor", "floor", 0.6, types=GRID_TYPES),
    "exclude": _inf("exclude", "exclude", 0, types=GRID_TYPES),
    "triggered-add": _inf("triggered-add", "add", 0.3, trigger=ASSAULT),
}


def _weight(occurrences: int, edge_type: str = "IN_CONFLICT_WITH") -> float:
    return compute_weight(
        WeightComponents(occurrences=occurrences, corpus_pair_count=occurrences,
                         corpus_source_degree=occurrences, corpus_target_degree=occurrences,
                         corpus_total_occurrences=occurrences, computed_at=NOW),
        edge_type=edge_type, valid_to=NOW - timedelta(days=30), now=NOW, rules=RULES,
        self_loop=False,
    )  # fmt: skip


# --- monotonicity --------------------------------------------------------------------------------


def _decreases(
    active: list[ActiveInfluencer], evidence: dict[str, str], strength_of=connection_strength
) -> list[str]:
    found = []
    for edge_type in ("IN_CONFLICT_WITH", "ROLE_IN", "VISITED"):
        strengths = [
            strength_of(_weight(n, edge_type), edge_type, active, evidence, RULES)[0]
            for n in range(0, 80)
        ]
        for n, (before, after) in enumerate(itertools.pairwise(strengths)):
            if after < before - 1e-12:
                found.append(f"{edge_type}: {n} -> {n + 1}, {before} -> {after}")
    return found


def test_adding_occurrences_never_lowers_a_strength_over_every_combination_of_influencers() -> None:
    """ADR-139's monotonicity test: over a grid of occurrences, for each subset of the influencer
    kinds switched on (2^6 combinations), with and without the trigger's evidence."""
    names = sorted(KINDS)
    for size in range(len(names) + 1):
        for chosen in itertools.combinations(names, size):
            active = _active(*(KINDS[n] for n in chosen))
            for evidence in ({}, {"triggered-add": "Incident"}):
                assert _decreases(active, evidence) == [], (chosen, evidence)


def test_the_grid_would_catch_a_boost_given_only_to_weak_links() -> None:
    """Rule 15: the grid reports the slip of boosting only a link still below the midpoint ("help
    the weak links"), in `connection_strength`'s own shape: the boost vanishes as the link crosses
    the midpoint, so its strength falls as its occurrences rise."""
    from ontology.influencers import applies_to, logistic, pre_logistic

    def slipped(weight, edge_type, active, evidence, rules):  # type: ignore[no-untyped-def]
        applied = [a for a in active if applies_to(a.influencer, edge_type, evidence)]
        raw = pre_logistic(weight, rules)
        if raw < rules.midpoint:
            raw += sum(a.influencer.size for a in applied if a.influencer.change == "add")
        return logistic(raw, rules), []

    assert _decreases(_active(KINDS["add"]), {}, slipped) != []


def test_with_nothing_applying_the_strength_is_the_stored_weight_exactly() -> None:
    for n in (0, 1, 5, 40):
        weight = _weight(n)
        assert connection_strength(weight, "IN_CONFLICT_WITH", [], {}, RULES) == (weight, [])
        unrelated = _active(_inf("calls", "add", 0.2, types=("COMMUNICATED_WITH",)))
        assert connection_strength(weight, "IN_CONFLICT_WITH", unrelated, {}, RULES)[0] == weight


def test_the_pre_logistic_score_is_recovered_exactly_from_a_stored_weight() -> None:
    for n in (0, 1, 2, 10, 39):
        weight = _weight(n)
        rule = RULES.rule_for("IN_CONFLICT_WITH")[1]
        expected = (RULES.alpha * math.log1p(n) / math.log1p(rule.heavy or 1)
                    + RULES.beta * 0.5 ** (30 / RULES.half_life_days))  # fmt: skip
        assert pre_logistic(weight, RULES) == pytest.approx(expected, abs=1e-9)


def test_each_kind_of_change_does_what_its_name_says() -> None:
    weight = _weight(1)
    add, _ = connection_strength(weight, "IN_CONFLICT_WITH", _active(KINDS["add"]), {}, RULES)
    assert add > weight
    up, _ = connection_strength(weight, "IN_CONFLICT_WITH", _active(KINDS["multiply"]), {}, RULES)
    assert up > weight
    down, _ = connection_strength(weight, "IN_CONFLICT_WITH", _active(KINDS["weaken"]), {}, RULES)
    assert down < weight
    floor, _ = connection_strength(weight, "IN_CONFLICT_WITH", _active(KINDS["floor"]), {}, RULES)
    assert floor == max(weight, 0.6)
    capped, applied = connection_strength(
        weight, "IN_CONFLICT_WITH", _active(KINDS["add"], KINDS["floor"], KINDS["exclude"]), {},
        RULES,
    )  # fmt: skip
    assert capped == weight  # an exclusion caps what the boost and the floor raised
    assert [a.id for a in applied] == ["add", "floor", "exclude"]


def test_boosts_add_and_stack() -> None:
    """The client's boosts "are added and stack": two adds move the score by their sum."""
    weight = _weight(3)
    two = _active(_inf("a", "add", 0.1), _inf("b", "add", 0.2))
    one = _active(_inf("c", "add", 0.3))
    assert connection_strength(weight, "IN_CONFLICT_WITH", two, {}, RULES)[0] == pytest.approx(
        connection_strength(weight, "IN_CONFLICT_WITH", one, {}, RULES)[0]
    )


# --- triggers ------------------------------------------------------------------------------------


def test_a_triggered_influencer_applies_only_with_its_evidence_and_only_to_its_link_types() -> None:
    triggered = KINDS["triggered-add"]
    weight = _weight(2)
    active = _active(triggered)
    assert connection_strength(weight, "IN_CONFLICT_WITH", active, {}, RULES)[0] == weight
    boosted, applied = connection_strength(
        weight, "IN_CONFLICT_WITH", active, {"triggered-add": "Incident"}, RULES
    )
    assert boosted > weight
    assert applied[0].record_kind == "Incident"
    # Evidence for another influencer is not this one's.
    assert connection_strength(weight, "IN_CONFLICT_WITH", active, {"other": "Incident"},
                               RULES)[0] == weight  # fmt: skip
    # Not one of its link types: evidence or none, nothing changes.
    assert connection_strength(_weight(2, "VISITED"), "VISITED", active,
                               {"triggered-add": "Incident"}, RULES)[0] == _weight(2, "VISITED")  # fmt: skip


def test_a_direct_influencer_applies_to_its_named_link_types_alone() -> None:
    direct = _inf("direct", "add", 0.1348, types=("COMMUNICATED_WITH", "VISITED"))
    assert applies_to(direct, "VISITED", {})
    assert applies_to(direct, "COMMUNICATED_WITH", {})
    assert not applies_to(direct, "PRESENT_AT", {})
    assert not applies_to(direct, "IN_CONFLICT_WITH", {"direct": "Incident"})


# --- the shipped defaults ------------------------------------------------------------------------


def test_the_weights_file_ships_direct_links_and_the_incident_source_influencer() -> None:
    defaults = load_strength_defaults()
    by_id = {i.id: i for i in defaults.influencers}
    direct = by_id["direct"]
    assert direct.trigger is None
    assert direct.link_types == ["COMMUNICATED_WITH", "TRANSACTED", "VISITED", "SHARED_CELL_WITH"]
    source = by_id["incident-source"]
    assert source.trigger == InfluencerTrigger(
        entity_type="Incident", property="category", values=["assault", "disorder", "find"]
    )
    assert source.link_types == ["ROLE_IN", "IN_CONFLICT_WITH", "ASSOCIATE_OF", "SHARED_CELL_WITH"]
    assert defaults.rarity_exclude_types == ("Alert",)
    for influencer in defaults.influencers:
        assert influencer.change == "add"
        assert influencer.note == "to be confirmed with the client"


def test_the_shipped_sizes_are_the_calibration_not_a_hand_tuned_number() -> None:
    """Decision 1: a boost moves an ordinary link about as far as doubling its count would."""
    boost = calibrated_boost(RULES)
    assert boost == pytest.approx(0.1348, abs=1e-4)
    for influencer in load_strength_defaults().influencers:
        assert influencer.size == pytest.approx(boost, abs=5e-5), influencer.id


def test_the_shipped_influencers_name_types_the_shipped_ontology_declares() -> None:
    from ontology.loader import load_default_ontology
    from ontology.packs import compose_with_packs

    ontology = compose_with_packs(load_default_ontology(), ["niem"])
    for influencer in load_strength_defaults().influencers:
        for link_type in influencer.link_types:
            assert ontology.edge_type(link_type) is not None, link_type
        if influencer.trigger is not None:
            declared = ontology.entity_type(influencer.trigger.entity_type)
            assert declared is not None
            prop = next(p for p in declared.properties if p.name == influencer.trigger.property)
            assert set(influencer.trigger.values) <= set(prop.values or [])


def test_a_malformed_shipped_influencer_is_refused_naming_it(tmp_path: Path) -> None:
    source = Path(load_weight_rules.__code__.co_filename).parent / "weights" / "default.yaml"
    text = source.read_text(encoding="utf-8")
    broken = tmp_path / "weights.yaml"
    broken.write_text(text.replace("    size: 0.1348\n", "    size: -1\n", 1), encoding="utf-8")
    with pytest.raises(OntologyError, match="'direct'"):
        load_strength_defaults(broken)


# --- the resolution order ------------------------------------------------------------------------


SHIPPED = [_inf("direct", "add", 0.1348, types=("VISITED",)), _inf("src", "add", 0.1, trigger=ASSAULT)]


def test_the_installation_set_replaces_a_shipped_influencer_of_the_same_id_and_adds_its_own() -> None:
    installation = [_inf("src", "add", 0.4, trigger=ASSAULT), _inf("money", "floor", 0.5)]
    active, off = resolve_influencers(SHIPPED, installation, installation_version=3)
    assert [(a.influencer.id, a.layer, a.influencer.size) for a in active] == [
        ("direct", "file", 0.1348), ("src", "installation", 0.4), ("money", "installation", 0.5)
    ]
    assert active[1].version == 3
    assert off == []


def test_a_case_override_comes_first_then_the_installation_then_the_file() -> None:
    installation = [_inf("src", "add", 0.4, trigger=ASSAULT)]
    case = CaseInfluencersInput(added=[_inf("src", "add", 0.9, trigger=ASSAULT)])
    active, _ = resolve_influencers(SHIPPED, installation, case, case_version=2)
    src = next(a for a in active if a.influencer.id == "src")
    assert (src.layer, src.influencer.size, src.version) == ("case", 0.9, 2)


def test_a_case_switches_off_an_installation_or_shipped_influencer_and_says_so() -> None:
    installation = [_inf("money", "floor", 0.5)]
    case = CaseInfluencersInput(switched_off=["direct", "money", "not-there"])
    active, off = resolve_influencers(SHIPPED, installation, case)
    assert [a.influencer.id for a in active] == ["src"]
    assert off == ["direct", "money"]


def test_an_installation_entry_switched_off_removes_the_shipped_one() -> None:
    active, _ = resolve_influencers(SHIPPED, [_inf("direct", "add", 0.1, types=("VISITED",),
                                                   enabled=False)])  # fmt: skip
    assert [a.influencer.id for a in active] == ["src"]


def test_the_legend_lists_exactly_the_influencers_in_force_and_the_direct_link_types() -> None:
    installation = [_inf("money", "add", 0.2, types=("TRANSACTED",))]
    case = CaseInfluencersInput(added=[_inf("case-only", "floor", 0.7, trigger=ASSAULT)],
                                switched_off=["src"])
    active, off = resolve_influencers(SHIPPED, installation, case, case_version=1)
    legend = legend_of(active, off, case_version=1)
    assert [(a.influencer.id, a.layer) for a in legend.influencers] == [
        ("direct", "file"), ("money", "installation"), ("case-only", "case")
    ]
    assert legend.direct_link_types == ["TRANSACTED", "VISITED"]
    assert legend.switched_off == ["src"]
    assert "what you may see" in legend.rarity_note
