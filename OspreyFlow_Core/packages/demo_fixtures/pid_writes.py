"""The Prison Intelligence Dataset's plan as graph writes (ADR-120 Amendments 9 to 11; stage 5).

`writes(plan, moment, ...)` turns everything the plan holds by the end of a moment into
`NodeWrite` and `EdgeWrite` lists for the graph port; the live access test and Brief 2's seed (for
D8's `PASSES_ITEMS_TO`) both use it. Ids are the plan's derived ids (`node_id`, `link_id`). A
link's interval comes from the one function that dates it, `link_instants`: the first to the last
instant of its rows, or, for a span (a custody, a cell stay, a cell-line pass), its first date's
start to its last date's end, open where it has no last date. Picture Documents and their `DEPICTS`
links are left out: the picture route writes those (`picture_writes` gives it the files).

Dates in properties are ISO strings, as every other fixture writes them. `datasets` is the one
dataset named. Provenance's one source is `<the dataset's source>:<dataset id>`, so that
`scripts.stamp_datasets` finds each of the two datasets' elements and never the other's; a dataset
that is not one of the two is refused, and so is a plan written into the other
profile's dataset.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime
from typing import Any

from knowledge_adapters.imei import imei
from knowledge_adapters.imsi import imsi
from schemas.domain import (
    EdgeWrite,
    Handling,
    Interval,
    NodeWrite,
    Provenance,
    ProvenanceState,
    SourceRef,
)

from . import pid_pictures
from .datasets import PID, PID_SCALE
from .pid_plan import (
    _MOMENT_ORDER,
    Moment,
    Plan,
    PlanEntity,
    PlanHandling,
    PlanLink,
    end_of,
    entity_moment,
    link_id,
    link_instants,
    links_at,
    node_id,
    start_of,
)

CREATED_BY = "pid-generator"
_SPANS = frozenset({"HELD_AT", "PRESENT_AT", "PASSES_ITEMS_TO"})
_KINDS = {
    "Person": "person",
    "Establishment": "establishment",
    "Organisation": "group",
    "Device": "handset",
}


def _sources() -> dict[str, str]:
    return {seed.id: f"{seed.source}:{seed.id}" for seed in (PID, PID_SCALE)}


#: The profile each dataset holds: the demo plan is the demo dataset's and the scale plan the scale
#: dataset's, never the other's.
_PROFILES = {PID.id: "demo", PID_SCALE.id: "scale"}


def _properties(entity: PlanEntity) -> dict[str, Any]:
    """An entity's properties as a Studio load stores them: a handset's `imei` and a SIM's `imsi`
    and normalised value through the same Knowledge Adapters R6 binds (the plan, and the files,
    hold the written 15-digit IMEI; the stored form is the adapter's 14 digits)."""
    props = {k: _value(v) for k, v in entity.properties.items()}
    if entity.entity_type == "Device":
        props["imei"] = imei(str(props["imei"]))
    elif entity.properties.get("endpoint_kind") == "imsi":
        props["imsi"] = imsi(str(props["imsi"]))
        props["value_normalised"] = imsi(str(props["value_normalised"]))
    return props


def _value(value: object) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    return list(value) if isinstance(value, tuple) else value


def _handling(handling: PlanHandling) -> Handling:
    return Handling(
        classification=handling.classification,
        handling_code=handling.handling_code,
        action_code=handling.action_code,
        sanitisation_code=handling.sanitisation_code,
        originator=handling.originator,
        owning_unit=handling.owning_unit,
    )


def _interval(plan: Plan, link: PlanLink) -> Interval | None:
    if link.link_type in _SPANS:
        if link.first_seen is None:
            return None
        last = None if link.last_seen is None else end_of(link.last_seen)
        return Interval(valid_from=start_of(link.first_seen), valid_to=last)
    instants = link_instants(plan, link)
    if not instants:
        return None
    return Interval(valid_from=min(instants), valid_to=max(instants))


def _is_picture(entity: PlanEntity) -> bool:
    return entity.entity_type == "Document" and entity.properties.get("media_kind") == "image"


def _provenance(
    state: ProvenanceState, source: str, key: str, created_at: datetime, **extra: Any
) -> Provenance:
    ref = SourceRef(
        document_id=source, locator=key, excerpt_hash=hashlib.sha256(key.encode()).hexdigest()
    )
    return Provenance(state=state, sources=[ref], first_seen=created_at, **extra)


def writes(
    plan: Plan, moment: Moment, *, dataset: str, created_at: datetime
) -> tuple[list[NodeWrite], list[EdgeWrite]]:
    """Every node and link the plan holds by the end of `moment`, the one `SECRET` link included
    (a store that leaves it out does so itself). `ValueError` for a dataset that is not one of the
    two the generator writes."""
    sources = _sources()
    if dataset not in sources:
        raise ValueError(
            f"{dataset!r} is not a Prison Intelligence dataset: expected one of {sorted(sources)}"
        )
    if plan.profile != _PROFILES[dataset]:
        raise ValueError(
            f"the {plan.profile} plan is not the {dataset!r} dataset's: it is the "
            f"{_PROFILES[dataset]} plan's"
        )
    source = sources[dataset]
    rank = _MOMENT_ORDER[moment]
    nodes = [
        NodeWrite(
            id=node_id(e.key),
            type=e.entity_type,
            properties=_properties(e),
            provenance=_provenance(ProvenanceState.ASSERTED, source, e.key, created_at),
            handling=_handling(e.handling),
            created_by=CREATED_BY,
            created_at=created_at,
            datasets=[dataset],
        )
        for e in plan.entities
        if _MOMENT_ORDER[entity_moment(plan, e.key)] <= rank and not _is_picture(e)
    ]
    edges = []
    for link in links_at(plan, moment, secret_cleared=True):
        if link.link_type == "DEPICTS":
            continue
        inferred = link.provenance == "inferred"
        edges.append(
            EdgeWrite(
                id=link_id(link),
                type=link.link_type,
                source=node_id(link.source),
                target=node_id(link.target),
                properties=dict(link.properties),
                interval=_interval(plan, link),
                occurrences=link.occurrences,
                provenance=_provenance(
                    ProvenanceState.INFERRED if inferred else ProvenanceState.ASSERTED,
                    source,
                    link.key,
                    created_at,
                    **(
                        {
                            "extracted_by": link.extracted_by,
                            "extraction_confidence": link.extraction_confidence,
                        }
                        if inferred
                        else {}
                    ),
                ),
                handling=_handling(link.handling),
                created_by=CREATED_BY,
                created_at=created_at,
                datasets=[dataset],
            )
        )
    return nodes, edges


def picture_kind(plan: Plan, subject_key: str) -> str:
    """The kind of picture a subject gets: a person, an establishment, a wing or a yard, a handset
    or a group."""
    entity = plan.entity(subject_key)
    if entity.entity_type == "Location":
        return "wing" if str(entity.properties["site_ref"]).split(":")[-2] == "wing" else "yard"
    return _KINDS[entity.entity_type]


def picture_writes(plan: Plan) -> list[tuple[str, str, bytes]]:
    """One (subject node id, file name, PNG bytes) for each subject that has a picture, in the
    plan's order, for the picture route to attach (`EntityPictureService.set`). The name is the
    subject's key with colons replaced, so it passes the route's own name check."""
    return [
        (
            node_id(key),
            key.replace(":", "_") + ".png",
            pid_pictures.draw_picture(key, picture_kind(plan, key), plan.seed),
        )
        for key in plan.picture_subjects
    ]
