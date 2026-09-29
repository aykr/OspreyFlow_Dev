"""Shared mechanics for the per-port conformance guard tests.

See the Phase 0 plan §2.A: the guard test is what makes an accidentally-broken
suite module fail loudly, rather than pytest silently reporting zero collected
tests for a parametrised suite whose registry happens to be empty.
"""

from __future__ import annotations

import importlib


def suite_imports_cleanly(module_name: str) -> bool:
    importlib.import_module(module_name)
    return True
