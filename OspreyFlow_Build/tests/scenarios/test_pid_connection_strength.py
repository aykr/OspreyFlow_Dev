"""The Prison Intelligence demo's connection-strength scene (ADR-139 decision 10; ADR-127 Amendment
42), proved on the plan without a store: every claim the scene makes rests on data the case already
holds, so no generator changed.

Worked out as the store works them out: the stored weight by `compute_weight` with the shipped
weights file (version 3), the influencers by `ontology/influencers.py` with the shipped defaults,
an influencer's evidence as the graph adapter finds it (a record at one end of the link, or linked to
both ends), and rarity as `ln(N / df)` over the case's persons (the PID is OFFICIAL throughout, so
every analyst sees all of it, as the client's analysts do). Each claim is checked at two load dates,
the plan's cut-off and six months after it, since a stored weight's recency is the load's.

The scene's claims, each a test:
- an assault-evidenced link drawn stronger (CAP-S2);
- a direct call against a shared address (CAP-S3): two men who held one cell at different times share
  it and nothing direct, where the principal's calls to the coordinator are a direct link;
- a rare shared contact ranking above a common one (CAP-S4);
- a strength rule (CAP-S6): with the case's own "Assault in this case" floor, a rule on conflicts
  reaching 0.95 raises exactly the principal and the two men from the assaults.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

import pytest

from adapters.graph_arcadedb.weight import compute_weight
from demo_fixtures import pid_plan
from ontology.influencers import connection_strength, load_strength_defaults, resolve_influencers
from ontology.weights import load_weight_rules
from schemas.domain import WeightComponents
from schemas.strength import CaseInfluencersInput, InfluencerTrigger, StrengthInfluencer

RULES = load_weight_rules()
PLAN = pid_plan.build_plan("demo")
LINKS = pid_plan.links_at(PLAN, "chapter4", secret_cleared=False)
KIND = {e.key: e.entity_type for e in PLAN.entities}
PROPS = {e.key: e.properties for e in PLAN.entities}
NEIGHBOURS: dict[str, set[str]] = defaultdict(set)
for _link in LINKS:
    NEIGHBOURS[_link.source].add(_link.target)
    NEIGHBOURS[_link.target].add(_link.source)

CUT_OFF = datetime.combine(pid_plan.CUT_OFF, datetime.min.time(), tzinfo=UTC)
LOAD_DATES = [CUT_OFF, CUT_OFF + timedelta(days=183)]

#: The case's own influencer the scene's Author adds (CAP-S6).
CASE_ASSAULT = StrengthInfluencer(
    id="assault-in-this-case", label="Assault in this case", link_types=["IN_CONFLICT_WITH"],
    change="floor", size=0.95,
    trigger=InfluencerTrigger(entity_type="Incident", property="category", values=["assault"]),
)  # fmt: skip


def _utc(value: date | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    return datetime(value.year, value.month, value.day, tzinfo=UTC)


def _weight(link: pid_plan.PlanLink, now: datetime) -> float:
    return compute_weight(
        WeightComponents(occurrences=link.occurrences, corpus_pair_count=0, corpus_source_degree=0,
                         corpus_target_degree=0, corpus_total_occurrences=0, computed_at=now),
        edge_type=link.link_type, valid_to=_utc(link.last_seen), now=now, rules=RULES,
        self_loop=link.source == link.target,
    )  # fmt: skip


def _evidence(link: pid_plan.PlanLink, active: list) -> dict[str, str]:  # type: ignore[type-arg]
    """As the graph adapter finds it: a record of the trigger's type and value at one end, or linked
    to both ends."""
    found: dict[str, str] = {}
    for a in active:
        trigger = a.influencer.trigger
        if trigger is None or link.link_type not in a.influencer.link_types:
            continue
        records = {
            k for k in {link.source, link.target} | (NEIGHBOURS[link.source] & NEIGHBOURS[link.target])
            if KIND.get(k) == trigger.entity_type
            and str(PROPS[k].get(trigger.property)) in trigger.values
        }  # fmt: skip
        if records:
            found[a.influencer.id] = trigger.entity_type
    return found


def _strength(link: pid_plan.PlanLink, now: datetime, active: list) -> tuple[float, float, list[str]]:  # type: ignore[type-arg]
    base = _weight(link, now)
    strength, applied = connection_strength(base, link.link_type, active, _evidence(link, active), RULES)
    return base, strength, [a.id for a in applied]


def _link(link_type: str, a: str, b: str) -> pid_plan.PlanLink:
    (found,) = [lk for lk in LINKS if lk.link_type == link_type and {lk.source, lk.target} == {a, b}]
    return found


SHIPPED, _ = resolve_influencers(load_strength_defaults().influencers)


@pytest.mark.parametrize("now", LOAD_DATES, ids=["at-cut-off", "six-months-on"])
def test_an_assault_evidenced_conflict_is_drawn_stronger(now: datetime) -> None:
    conflict = _link("IN_CONFLICT_WITH", "principal", "calder_1")
    assert PROPS["incident:assault_1"]["category"] == "assault"
    assert "incident:assault_1" in NEIGHBOURS["principal"] & NEIGHBOURS["calder_1"]
    base, strength, applied = _strength(conflict, now, SHIPPED)
    assert applied == ["incident-source"]
    assert strength > base


@pytest.mark.parametrize("now", LOAD_DATES, ids=["at-cut-off", "six-months-on"])
def test_a_direct_call_against_a_shared_address(now: datetime) -> None:
    # Two men who held cell F1-03 at different times share that address in custody, and no link.
    assert "cell:F1-03" in NEIGHBOURS["cellmate_1"] & NEIGHBOURS["cellmate_2"]
    assert "cellmate_2" not in NEIGHBOURS["cellmate_1"]
    stays = [_link("PRESENT_AT", who, "cell:F1-03") for who in ("cellmate_1", "cellmate_2")]
    for stay in stays:
        assert _strength(stay, now, SHIPPED)[2] == []  # an address is not a direct link
    call = _link("COMMUNICATED_WITH", "pin:principal", "number:coordinator")
    base, strength, applied = _strength(call, now, SHIPPED)
    assert applied == ["direct"] and strength > base
    assert strength > max(_strength(stay, now, SHIPPED)[1] for stay in stays)


def test_a_rare_shared_contact_ranks_above_a_common_one() -> None:
    people = {k for k, t in KIND.items() if t == "Person"}
    shared = NEIGHBOURS["relay_1"] & NEIGHBOURS["relay_2"]

    def score(attribute: str) -> float:
        return math.log(len(people) / len(NEIGHBOURS[attribute] & people))

    assert {"relay_4", "principal", "est:fenwick-moor"} <= shared
    # relay_4 knows three people; the principal is linked to many; everyone is held at Fenwick Moor.
    assert score("relay_4") > score("principal") > score("est:fenwick-moor")


@pytest.mark.parametrize("now", LOAD_DATES, ids=["at-cut-off", "six-months-on"])
def test_a_strength_rule_with_the_cases_own_influencer_raises_exactly_the_assault_conflicts(
    now: datetime,
) -> None:
    case, _ = resolve_influencers(
        load_strength_defaults().influencers, None, CaseInfluencersInput(added=[CASE_ASSAULT]),
        case_version=1,
    )  # fmt: skip
    conflicts = [lk for lk in LINKS if lk.link_type == "IN_CONFLICT_WITH"]
    reached = {
        end
        for lk in conflicts
        if _strength(lk, now, case)[1] >= 0.95
        for end in (lk.source, lk.target)
    }
    assert reached == {"principal", "calder_1", "calder_2"}
    # Without the case's own influencer, nothing reaches it: the rule says what the case added.
    assert not any(_strength(lk, now, SHIPPED)[1] >= 0.95 for lk in conflicts)
