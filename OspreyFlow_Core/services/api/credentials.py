"""Resolves a `MapProvider.credential` reference — `spec/00_ARCHITECTURE.md`
§1.2: "a reference, never a value" — server-side, at the one place this
repo ever reads an actual credential value. `services/api/mapconfig_loader.
py`'s `public_view()` never exposes `credential`; this module is the other
side of that boundary, called only from `services/api/tile_proxy.py`.
"""

from __future__ import annotations

import os


class MissingCredentialError(RuntimeError):
    def __init__(self, var_name: str) -> None:
        self.var_name = var_name
        super().__init__(f"environment variable {var_name!r} is not set")


def resolve_env_credential(reference: str) -> str:
    """`reference` is an already-validated `env:VAR_NAME` string
    (`schemas.mapconfig.MapProvider`'s own `_credential_is_a_reference_not_a_value`
    validator enforces the shape before this is ever called)."""
    var_name = reference.removeprefix("env:")
    value = os.environ.get(var_name)
    if value is None:
        raise MissingCredentialError(var_name)
    return value
