"""Proxies a tile request to a tier-3/tier-4 provider — `docs/00_ARCHITECTURE.md`
§1.2's "The tile proxy": credential secrecy (a `credential: env:VAR`
reference resolved here, never sent to the browser), egress policy (this
is the one named, auditable exception to default-deny egress), caching/
entitlement (`services/api/tile_cache.py`'s job, called by the route this
module's `fetch_tile` feeds — `services/api/app.py`).

`httpx`'s actual network call is injected out via `http_get`, the same
shape `scripts/build_local_basemap.py`'s `download_extract` already uses
for its own network call — CI never depends on a third party's
availability (`07_BUILD_PLAN.md` standing rule 3), so this is exercised in
tests only for its argument-construction/error-handling, with a real
network call happening only against a local loopback stand-in server.

**The `MapProvider.endpoint` conflict this docstring used to record is
closed, in Phase 5's known-gaps closure.** `endpoint` is always a bare service base URL — the
same shape `services/api/tier4_registration.py`'s `register_tier4_provider`
and `scripts/verify_map.py`'s CRS check already used, and the one
`docs/00_ARCHITECTURE.md`'s own worked `wmts-corporate` example writes.
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


def _build_wmts_kvp_url(provider: MapProvider, z: int, x: int, y: int) -> str:
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
    if provider.credential is not None:
        # Resolving *where* a credential belongs in a KVP GetTile request is
        # a real, separate naming gap `docs/07_BUILD_PLAN.md`'s Phase 5
        # known-gaps list already records for the template path
        # (`{credential}`'s own placeholder-naming flag below) — no shipped
        # or tested provider exercises a credentialed WMTS KVP request yet,
        # so this raises rather than guessing a query-parameter name.
        raise NotImplementedError(
            f"provider {provider.id!r} declares a credential, but no KVP query-parameter name "
            "for it is defined yet — flagged, not guessed"
        )
    extra_params = "".join(f"&{quote(k)}={quote(v)}" for k, v in provider.variables.items())
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


def build_upstream_url(provider: MapProvider, z: int, x: int, y: int) -> str:
    """A real WMTS KVP `GetTile` URL for `service: wmts` (see
    `_build_wmts_kvp_url`); otherwise substitutes `{z}`/`{x}`/`{y}`, every
    `provider.variables` entry, and — when `provider.credential` is set —
    a `{credential}` placeholder with the resolved value, into
    `provider.endpoint or provider.source` as a template.

    `{credential}` as the placeholder name is this checkpoint's own naming
    choice: `MapProvider`'s schema has no field naming which template
    placeholder a credential fills, and the architecture doc doesn't say
    either — flagged here rather than guessed silently.
    """
    if provider.service is OgcServiceKind.WMTS:
        return _build_wmts_kvp_url(provider, z, x, y)
    template = provider.endpoint or provider.source
    if template is None:
        raise ValueError(f"provider {provider.id!r} has no endpoint or source template to proxy")
    values: dict[str, str] = {**provider.variables, "z": str(z), "x": str(x), "y": str(y)}
    if provider.credential is not None:
        values["credential"] = resolve_env_credential(provider.credential)
    return template.format(**values)


async def _http_get(url: str) -> bytes:
    async with httpx.AsyncClient() as client:
        response = await client.get(url, timeout=10.0)
        response.raise_for_status()
        return response.content


async def fetch_tile(
    url: str, *, http_get: Callable[[str], Awaitable[bytes]] = _http_get
) -> bytes:
    return await http_get(url)
