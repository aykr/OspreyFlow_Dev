"""`_pending_port_placeholders.py` must not outlive the phases that replace it.

`GraphPort`'s placeholder types moved to the real domain model
(`schemas/domain.py`) in Phase 1 once `graph_arcadedb` was registered —
`_phase0_placeholders.py` is gone (this phase's own exit
criterion). `AnalyticsPort`'s moved to `schemas/analytics.py` in Phase 2 once
`analytics_duckdb` was registered. `ModelPort`'s moved to `schemas/model.py`
across Phase 6 Stages 1 and 2 as `adapters/model_litellm` implemented each
pair for real.

Note on this test's history: through Phase 6, a port's placeholder types and
its adapter registration always landed in the same phase/stage, so gating
the module's deletion on "are all three of `ANALYTICS_PORT_ADAPTERS`/
`COMPUTE_PORT_ADAPTERS`/`MODEL_PORT_ADAPTERS` populated" was a correct proxy
for "does any placeholder content remain" — the two conditions never
diverged. Phase 7 Stage 2 is the first point they do: standing rule 1
(conformance suites, and the schemas they need, before any adapter) moves
`ComputePort`'s real schemas (`schemas/compute.py`) ahead of
`adapters/compute_rustworkx`'s own registration by a full stage.
Checked directly, not assumed, before writing the module off: keying
deletion to registry population would have kept `_pending_port_placeholders.py`
around empty of all content, `COMPUTE_PORT_ADAPTERS` being the only registry
still unpopulated — which is exactly the "an instruction whose condition no
longer matches what it was protecting" shape this project's own graphify-hook
finding already named once. Corrected here to what the module's own
docstring always actually described: it exists while any port's placeholder
content remains, checked by import, not by a proxy that stopped tracking it.
"""

from __future__ import annotations

import importlib.util


def test_pending_port_placeholders_module_is_gone() -> None:
    """`ComputePort` was the last port carrying placeholder content
    (`schemas/compute.py` replaced it in Phase 7 Stage 2, ahead of
    `adapters/compute_rustworkx`'s own registration — standing rule 1).
    Every port now has real domain content; this module must never come
    back, the same permanent regression `test_phase0_placeholders_module_
    is_gone` already proves for its own Phase 0 predecessor."""
    assert importlib.util.find_spec("schemas._pending_port_placeholders") is None


def test_phase0_placeholders_module_is_gone() -> None:
    """`GRAPH_PORT_ADAPTERS` is non-empty from Phase 1 on, so this module
    must never come back — see `tests/conformance/graph_port/test_guard.py`
    for the corresponding registry-population assertion."""
    assert importlib.util.find_spec("schemas._phase0_placeholders") is None
