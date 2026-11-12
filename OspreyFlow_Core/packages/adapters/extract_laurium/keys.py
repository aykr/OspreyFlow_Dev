"""Laurium's own gateway key (`06_DECISIONS.md` ADR-135 Amendment 6 decision 8): the gateway's
master key never crosses into Laurium's container.

The master key is admin on the gateway (it makes, changes and deletes every key and model), and
Laurium's image runs 126 third-party packages. So the Conduit, which holds the master key, sends
Laurium's service a **scoped virtual key** for each call and never the master key:

- a call for a hosted engine goes with that engine's own key (`usage.engine_key`), as Deep read's;
- a call for the deployment's own models (`local`), or outside the routing, goes with **Laurium's
  own key**, made here like the engines' keys: an HMAC under the master key, never stored, which
  each Conduit derives alike, held on the gateway with `models` naming the deployment's own models
  alone (never empty: an empty `models` is every model, measured), and no admin right.

Its own label (`osprey-service:laurium`) keeps it apart from any engine's key, even an engine
named `laurium`. It is tagged `metadata.osprey_service`, not `osprey_engine`, so the engines'
stale-key sweep (`ModelAdmin.revoke_stale_engine_keys`) leaves it alone. It is made at the
Conduit's start, and every older Laurium key deleted, by `laurium_at_start` (P12 part 2, through
`services.api.laurium_start`).
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Sequence

import httpx

_LABEL = b"osprey-service:laurium"
METADATA = {"osprey_service": "laurium"}


class LauriumKeyRefused(Exception):
    """The gateway would not make or change Laurium's key; in fixed words, never the gateway's."""


def laurium_key(master: str) -> str:
    """Laurium's own gateway key, derived from the master key. Refused from an empty master key,
    from which anyone could derive it."""
    if not master.strip():
        raise ValueError("no master key: Laurium's key is never derived from an empty one")
    return "sk-osprey-laurium-" + hmac.new(master.encode(), _LABEL, hashlib.sha256).hexdigest()[:48]


async def put_laurium_key(gateway: httpx.AsyncClient, master: str, models: Sequence[str]) -> str:
    """Laurium's key held on the gateway with `models` alone: updated where the gateway holds it,
    made where it does not (the update's 404), as `ModelAdmin.put_engine_key` does. The key travels
    only in a request's body; every answer is discarded (the update's carries the key)."""
    if not models:
        raise ValueError("Laurium's key names at least one model: an empty list is every model")
    key = laurium_key(master)
    auth = {"Authorization": f"Bearer {master}"}
    fields = {"key": key, "models": list(models)}
    resp = await gateway.post("/key/update", json=fields, headers=auth)
    if resp.status_code == 404:
        resp = await gateway.post(
            "/key/generate", json={**fields, "metadata": METADATA}, headers=auth
        )
    if resp.status_code != 200:
        raise LauriumKeyRefused(
            f"The model gateway refused Laurium's key (HTTP {resp.status_code})."
        )
    return key


async def delete_laurium_key(gateway: httpx.AsyncClient, master: str) -> None:
    resp = await gateway.post(
        "/key/delete",
        json={"keys": [laurium_key(master)]},
        headers={"Authorization": f"Bearer {master}"},
    )
    if resp.status_code not in (200, 404):  # 404: none was held (measured)
        raise LauriumKeyRefused(
            f"The model gateway refused to delete Laurium's key (HTTP {resp.status_code})."
        )


#: As the engines' sweep reads the gateway's keys (`ModelAdmin.revoke_stale_engine_keys`): at most
#: 100 a page (measured), every page read before anything is deleted.
_KEY_PAGE = 100
_MAX_KEY_PAGES = 100


async def laurium_at_start(gateway: httpx.AsyncClient, master: str, models: Sequence[str]) -> str:
    """At the Conduit's start, Laurium chosen (decision 8, part 2): Laurium's key held with `models`
    alone, and **every other key tagged as Laurium's deleted**, so a key made from a master key
    since rotated is not left valid for whoever holds the old one. Every page of `/key/list` is
    read before anything is deleted, and each stale key is named by its SHA-256 alone, so no old
    key travels. A key not tagged `osprey_service: laurium` is someone else's and is left alone."""
    key = await put_laurium_key(gateway, master, models)
    current = hashlib.sha256(key.encode()).hexdigest()
    auth = {"Authorization": f"Bearer {master}"}
    stale: list[str] = []
    page, pages = 1, 1
    while page <= pages:
        if page > _MAX_KEY_PAGES:
            raise LauriumKeyRefused(
                f"The model gateway holds more than {_MAX_KEY_PAGES * _KEY_PAGE} keys, so "
                "Laurium's old keys were not looked for."
            )
        resp = await gateway.get(
            "/key/list",
            params={"return_full_object": "true", "page": page, "size": _KEY_PAGE},
            headers=auth,
        )
        if resp.status_code != 200:
            raise LauriumKeyRefused(
                f"The model gateway refused the list of keys (HTTP {resp.status_code})."
            )
        body = resp.json()
        pages = int(body.get("total_pages") or 1)
        for row in body.get("keys") or []:
            token = str(dict(row).get("token") or "")
            tag = dict(dict(row).get("metadata") or {}).get("osprey_service")
            if tag == METADATA["osprey_service"] and token and token != current:
                stale.append(token)
        page += 1
    for token in stale:
        resp = await gateway.post("/key/delete", json={"keys": [token]}, headers=auth)
        if resp.status_code not in (200, 404):
            raise LauriumKeyRefused(
                f"The model gateway refused to delete an old Laurium key (HTTP {resp.status_code})."
            )
    return key
