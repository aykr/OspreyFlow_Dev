"""The HMP pack's prison intelligence network (`06_DECISIONS.md` ADR-117): the custody links,
incidents, visitors, phones and payments around the fixture's principal subject and relay group,
drawn so a prison analyst's own questions have something real to find.

**The story it carries, by construction rather than by chance.** The principal subject
(`HMP-0001`) runs a supply network inside HMP Hollywood with the relay group (`HMP-0003` to
`HMP-0010`). Outside, a coordinator visits the principal in person and a relay member by video,
and the principal and three relay members all call the coordinator's number (the shared-number
pattern); one outside account pays the private cash of the principal and two relay members (the
shared-payer pattern). Calls to the coordinator surge in the weeks before a run of finds of mobile
phones and spice in the relay group's cells. The principal has a long cell history (many
cellmates, the star a network viewer draws), two co-defendants in the relay group, and conflicts,
one of them known only from covert intelligence and so marked SECRET (the access-control step of
the demonstration). Around them, a general population with its own ordinary cell shares, family
visits, calls and payments, so the network is not only the story.

**Everything is invented** (rule 9). Prison numbers are this fixture's own `HMP-nnnn`; visitors'
National Insurance numbers use the `QQ` prefix, which is never issued; phone numbers are in
Ofcom's range reserved for drama (07700 900000 to 900999); accounts are at a fictional bank. HMP
Hollywood's point is open country near Warwick, where there is no prison; the outside places are
town centres, offset a little at random.

Deterministic: `plan_network()` builds the same plan on every call (one seeded generator), and
the plan is pure — keys, not ids — so its shape is tested without a store
(`tests/scenarios/test_hmp_network.py`). `write_hmp_network` writes it through `GraphPort` and
returns the analytics events, each tied to the summarised link it is one occurrence of.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from conduit_common.identity import new_edge_id, new_node_id
from ports.graph import GraphPort
from schemas.analytics import EventRecord
from schemas.domain import (
    EdgeId,
    EdgeWrite,
    Handling,
    Interval,
    NodeId,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)

from .hmp_population import (
    PRINCIPAL_SUBJECT_INDEX,
    RELAY_GROUP_INDICES,
    SECOND_SUBJECT_INDEX,
    TOTAL_PERSONS,
    prison_number_for_index,
)

#: HMP Hollywood, a fictional prison: open country between Warwick and Southam, where there is none.
PRISON_POINT: tuple[float, float] = (52.2600, -1.4900)

#: Town centres the outside network lives in (offset a little per person at random).
TOWNS: dict[str, tuple[float, float]] = {
    "Birmingham": (52.4862, -1.8904),
    "Coventry": (52.4068, -1.5197),
    "Leicester": (52.6369, -1.1398),
    "Wolverhampton": (52.5870, -2.1288),
    "Northampton": (52.2405, -0.9027),
    "Oxford": (51.7520, -1.2577),
    "London": (51.5072, -0.1276),
    "Nottingham": (52.9548, -1.1581),
}

#: The network's own span; the finds fall in the fixture's incident window (`hmp.py`).
NETWORK_START = date(2025, 4, 1)
SURGE_START = date(2025, 12, 1)
NETWORK_END = date(2026, 3, 6)

_SOURCE = "hmp-network"


@dataclass(frozen=True)
class EventSpec:
    at: datetime
    point: tuple[float, float] | None = None
    duration_s: float | None = None
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NodeSpec:
    key: str
    type: str
    properties: dict[str, Any]


@dataclass(frozen=True)
class EdgeSpec:
    type: str
    source: str
    target: str
    properties: dict[str, Any] = field(default_factory=dict)
    interval: tuple[datetime, datetime] | None = None
    events: tuple[EventSpec, ...] = ()
    classification: str = "OFFICIAL"

    @property
    def occurrences(self) -> int:
        return max(1, len(self.events))


@dataclass
class NetworkPlan:
    """Keys: `prisoner:<index>` for the existing population (resolved by prison number at write),
    and `visitor:`, `phone:`, `pin:`, `account:`, `incident:` for what this module adds."""

    nodes: list[NodeSpec] = field(default_factory=list)
    edges: list[EdgeSpec] = field(default_factory=list)


def prisoner(index: int) -> str:
    return f"prisoner:{index}"


P = PRINCIPAL_SUBJECT_INDEX
SECOND = SECOND_SUBJECT_INDEX
R = RELAY_GROUP_INDICES  # eight: R[0] is HMP-0003 ... R[7] is HMP-0010
#: The outside coordinator, the shared payer, and their numbers and account.
COORDINATOR = "visitor:0"
COORDINATOR_PHONE = "phone:+447700900100"
PAYER = "visitor:1"
SHARED_ACCOUNT = "account:SYN-40001"
#: The conflict known only from covert intelligence (the access-control step).
SECRET_CONFLICT = (P, 11)

_VISITOR_FAMILY = (
    "ASHWORTH", "BRANNIGAN", "CHAUDHRY", "DUNMORE", "ELLISON", "FAIRCLOUGH", "GALLAGHER",
    "HUSSAIN", "IKEDA", "JANKOWSKA", "KILBRIDE", "LOVELL", "MORCOMBE", "NWOSU", "OGDEN",
    "PRENDERGAST", "QUAYLE", "ROWNTREE", "STACEY", "THORNBURY", "UMEH", "VARGA", "WINTERTON",
    "YARDLEY",
)
_VISITOR_GIVEN = (
    "Dean", "Kerry", "Shane", "Leanne", "Jordan", "Tasha", "Reece", "Jodie", "Kyle", "Shona",
    "Wayne", "Carly",
)


def _dt(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), tzinfo=UTC)


def _days(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def plan_network(seed: int = 117) -> NetworkPlan:
    rng = random.Random(seed)
    plan = NetworkPlan()
    general = [i for i in range(TOTAL_PERSONS) if i not in {P, SECOND, *R}]

    def near(town: str) -> tuple[float, float]:
        lat, lon = TOWNS[town]
        return (round(lat + rng.uniform(-0.03, 0.03), 5), round(lon + rng.uniform(-0.04, 0.04), 5))

    # --- people outside -------------------------------------------------------------------
    visitor_towns: dict[str, str] = {}
    for n in range(24):
        key = f"visitor:{n}"
        town = (
            "Birmingham" if n == 0 else "Leicester" if n == 1 else rng.choice(sorted(TOWNS))
        )
        visitor_towns[key] = town
        plan.nodes.append(
            NodeSpec(
                key,
                "Person",
                {
                    "nino": f"QQ{100000 + n * 137:06d}{'ABCD'[n % 4]}",
                    "family_name": _VISITOR_FAMILY[n],
                    "given_names": _VISITOR_GIVEN[n % len(_VISITOR_GIVEN)],
                    "date_of_birth": date(1968 + (n * 5) % 35, 1 + n % 12, 1 + (n * 3) % 27)
                    .isoformat(),
                },
            )
        )

    # --- phones: each person's number, and calls ------------------------------------------
    def phone(key: str, number: int) -> str:
        e164 = f"+447700900{number:03d}"
        node_key = f"phone:{e164}"
        plan.nodes.append(
            NodeSpec(
                node_key,
                "Endpoint",
                {
                    "e164": e164,
                    "value_raw": f"07700 900{number:03d}",
                    "value_normalised": e164,
                    "endpoint_kind": "msisdn",
                },
            )
        )
        plan.edges.append(EdgeSpec("USES", key, node_key))
        return node_key

    def pin(index: int) -> str:
        number = prison_number_for_index(index)
        node_key = f"pin:{number}"
        plan.nodes.append(
            NodeSpec(
                node_key,
                "Endpoint",
                {
                    "handle": f"pin:{number.lower()}",
                    "value_raw": f"PIN phone account {number}",
                    "value_normalised": f"pin:{number.lower()}",
                    "endpoint_kind": "account",
                },
            )
        )
        plan.edges.append(EdgeSpec("USES", prisoner(index), node_key))
        return node_key

    def calls(
        caller: str, callee: str, town: str, count: int, *, surge: bool = False
    ) -> EdgeSpec:
        """`count` calls spread over the network's span; with `surge`, two in three of them in
        the weeks before the finds."""
        quiet_days = _days(NETWORK_START, SURGE_START - timedelta(days=1))
        surge_days = _days(SURGE_START, NETWORK_END)
        events = []
        for i in range(count):
            pool = surge_days if surge and i % 3 != 0 else quiet_days + surge_days
            day = rng.choice(pool)
            at = _dt(day, rng.choice((9, 11, 13, 17, 18, 19)), rng.randrange(0, 60, 5))
            events.append(
                EventSpec(
                    at,
                    near(town),
                    duration_s=float(rng.randint(40, 600)),
                    properties={"direction": "outbound"},
                )
            )
        events.sort(key=lambda e: e.at)
        spec = EdgeSpec(
            "COMMUNICATED_WITH",
            caller,
            callee,
            interval=(events[0].at, events[-1].at),
            events=tuple(events),
        )
        plan.edges.append(spec)
        return spec

    coordinator_phone = phone(COORDINATOR, 100)
    assert coordinator_phone == COORDINATOR_PHONE
    london_phone = phone("visitor:2", 101)
    pins = {i: pin(i) for i in (P, SECOND, *R)}
    # The shared number: the principal and three relay members all call the coordinator.
    calls(pins[P], coordinator_phone, "Birmingham", 46, surge=True)
    for member, count in ((R[1], 22), (R[3], 18), (R[5], 15)):
        calls(pins[member], coordinator_phone, "Birmingham", count, surge=True)
    calls(pins[P], london_phone, "London", 12)
    calls(pins[R[0]], london_phone, "London", 9)
    calls(pins[SECOND], phone("visitor:3", 102), visitor_towns["visitor:3"], 14)
    # The general population's own calls home, one number each.
    for n, index in enumerate(general[:40]):
        family_key = f"visitor:{4 + n % 20}"
        number = phone(family_key, 110 + n) if n < 20 else f"phone:+447700900{110 + n - 20:03d}"
        calls(pin(index), number, visitor_towns[family_key], rng.randint(3, 14))

    # --- visits -------------------------------------------------------------------------
    def visits(visitor: str, index: int, channel: str, count: int) -> None:
        days = sorted(rng.sample(_days(NETWORK_START, NETWORK_END), count))
        events = tuple(
            EventSpec(
                _dt(day, 14 if channel == "in_person" else 18, 0),
                PRISON_POINT,
                duration_s=3600.0 if channel == "in_person" else 1800.0,
                properties={"channel": channel},
            )
            for day in days
        )
        plan.edges.append(
            EdgeSpec(
                "VISITED",
                visitor,
                prisoner(index),
                {"channel": channel},
                interval=(events[0].at, events[-1].at),
                events=events,
            )
        )

    visits(COORDINATOR, P, "in_person", 7)  # the coordinator visits the principal
    visits(COORDINATOR, R[1], "video", 5)  # and a relay member, by video: a third-party link
    visits("visitor:2", R[0], "in_person", 4)
    visits(PAYER, R[3], "video", 3)
    visits("visitor:3", SECOND, "in_person", 6)
    for n, index in enumerate(general[:30]):
        visits(f"visitor:{4 + n % 20}", index, "video" if n % 3 == 0 else "in_person",
               rng.randint(1, 5))

    # --- money --------------------------------------------------------------------------
    def account(holder: str, number: str, *, institution: str, name: str) -> str:
        node_key = f"account:{number}"
        plan.nodes.append(
            NodeSpec(
                node_key,
                "Account",
                {
                    "account_number": number,
                    "institution": institution,
                    "currency": "GBP",
                    "name": name,
                },
            )
        )
        plan.edges.append(EdgeSpec("HOLDS_ACCOUNT", holder, node_key))
        return node_key

    def private_cash(index: int) -> str:
        number = prison_number_for_index(index)
        return account(
            prisoner(index), f"PC-{number}", institution="HMP Hollywood private cash",
            name=f"Private cash {number}",
        )

    def payments(payer: str, payee: str, town: str, count: int) -> None:
        days = sorted(rng.sample(_days(NETWORK_START, NETWORK_END), count))
        events = tuple(
            EventSpec(
                _dt(day, 10, 30),
                near(town),
                properties={
                    "amount": float(rng.choice((25, 40, 50, 60, 75, 90, 100, 150))),
                    "transaction_type": "TRANSFER",
                },
            )
            for day in days
        )
        plan.edges.append(
            EdgeSpec(
                "TRANSACTED", payer, payee, interval=(events[0].at, events[-1].at), events=events
            )
        )

    shared = account(PAYER, "SYN-40001", institution="Fictional Bank", name="L. Dunmore current")
    assert shared == SHARED_ACCOUNT
    coordinator_account = account(
        COORDINATOR, "SYN-40002", institution="Fictional Bank", name="D. Ashworth current"
    )
    cash = {i: private_cash(i) for i in (P, R[0], R[2], R[4])}
    # The shared payer: one outside account funds the principal and two relay members.
    payments(shared, cash[P], "Leicester", 9)
    payments(shared, cash[R[2]], "Leicester", 6)
    payments(shared, cash[R[4]], "Leicester", 5)
    payments(coordinator_account, cash[R[0]], "Birmingham", 4)
    for n, index in enumerate(general[:12]):
        family_key = f"visitor:{4 + n}"
        family_account = account(
            family_key, f"SYN-{40100 + n}", institution="Fictional Bank",
            name=f"{_VISITOR_FAMILY[4 + n].title()} current",
        )
        payments(family_account, private_cash(index), visitor_towns[family_key], rng.randint(1, 4))

    # --- custody links ------------------------------------------------------------------
    def cellshare(a: int, b: int, start: date, weeks: int) -> None:
        end = start + timedelta(weeks=weeks)
        plan.edges.append(
            EdgeSpec(
                "SHARED_CELL_WITH",
                prisoner(a),
                prisoner(b),
                {"cell": f"Wing {a % 8 + 1}, Cell {rng.randint(1, 60)}"},
                interval=(_dt(start, 9), _dt(end, 9)),
                events=(EventSpec(_dt(start, 9), PRISON_POINT, properties={"weeks": weeks}),),
            )
        )

    # The principal's long cell history: the star a network viewer draws around them.
    start = date(2024, 6, 3)
    for mate in general[:14]:
        weeks = rng.randint(3, 8)
        cellshare(P, mate, start, weeks)
        start += timedelta(weeks=weeks)
    cellshare(P, R[4], date(2024, 3, 4), 10)
    for a, b in ((R[0], R[1]), (R[2], R[3]), (R[4], R[5]), (R[6], R[7]), (R[1], R[5])):
        cellshare(a, b, rng.choice(_days(NETWORK_START, SURGE_START)), rng.randint(4, 12))
    for _ in range(90):
        a, b = rng.sample(general, 2)
        cellshare(a, b, rng.choice(_days(date(2024, 1, 1), NETWORK_END)), rng.randint(2, 10))

    for a, b, case in (
        (P, R[0], "CASE-2022-0441"), (P, R[1], "CASE-2022-0441"), (R[0], R[1], "CASE-2022-0441"),
        (R[6], R[7], "CASE-2023-1187"),
    ):
        plan.edges.append(EdgeSpec("CO_DEFENDANT_OF", prisoner(a), prisoner(b), {"case_ref": case}))
    for n in range(12):
        a, b = rng.sample(general, 2)
        plan.edges.append(
            EdgeSpec(
                "CO_DEFENDANT_OF", prisoner(a), prisoner(b), {"case_ref": f"CASE-2021-{n:04d}"}
            )
        )

    def conflict(a: int, b: int, reason: str, day: date, classification: str = "OFFICIAL") -> None:
        plan.edges.append(
            EdgeSpec(
                "IN_CONFLICT_WITH",
                prisoner(a),
                prisoner(b),
                {"reason": reason},
                interval=(_dt(day, 12), _dt(NETWORK_END, 12)),
                events=(EventSpec(_dt(day, 12), PRISON_POINT, properties={"reason": reason}),),
                classification=classification,
            )
        )

    conflict(P, 10, "debt", date(2025, 9, 14))
    conflict(*SECRET_CONFLICT, "rival supply", date(2025, 11, 2), classification="SECRET")
    conflict(R[7], 12, "assault on a relative", date(2026, 1, 20))
    for n in range(6):
        a, b = rng.sample(general, 2)
        conflict(a, b, rng.choice(("debt", "gang rivalry", "keep apart")), date(2025, 6 + n, 10))

    # --- incidents and who was involved -----------------------------------------------
    finds = (
        ("mobile phone", R[1]), ("mobile phone", R[3]), ("SIM card", R[3]), ("spice", R[5]),
        ("mobile phone", R[0]), ("spice", R[1]), ("cannabis", R[6]), ("mobile phone", R[5]),
        ("spice", R[2]), ("SIM card", R[0]), ("improvised weapon", R[7]), ("mobile phone", R[4]),
    )
    incident_days = _days(date(2026, 1, 5), NETWORK_END)
    yards = "ABCDEFGHIJ"
    n_incident = 0

    def incident(category: str, title: str, item: str | None, roles: list[tuple[int, str]]) -> None:
        nonlocal n_incident
        n_incident += 1
        day = incident_days[(n_incident * 7) % len(incident_days)]
        at = _dt(day, rng.choice((10, 11, 14, 15, 16)), rng.randrange(0, 60, 5))
        ref = f"IR-2026-{n_incident:04d}"
        yard = yards[rng.randrange(4)] if category != "find" else yards[n_incident % 10]
        properties: dict[str, Any] = {
            "incident_ref": ref,
            "name": f"{title}, Yard {yard} ({ref})",
            "category": category,
            "occurred_at": at.isoformat(),
        }
        if item:
            properties["item"] = item
        key = f"incident:{ref}"
        plan.nodes.append(NodeSpec(key, "Incident", properties))
        for index, role in roles:
            plan.edges.append(
                EdgeSpec(
                    "ROLE_IN",
                    prisoner(index),
                    key,
                    {"role": role},
                    interval=(at, at),
                    events=(
                        EventSpec(
                            at, PRISON_POINT, properties={"category": category, "role": role}
                        ),
                    ),
                )
            )

    for item, holder in finds:
        roles = [(holder, "found in possession")]
        if item in {"mobile phone", "SIM card"}:
            roles.append((P, "suspected owner"))
        incident("find", f"Find: {item}", item, roles)
    assaults = ((P, 10), (R[7], 12), (R[2], general[20]), (R[6], general[21]), (P, general[22]),
                (R[0], general[23]), (general[24], general[25]), (general[26], general[27]))
    for assailant, victim in assaults:
        incident("assault", "Assault", None, [(assailant, "assailant"), (victim, "victim")])
    for n in range(6):
        participants = [R[n % 8], R[(n + 3) % 8], *rng.sample(general[30:80], 2)]
        incident("disorder", "Disorder", None, [(i, "participant") for i in participants])

    return plan


def _handling(classification: str = "OFFICIAL") -> Handling:
    return Handling(
        classification=classification,
        handling_code="P",
        originator="hmp-hollywood",
        owning_unit="hmp-hollywood",
    )


def _provenance(label: str) -> Provenance:
    return Provenance(
        state=ProvenanceState.ASSERTED,
        sources=[SourceRef(document_id=_SOURCE, locator=label, excerpt_hash="")],
        first_seen=datetime.now(UTC),
    )


_CHUNK = 40


async def write_hmp_network(
    *,
    graph: GraphPort,
    person_ids: dict[str, NodeId],
    principal: Principal,
    investigation_scope: str,
    load_id_prefix: str = "load-hmp-network",
    plan: NetworkPlan | None = None,
) -> list[EventRecord]:
    """Writes the plan through `GraphPort` (nodes, then links, each in committed chunks, as
    `hmp_graph.py` does and for its reasons) and returns the analytics events. `person_ids` is
    `HmpGraphResult.person_node_ids`: prison number to node id."""
    plan = plan if plan is not None else plan_network()
    now = datetime.now(UTC)
    ids: dict[str, NodeId] = {
        prisoner(index): person_ids[prison_number_for_index(index)]
        for index in range(TOTAL_PERSONS)
    }
    node_writes: list[NodeWrite] = []
    for node in plan.nodes:
        if node.key in ids:
            continue  # a phone or account named twice in the plan is one node
        ids[node.key] = new_node_id()
        node_writes.append(
            NodeWrite(
                id=ids[node.key],
                type=node.type,
                properties=node.properties,
                provenance=_provenance(node.key),
                handling=_handling(),
                created_by=principal.id,
                created_at=now,
                load_id=f"{load_id_prefix}-nodes",
            )
        )
    for i in range(0, len(node_writes), _CHUNK):
        tx = await graph.begin_transaction()
        try:
            await graph.upsert_nodes(node_writes[i : i + _CHUNK], tx)
        except Exception:
            await graph.rollback_transaction(tx)
            raise
        await graph.commit_transaction(tx)

    edge_writes = [
        EdgeWrite(
            id=new_edge_id(),
            type=spec.type,
            source=ids[spec.source],
            target=ids[spec.target],
            properties=spec.properties,
            interval=(
                Interval(valid_from=spec.interval[0], valid_to=spec.interval[1])
                if spec.interval
                else None
            ),
            occurrences=spec.occurrences,
            provenance=_provenance(f"{spec.type}:{spec.source}:{spec.target}"),
            handling=_handling(spec.classification),
            created_by=principal.id,
            created_at=now,
            load_id=f"{load_id_prefix}-links",
        )
        for spec in plan.edges
    ]
    edge_ids: list[EdgeId] = []
    for i in range(0, len(edge_writes), _CHUNK):
        tx = await graph.begin_transaction()
        try:
            edge_ids.extend(await graph.upsert_edges(edge_writes[i : i + _CHUNK], tx))
        except Exception:
            await graph.rollback_transaction(tx)
            raise
        await graph.commit_transaction(tx)

    events: list[EventRecord] = []
    for spec, write, edge_id in zip(plan.edges, edge_writes, edge_ids, strict=True):
        for n, event in enumerate(spec.events):
            events.append(
                EventRecord(
                    event_id=f"{edge_id}-{n:04d}",
                    edge_id=edge_id,
                    edge_type=spec.type,
                    source_id=write.source,
                    target_id=write.target,
                    occurred_at=event.at,
                    duration_s=event.duration_s,
                    lat=event.point[0] if event.point else None,
                    lon=event.point[1] if event.point else None,
                    direction=event.properties.get("direction"),
                    properties={k: v for k, v in event.properties.items() if k != "direction"},
                    investigation_scope=investigation_scope,
                    handling=_handling(spec.classification),
                )
            )
    return events
