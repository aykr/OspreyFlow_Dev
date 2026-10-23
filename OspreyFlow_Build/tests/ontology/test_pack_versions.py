"""The composed ontology keeps each pack's name and `pack_version` (`06_DECISIONS.md` ADR-120 D10,
first bullet), so a published recipe can pin the pack versions it was written against.

What each test checks, and the violation that fails it:
- `test_the_core_alone_carries_no_pack`: the core claiming a pack.
- `test_the_deployment_ontology_carries_every_pack_s_version`: a composed schema dropping the
  versions, or a pack bump without this test's literal pin (fibo 1, niem 3, stix 1) moving.
- `test_composing_one_pack_records_only_that_pack`: versions recorded for packs not composed.
- `test_composing_onto_a_composed_schema_keeps_its_pack_versions`: composing onto an already
  composed schema forgetting the versions it carries (starting from an empty map).
- `test_a_pack_without_an_integer_version_is_refused`: a pack file with a missing, string,
  boolean (an `int` in Python), zero or negative version being accepted.
- `test_the_public_copy_keeps_the_pack_versions`: `public_ontology` dropping `packs`. It checks
  the function only; the route's own JSON is asserted in `test_link_type_routes.py`, against the
  core-only ontology that test serves.
"""

from __future__ import annotations

from typing import Any

import pytest

from ontology.errors import OntologyError
from ontology.loader import load_default_ontology
from ontology.packs import PACK_NAMES, compose_with_packs, load_deployment_ontology, load_pack


def test_the_core_alone_carries_no_pack() -> None:
    assert load_default_ontology().packs == {}


def test_the_deployment_ontology_carries_every_pack_s_version() -> None:
    packs = load_deployment_ontology().packs
    assert packs == {name: load_pack(name)["pack_version"] for name in PACK_NAMES}
    # Pinned on purpose: a pack bump must change this line as well as the pack file.
    assert packs == {"fibo": 1, "niem": 3, "stix": 1}


def test_composing_one_pack_records_only_that_pack() -> None:
    assert compose_with_packs(load_default_ontology(), ["niem"]).packs == {"niem": 3}


def test_composing_onto_a_composed_schema_keeps_its_pack_versions() -> None:
    core = load_default_ontology()
    composed = compose_with_packs(compose_with_packs(core, ["fibo"]), ["niem"])
    assert composed.packs == {"fibo": 1, "niem": 3}


_REMOVED: Any = object()


@pytest.mark.parametrize(
    "bad", [_REMOVED, "3", True, 0, -1], ids=["missing", "string", "bool", "zero", "negative"]
)
def test_a_pack_without_an_integer_version_is_refused(
    bad: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ontology.packs as packs

    real_load = packs.load_pack

    def broken(name: str) -> dict[str, Any]:
        raw = dict(real_load(name))
        if bad is _REMOVED:
            raw.pop("pack_version", None)
        else:
            raw["pack_version"] = bad
        return raw

    monkeypatch.setattr(packs, "load_pack", broken)
    with pytest.raises(OntologyError) as caught:
        compose_with_packs(load_default_ontology(), ["niem"])
    assert "niem" in str(caught.value)
    assert "pack_version" in str(caught.value)


def test_the_public_copy_keeps_the_type_packs() -> None:
    """`public_ontology` dropping `type_packs`, which the served schema (`GET /v1/ontology`) would
    then lose, leaving a client unable to tell which pack defines a type."""
    from services.api.link_types import public_ontology

    deployed = load_deployment_ontology()
    assert deployed.type_packs, "the premise: the deployment ontology has pack-defined types"
    assert public_ontology(deployed).type_packs == deployed.type_packs


def test_the_public_copy_keeps_the_pack_versions() -> None:
    from services.api.link_types import public_ontology

    deployed = load_deployment_ontology()
    assert public_ontology(deployed).packs == deployed.packs


def test_type_packs_holds_every_type_each_pack_defines() -> None:
    """ADR-120 Amendment 1, decision 2: a pack's own entity and link types are recorded against it,
    so a recipe writing one can be pinned. Red if a type a pack defines is missing from the map or
    credited to another pack, or if the core's own types are credited to a pack."""
    deployed = load_deployment_ontology()
    expected: dict[str, str] = {}
    for name in PACK_NAMES:
        raw = load_pack(name)
        for entity in raw.get("entity_types") or []:
            expected[entity["name"]] = name
        for edge in raw.get("edge_types") or []:
            if not edge.get("extends"):
                expected[edge["name"]] = name
    assert expected, "the packs define nothing, so this test would prove nothing"
    assert deployed.type_packs == expected
    assert load_default_ontology().type_packs == {}


def test_type_packs_holds_no_widened_type() -> None:
    """ADR-120 Amendment 1, decision 1: widening only adds link ends, so the core's `TRANSACTED`,
    `USES` and `DEPICTS` stay the core's. Red if a widened type is credited to the pack widening
    it, which would pin FIBO on a `TRANSACTED` between two core endpoints."""
    type_packs = load_deployment_ontology().type_packs
    for widened in ("TRANSACTED", "USES", "DEPICTS"):
        assert widened not in type_packs
    # The guard is not vacuous: a pack's own type is there.
    assert type_packs["Account"] == "fibo"
