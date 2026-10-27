"""Domain ontology packs (`06_DECISIONS.md` ADR-108, phase D): versioned, licence-registered
overlays over the POLE core — FIBO, NIEM, STIX 2.1 — composed per pipeline, never editing the
core in place.

**Composition rules.** A pack's entity type must not exist already (collision refused by name).
A pack's edge type is a definition unless it carries `extends: true`, which may only widen an
existing edge type's ends — the one mechanism by which a pack touches the core (FIBO adds
Accounts to `TRANSACTED`'s ends; STIX adds SDOs to `USES`'); everything else about the extended
type stays the core's. The composed schema then passes the loader's own checks (channel-and-shape
uniqueness, endpoint names), so a pack cannot smuggle in what `default.yaml` could not declare.
The composed version stays the core's; the composed schema also carries each pack's
`pack_version` (`OntologySchema.packs`) and which pack defines each type it adds
(`OntologySchema.type_packs`, a type a pack only widens excluded). A published recipe pins, beside
`ontology_version`, every pack it names and every pack whose types it writes ("names or writes",
ADR-120 Amendment 1), and a pack bump flags those recipes as a core bump flags every recipe; the
pinning (publish and the start-up backfill), the engine's refusal of a stale pin and the flagging
are built (ADR-120 D10, Amendments 1 to 3).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, get_args

import yaml

from schemas.domain import DomainPack, EdgeTypeDef, EntityTypeDef, OntologySchema
from schemas.ingest import DomainPackEntry

from .errors import OntologyError
from .loader import _check_edge_endpoints, _check_entity_types, check_icon_by_value

#: ADR-126: the values are `schemas.domain.DomainPack`'s, so a case's packs and the deployment's
#: packs cannot drift apart.
PACK_NAMES: tuple[str, ...] = get_args(DomainPack)

_PACKS_DIR = Path(__file__).parent / "packs"


def load_pack(name: str) -> dict[str, Any]:
    """One pack's raw document; refused by name before the filesystem is asked."""
    if name not in PACK_NAMES:
        raise OntologyError(f"unknown domain pack '{name}'; the packs are {', '.join(PACK_NAMES)}")
    raw = yaml.safe_load((_PACKS_DIR / f"{name}.yaml").read_text())
    if not isinstance(raw, dict):
        raise OntologyError(f"pack '{name}' is not a YAML mapping")
    return raw


def compose_with_packs(base: OntologySchema, packs: list[str]) -> OntologySchema:
    """The core plus each named pack, in order; the result passes the loader's own checks."""
    entity_types = list(base.entity_types)
    edge_types = list(base.edge_types)
    versions = {**base.packs}
    type_packs = {**base.type_packs}
    for name in packs:
        raw = load_pack(name)
        declared = raw.get("pack_version")
        if not isinstance(declared, int) or isinstance(declared, bool) or declared < 1:
            raise OntologyError(f"pack '{name}' has no integer pack_version ≥ 1 (ADR-120 D10)")
        versions[name] = declared
        known_entities = {e.name for e in entity_types}
        for entry in raw.get("entity_types") or []:
            if entry["name"] in known_entities:
                raise OntologyError(
                    f"pack '{name}' defines entity type '{entry['name']}', which already exists"
                )
            entity_types.append(EntityTypeDef.model_validate(entry))
            type_packs[entry["name"]] = name
            known_entities.add(entry["name"])
        edges_by_name = {e.name: e for e in edge_types}
        for entry in raw.get("edge_types") or []:
            if entry.get("extends"):
                existing = edges_by_name.get(entry["name"])
                if existing is None:
                    raise OntologyError(
                        f"pack '{name}' extends edge type '{entry['name']}', which does not exist"
                    )
                widened = existing.model_copy(
                    update={
                        "from_types": [
                            *existing.from_types,
                            *[t for t in entry.get("from", []) if t not in existing.from_types],
                        ],
                        "to_types": [
                            *existing.to_types,
                            *[t for t in entry.get("to", []) if t not in existing.to_types],
                        ],
                    }
                )
                edge_types[edge_types.index(existing)] = widened
                edges_by_name[entry["name"]] = widened
                continue
            if entry["name"] in edges_by_name:
                raise OntologyError(
                    f"pack '{name}' defines edge type '{entry['name']}', which already exists; "
                    "widening an existing type needs `extends: true`"
                )
            defined = EdgeTypeDef.model_validate(entry)
            edge_types.append(defined)
            edges_by_name[defined.name] = defined
            type_packs[defined.name] = name

    _check_entity_types(entity_types)
    check_icon_by_value(entity_types)
    _check_edge_endpoints(entity_types, edge_types)
    return OntologySchema(
        version=base.version,
        entity_types=entity_types,
        edge_types=edge_types,
        packs=versions,
        type_packs=type_packs,
    )


_PACK_LABELS = {
    "fibo": "Financial fraud and AML (FIBO)",
    "niem": "Crime case analysis (NIEM)",
    "stix": "Cyber threat analytics (STIX 2.1)",
}


def pack_catalogue() -> list[DomainPackEntry]:
    """The Studio's domain-model choices: the POLE core first (it adds nothing to itself), then
    each pack with what it brings — read from the packs themselves, never hardcoded."""
    entries = [DomainPackEntry(name="pole", label="Bespoke POLE (the core model)")]
    for name in PACK_NAMES:
        raw = load_pack(name)
        entries.append(
            DomainPackEntry(
                name=name,
                label=_PACK_LABELS[name],
                entity_types=[e["name"] for e in raw.get("entity_types") or []],
                edge_types=[e["name"] for e in raw.get("edge_types") or []],
            )
        )
    return entries


def load_deployment_ontology() -> OntologySchema:
    """The schema a deployment applies and serves (ADR-108 Amendment 4): the core composed with
    every shipped pack, at the core's own version. `compose_with_packs` had no production caller
    before this — a pipeline could choose FIBO at save and publish and still have its `Account`
    rows refused at run time, because the store's applied schema never carried the pack's types.
    Composition is deterministic (the packs ship with the code and collisions are refused at
    load), so "version N" remains well defined: it is version N as this build composes it. The
    pipeline's own chosen pack remains the Studio's declared vocabulary and the run report's
    words; this is the superset the store accepts."""
    from .loader import load_default_ontology

    return compose_with_packs(load_default_ontology(), list(PACK_NAMES))
