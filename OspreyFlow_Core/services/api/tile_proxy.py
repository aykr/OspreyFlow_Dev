"""Proxies a tile request to a tier-3/tier-4 provider — `spec/00_ARCHITECTURE.md`
§1.2's "The tile proxy": credential secrecy (a `credential: env:VAR`
reference resolved here, never sent to the browser), egress policy (this
is the one named, auditable exception to default-deny egress), caching/
entitlement (`services/api/tile_cache.py`'s job, called by the route this
module's `fetch_tile` feeds — `services/api/app.py`).

`httpx`'s actual network call is injected out via `http_get`, the same
shape `scripts/build_local_basemap.py`'s `download_extract` already uses
for its own network call — CI never depends on a third party's
availability, so this is exercised in
tests only for its argument-construction/error-handling, with a real
network call happening only against a local loopback stand-in server.

**The `MapProvider.endpoint` conflict this docstring used to record is
closed, in Phase 5's known-gaps closure.** `endpoint` is always a bare service base URL — the
same shape `services/api/tier4_registration.py`'s `register_tier4_provider`
and `scripts/verify_map.py`'s CRS check already used, and the one
`spec/00_ARCHITECTURE.md`'s own worked `wmts-corporate` example writes.
For `service: wmts`, `build_upstream_url` now builds a real WMTS KVP
`GetTile` request from that bare endpoint plus `provider.layer` and the
three fields `register_tier4_provider` discovers alongside it
(`tile_matrix_set`/`format`/`wmts_style`) — never a `{z}`/`{x}`/`{y}`
*template* stored in `endpoint` itself. Tiers 1-3's `source`, and any
non-WMTS tier-4 shape (out of scope until tier-4 breadth work), keep the
original template-substitution behaviour unchanged.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import cast
from urllib.parse import quote

import httpx
from services.api.credentials import resolve_env_credential

from schemas.mapconfig import MapProvider, OgcServiceKind


class MissingMapKeyError(RuntimeError):
    """A provider whose tiles need a key, with none held (ADR-147). Fixed words naming the provider
    and where a key is set, never an address."""

    def __init__(self, provider_id: str) -> None:
        self.provider_id = provider_id
        super().__init__(
            f"The map provider {provider_id!r} needs a key and none is set. Someone who manages "
            "geospatial settings can set it in Admin › Maps."
        )


def _key_for(provider: MapProvider, key: str | None) -> str | None:
    """The key a request carries: the one set in *Admin › Maps* (`key`) first, then `osprey.yaml`'s
    `credential: env:VAR`; refused in words where the provider needs one and neither is held."""
    if key is not None:
        return key
    if provider.credential is not None:
        return resolve_env_credential(provider.credential)
    if provider.needs_key:
        raise MissingMapKeyError(provider.id)
    return None


def _build_wmts_kvp_url(
    provider: MapProvider, z: int, x: int, y: int, key: str | None = None
) -> str:
    """A real WMTS KVP `GetTile` request against a bare service `endpoint`
    — see this module's own docstring for why `endpoint` is never a
    template for a WMTS provider. Every one of `layer`/`tile_matrix_set`/
    `format`/`wmts_style` must already be set: they are what
    `register_tier4_provider` discovers at registration, hand-copied into
    `osprey.yaml` the same way `layer` alone used to be before this fix.
    """
    missing = [
        name
        for name, value in (
            ("layer", provider.layer),
            ("tile_matrix_set", provider.tile_matrix_set),
            ("format", provider.format),
            ("wmts_style", provider.wmts_style),
        )
        if value is None
    ]
    if missing:
        raise ValueError(
            f"provider {provider.id!r} is missing {', '.join(missing)} — required for a WMTS "
            "KVP GetTile request (register_tier4_provider discovers these; copy them into "
            "osprey.yaml the same way layer already is)"
        )
    extra_params = "".join(f"&{quote(k)}={quote(v)}" for k, v in provider.variables.items())
    secret = _key_for(provider, key)
    if secret is not None and provider.credential_param is None:
        raise ValueError(
            f"provider {provider.id!r} is a WMTS service holding a key but names no "
            "credential_param for it, so the key has nowhere to go"
        )
    if secret is not None:
        # `credential_param` is required with a WMTS credential (`MapProvider`'s own check), and a
        # key set in Admin needs it too (`needs_key`), so it is set here.
        extra_params += f"&{quote(cast(str, provider.credential_param))}={quote(secret, safe='')}"
    # `missing` above already proves each of these four is not None for a `service: wmts`
    # provider that reaches this point — the `cast`s tell mypy what the raise already enforces
    # at runtime, without repeating it as a redundant assertion.
    return (
        f"{provider.endpoint}?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0"
        f"&LAYER={quote(cast(str, provider.layer))}&STYLE={quote(cast(str, provider.wmts_style))}"
        f"&TILEMATRIXSET={quote(cast(str, provider.tile_matrix_set))}"
        f"&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&FORMAT={quote(cast(str, provider.format))}"
        f"{extra_params}"
    )


def build_upstream_url(
    provider: MapProvider, z: int, x: int, y: int, *, key: str | None = None
) -> str:
    """A real WMTS KVP `GetTile` URL for `service: wmts` (see
    `_build_wmts_kvp_url`); otherwise substitutes `{z}`/`{x}`/`{y}`, every
    `provider.variables` entry, and — when `provider.credential` is set —
    a `{credential}` placeholder with the resolved value, into
    `provider.endpoint or provider.source` as a template.

    A key set in *Admin › Maps* (`key`, read from the Conduit's map key file) comes before
    `osprey.yaml`'s `credential: env:VAR`; a provider that needs a key and holds neither is
    refused in words (`MissingMapKeyError`). `{credential}` is where a template takes it, and a WMTS
    request's `credential_param` names its query parameter (ADR-147 decision 4).
    """
    if provider.service is OgcServiceKind.WMTS:
        return _build_wmts_kvp_url(provider, z, x, y, key)
    template = provider.endpoint or provider.source
    if template is None:
        raise ValueError(f"provider {provider.id!r} has no endpoint or source template to proxy")
    values: dict[str, str] = {**provider.variables, "z": str(z), "x": str(x), "y": str(y)}
    secret = _key_for(provider, key)
    if secret is not None:
        values["credential"] = secret
    return template.format(**values)


async def _http_get(url: str) -> bytes:
    async with httpx.AsyncClient() as client:
        response = await client.get(url, timeout=10.0)
        response.raise_for_status()
        return response.content


async def fetch_tile(url: str, *, http_get: Callable[[str], Awaitable[bytes]] = _http_get) -> bytes:
    return await http_get(url)
