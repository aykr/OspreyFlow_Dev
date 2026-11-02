"""The Prison Intelligence demo shows both compositions on one case (ADR-139 Amendment 2, ruling 5;
ADR-127 Amendment 43): the case's Author switches it to client parity through a case override, and
back. Proved on the plan without a store, as `test_pid_connection_strength.py` proves the standard
scene: no generator changed, every claim rests on data the case already holds.

Worked out as the store works them out: the stored weight by `compute_weight` with the shipped
weights file; standard strength by `connection_strength`; client parity by `parity_strength`, with a
stored link's rarity term `1 − 1/n` over the visible links of its type (the case is one dataset and
OFFICIAL throughout, so every analyst sees all of it, as the client's analysts do), and a shared
value's by `share_rarity(C(k, 2), Σ C(k_b, 2))` over the values of its kind. Each claim is checked
at two load dates; client parity has no recency, so its figures are the same at both.

The scene's claims, each a test (capture steps `CAP-S7` to `CAP-S10`, not yet run):
- the switch itself, and back (CAP-S7, CAP-S10);
- under client parity a call's count and age no longer draw it heavier: the principal's busiest call
  and the case's quietest are drawn alike, at the client's raw sum (CAP-S8);
- the assault-evidenced conflict: under the standard composition busier or fresher plain conflicts
  draw above it; under client parity it is above every plain conflict, since only the adds separate
  them (CAP-S8);
- the rare shared contact ranks first under the client's own measure, as under IDF (CAP-S9).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta

import pytest

from adapters.graph_arcadedb.weight import compute_weight
from demo_fixtures import pid_plan
from ontology.influencers import (
    StrengthDefaults,
    connection_strength,
    load_strength_defaults,
    pair_links,
    parity_drawn,
    parity_strength,
    resolve_influencers,
    resolve_settings,
    share_rarity,
)
from ontology.weights import load_weight_rules
from schemas.domain import WeightComponents
from schemas.strength import CaseInfluencersInput

RULES = load_weight_rules()
DEFAULTS: StrengthDefaults = load_strength_defaults()
PLAN = pid_plan.build_plan("demo")
LINKS = pid_plan.links_at(PLAN, "chapter4", secret_cleared=False)
KIND = {e.key: e.entity_type for e in PLAN.entities}
PROPS = {e.key: e.properties for e in PLAN.entities}
NEIGHBOURS: dict[str, set[str]] = defaultdict(set)
for _link in LINKS:
    NEIGHBOURS[_link.source].add(_link.target)
    NEIGHBOURS[_link.target].add(_link.source)
PER_TYPE = Counter(link.link_type for link in LINKS)
PEOPLE = {k for k, t in KIND.items() if t == "Person"}

CUT_OFF = datetime.combine(pid_plan.CUT_OFF, datetime.min.time(), tzinfo=UTC)
LOAD_DATES = [CUT_OFF, CUT_OFF + timedelta(days=183)]
SHIPPED, _ = resolve_influencers(DEFAULTS.influencers)
#: The case's own override in the scene: client parity, nothing added or switched off.
PARITY_OVERRIDE = CaseInfluencersInput(composition="client_parity")


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


def _evidence(link: pid_plan.PlanLink) -> dict[str, str]:
    """As the graph adapter finds it: a record of the trigger's type and value at one end, or linked
    to both ends."""
    found: dict[str, str] = {}
    for a in SHIPPED:
        trigger = a.influencer.trigger
        if trigger is None or link.link_type not in a.influencer.link_types:
            continue
        ends = {link.source, link.target} | (NEIGHBOURS[link.source] & NEIGHBOURS[link.target])
        kind = getattr(trigger, "entity_type", None)
        prop, values = getattr(trigger, "property", ""), getattr(trigger, "values", [])
        if any(KIND.get(k) == kind and str(PROPS[k].get(prop)) in values for k in ends):
            found[a.influencer.id] = str(getattr(trigger, "entity_type", ""))
    return found


def _standard(link: pid_plan.PlanLink, now: datetime) -> float:
    weight = _weight(link, now)
    return connection_strength(weight, link.link_type, SHIPPED, _evidence(link), RULES)[0]


def _parity(link: pid_plan.PlanLink) -> tuple[float, float]:
    """The raw sum on the client's scale and the drawn strength: the link's own rarity term among
    the links of its type in the case's one dataset, plus the shipped adds that apply."""
    term = share_rarity(1, PER_TYPE[link.link_type])
    raw, drawn, _ = parity_strength(term, link.link_type, SHIPPED, _evidence(link))
    return raw, drawn


def _link(link_type: str, a: str, b: str) -> pid_plan.PlanLink:
    (found,) = [
        lk for lk in LINKS if lk.link_type == link_type and {lk.source, lk.target} == {a, b}
    ]
    return found


def test_the_cases_author_switches_it_to_client_parity_and_back() -> None:
    """CAP-S7 and CAP-S10: the case's own override chooses client parity for this case alone, and
    clearing it restores the shipped composition. The parity sum reads the client's measure."""
    switched = resolve_settings(DEFAULTS, None, None, PARITY_OVERRIDE.composition)
    assert (switched.composition, switched.composition_layer, switched.rarity_measure) == (
        "client_parity", "case", "share",
    )  # fmt: skip
    back = resolve_settings(DEFAULTS, None, None, CaseInfluencersInput().composition)
    assert (back.composition, back.composition_layer) == ("standard", "file")


@pytest.mark.parametrize("now", LOAD_DATES, ids=["at-cut-off", "six-months-on"])
def test_under_client_parity_a_calls_count_and_age_no_longer_draw_it_heavier(now: datetime) -> None:
    """CAP-S8: the principal's PIN calls to the coordinator are the case's busiest call (201); a
    call seen once is the quietest. Standard draws the busy one heavier; client parity draws them
    alike, at `1 − 1/2,572 + 0.1348` (the direct add), the same at either load date."""
    calls = [lk for lk in LINKS if lk.link_type == "COMMUNICATED_WITH"]
    busiest = _link("COMMUNICATED_WITH", "pin:principal", "number:coordinator")
    assert busiest.occurrences == max(c.occurrences for c in calls) == 201
    quietest = min(calls, key=lambda c: (c.occurrences, c.key))
    assert quietest.occurrences == 1
    assert _standard(busiest, now) > _standard(quietest, now)
    raw, drawn = _parity(busiest)
    assert _parity(quietest) == (raw, drawn)
    assert PER_TYPE["COMMUNICATED_WITH"] == 2572
    assert raw == pytest.approx(1 - 1 / 2572 + 0.1348)
    assert round(raw, 4) == 1.1344 and round(drawn, 2) == 0.79
    assert drawn == pytest.approx(parity_drawn(raw))


@pytest.mark.parametrize("now", LOAD_DATES, ids=["at-cut-off", "six-months-on"])
def test_under_client_parity_the_assault_evidenced_conflict_is_above_every_plain_one(
    now: datetime,
) -> None:
    """CAP-S8, the two compositions side by side. The principal's conflict with calder_1 is
    evidenced by assault_1; 94 conflicts no assault, disorder or find evidences are plain. Under the
    standard composition some plain conflicts, busier or fresher, draw above it (count and recency
    count). Under client parity it is above every one of them: they share one rarity term
    (`1 − 1/96`), and only its assault add (0.1348) separates them."""
    evidenced = _link("IN_CONFLICT_WITH", "principal", "calder_1")
    assert _evidence(evidenced) == {"incident-source": "Incident"}
    plain = [lk for lk in LINKS if lk.link_type == "IN_CONFLICT_WITH" and not _evidence(lk)]
    assert len(plain) == 94
    assert any(_standard(lk, now) > _standard(evidenced, now) for lk in plain)
    assert {round(_parity(lk)[0], 12) for lk in plain} == {round(1 - 1 / 96, 12)}
    assert _parity(evidenced)[0] == pytest.approx(1 - 1 / 96 + 0.1348)
    assert round(_parity(evidenced)[0], 4) == 1.1244
    assert all(_parity(evidenced)[1] > _parity(lk)[1] for lk in plain)


def _share(value: str) -> float:
    """The client's rarity of one value: its pair links among the case's persons against those of
    every value of its kind."""
    kind = KIND[value]
    total = sum(pair_links(len(NEIGHBOURS[b] & PEOPLE)) for b, t in KIND.items() if t == kind)
    return share_rarity(pair_links(len(NEIGHBOURS[value] & PEOPLE)), total)


def test_the_rare_shared_contact_ranks_first_under_the_clients_measure() -> None:
    """CAP-S9: relay_1 and relay_2 share relay_4 (three people are linked to him), the principal
    (many) and Fenwick Moor (everyone). Under the client's share measure the order is the IDF
    measure's: relay_4, then the principal, then the establishment; the pair's rarity is relay_4's,
    and with no shipped add on a shared value its parity sum is the same figure."""
    shared = NEIGHBOURS["relay_1"] & NEIGHBOURS["relay_2"]
    assert {"relay_4", "principal", "est:fenwick-moor"} <= shared
    assert _share("relay_4") > _share("principal") > _share("est:fenwick-moor")
    assert round(_share("relay_4"), 4) == 0.9994
    assert round(_share("principal"), 4) == 0.9383
    assert round(_share("est:fenwick-moor"), 4) == 0.1562
    pair = max(_share(a) for a in shared)
    assert pair == _share("relay_4")
    raw, _, applied = parity_strength(pair, "SHARED_VALUE", SHIPPED, {})
    assert raw == pair and applied == []
