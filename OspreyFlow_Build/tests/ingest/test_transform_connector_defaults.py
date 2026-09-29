"""Every Knowledge Adapter that takes a connector default receives it — round 13cf.

`services/ingest/transforms.py`'s `_CONNECTOR_DEFAULT_PARAMS` is a hand-kept table of which
adapter gets which connector-level default. `polygon_ref` (owner ruling R9) was registered
without an entry, so on a real deployment every site-grid row reached it with no `source_crs`,
was refused as "ambiguous coordinate reference system", and the grid route 500ed. Nothing in
process could see it: the grid route's own tests monkeypatch `run_recipe`, and the recipe
end-to-end test is live-tier.

The guard is on the class, not the instance: any adapter whose signature names a connector
default must be in the table, so the next adapter added this way cannot repeat it.
"""

from __future__ import annotations

import inspect

import pytest
from services.ingest.transforms import _CONNECTOR_DEFAULT_PARAMS, apply_transform

from knowledge_adapters import REGISTRY

_CONNECTOR_DEFAULTS = ("source_crs", "date_order")


@pytest.mark.parametrize("name", sorted(REGISTRY))
def test_an_adapter_taking_a_connector_default_is_given_it(name: str) -> None:
    parameters = inspect.signature(REGISTRY[name]).parameters
    wanted = {p for p in _CONNECTOR_DEFAULTS if p in parameters}
    assert wanted <= set(_CONNECTOR_DEFAULT_PARAMS.get(name, ())), (
        f"{name!r} takes {sorted(wanted)} but `_CONNECTOR_DEFAULT_PARAMS` does not pass it, so "
        "a connector's declared default never reaches it"
    )


def test_polygon_ref_receives_the_connectors_source_crs() -> None:
    """The real call shape: eight corner fields and a connector declaring EPSG:4326, as the
    site-grid recipe's own binding produces it."""
    corners = ("-1.836", "52.409", "-1.8355", "52.409", "-1.8355", "52.40875", "-1.836", "52.40875")
    ref = apply_transform("polygon_ref", corners, connector_defaults={"source_crs": "EPSG:4326"})
    assert ref == "geo:e0bb0c71a866d86d"
